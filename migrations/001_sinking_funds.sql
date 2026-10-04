-- ══════════════════════════════════════════════════════════════════════════
-- Sinking Funds
-- Run once in the Supabase SQL editor. Idempotent — safe to re-run.
--
-- Accounting model:
--   balance = opening_balance
--           + SUM(expenses.amount_mxn) WHERE sinking_fund_id = fund
--                                        AND date    >= cycle_started_on
--           - SUM(payouts.amount_mxn)  WHERE sinking_fund_id = fund
--                                        AND paid_on >= cycle_started_on
--
-- Contributions are REAL expenses carrying sinking_fund_id, so net balance
-- drops when you save. Payouts live in their own table and are NEVER
-- expenses, so paying the bill from the fund cannot hit net balance twice.
-- ══════════════════════════════════════════════════════════════════════════


-- ── 1. Funds ──────────────────────────────────────────────────────────────
create table if not exists public.sinking_funds (
  id      uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,

  name  text not null check (length(btrim(name)) between 1 and 100),
  notes text,

  -- Nullable: an open-ended fund ("Car repairs") is valid, but only in
  -- fixed_per_period mode — enforced by sinking_funds_mode_fields below.
  target_amount   numeric(12,2) check (target_amount is null or target_amount > 0),
  currency_id     uuid references public.currencies(id),

  -- Fund balance at cycle_started_on. Seeded from the user's "already saved"
  -- input on create, then overwritten with the leftover surplus on every
  -- renewal. Never backed by an expense row, so it never affects net balance.
  opening_balance numeric(12,2) not null default 0 check (opening_balance >= 0),

  -- target_by_date   -> app derives the per-period set-aside
  -- fixed_per_period -> app derives the projected completion date
  mode text not null default 'target_by_date'
       check (mode in ('target_by_date','fixed_per_period')),
  contribution_amount numeric(12,2)
       check (contribution_amount is null or contribution_amount > 0),

  cadence text not null default 'monthly' check (cadence in ('weekly','monthly')),
  -- 0=Mon .. 6=Sun, matching projected_costs.day_of_week
  contribution_day_of_week  smallint check (contribution_day_of_week  between 0 and 6),
  contribution_day_of_month smallint check (contribution_day_of_month between 1 and 31),

  due_date         date,
  -- Scoping the ledger sums to this date is what makes renewal free:
  -- no rows move, none are deleted, no history is rewritten.
  cycle_started_on date not null default current_date,

  repeat_interval text not null default 'none'
       check (repeat_interval in ('none','monthly','quarterly','semiannual','annual')),
  -- Premiums drift. Applied to target_amount on each renewal.
  renewal_increase_pct numeric(5,2) not null default 0
       check (renewal_increase_pct between -100 and 100),
  auto_renew boolean not null default true,

  -- The auto-created "<name> Fund" expense category. Presentation only —
  -- used for analytics grouping and the Week View colour dot. The source of
  -- truth for the balance is expenses.sinking_fund_id, NOT this category.
  category_id       uuid references public.categories(id)      on delete set null,
  projected_cost_id uuid references public.projected_costs(id) on delete set null,

  is_active  boolean     not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint sinking_funds_mode_fields check (
       (mode = 'target_by_date'   and target_amount       is not null
                                  and due_date            is not null)
    or (mode = 'fixed_per_period' and contribution_amount is not null)
  ),

  -- A recurring fund needs a due date to roll forward from.
  constraint sinking_funds_repeat_needs_due check (
    repeat_interval = 'none' or due_date is not null
  )
);

create index if not exists sinking_funds_user_active_idx
  on public.sinking_funds(user_id, is_active);
create index if not exists sinking_funds_user_due_idx
  on public.sinking_funds(user_id, due_date);

alter table public.sinking_funds enable row level security;
drop policy if exists sinking_funds_owner on public.sinking_funds;
create policy sinking_funds_owner on public.sinking_funds
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);


-- ── 2. Payout ledger ──────────────────────────────────────────────────────
-- Payouts are deliberately NOT expenses. Net balance is derived only from
-- the expenses and earnings tables, so a payout row cannot move it and no
-- existing aggregation needs a new filter.
create table if not exists public.sinking_fund_payouts (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id)           on delete cascade,
  sinking_fund_id uuid not null references public.sinking_funds(id) on delete cascade,

  amount      numeric(12,2) not null check (amount > 0),
  currency_id uuid references public.currencies(id),
  amount_mxn  numeric(12,2) not null check (amount_mxn > 0),

  paid_on     date not null default current_date,
  week_number smallint,
  week_year   smallint,

  -- payout  -> the real bill was paid out of the fund
  -- release -> user pulled money back to spendable; creates an offsetting
  --            earning, because expenses.amount has a > 0 validator so a
  --            negative contribution is impossible
  kind  text not null default 'payout' check (kind in ('payout','release')),
  notes text,

  -- Audit trail: which cycle this payout closed.
  cycle_started_on date not null,
  cycle_due_date   date,

  -- Set only when the fund was short and the user topped up out of pocket.
  top_up_expense_id  uuid references public.expenses(id)        on delete set null,
  -- Set only for kind = 'release'.
  release_earning_id uuid references public.earnings(id)        on delete set null,
  -- Lets a linked planned cost read as paid without creating an expense.
  projected_cost_id  uuid references public.projected_costs(id) on delete set null,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists sf_payouts_user_fund_idx
  on public.sinking_fund_payouts(user_id, sinking_fund_id, paid_on desc);

alter table public.sinking_fund_payouts enable row level security;
drop policy if exists sf_payouts_owner on public.sinking_fund_payouts;
create policy sf_payouts_owner on public.sinking_fund_payouts
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);


-- ── 3. The link column on expenses ────────────────────────────────────────
-- Purely additive metadata, exactly like projected_cost_id.
-- ON DELETE SET NULL preserves financial history: deleting a fund never
-- deletes the expenses that funded it.
alter table public.expenses
  add column if not exists sinking_fund_id uuid
  references public.sinking_funds(id) on delete set null;

create index if not exists expenses_sinking_fund_idx
  on public.expenses(sinking_fund_id) where sinking_fund_id is not null;


-- ── 4. updated_at triggers ────────────────────────────────────────────────
-- Reuses the existing trigger function if the project already defines one.
-- If public.set_updated_at() does not exist, create it first:
--
--   create or replace function public.set_updated_at() returns trigger as $$
--     begin new.updated_at = now(); return new; end;
--   $$ language plpgsql;
--
do $$
begin
  if exists (select 1 from pg_proc where proname = 'set_updated_at') then
    drop trigger if exists sinking_funds_set_updated_at on public.sinking_funds;
    create trigger sinking_funds_set_updated_at
      before update on public.sinking_funds
      for each row execute function public.set_updated_at();

    drop trigger if exists sf_payouts_set_updated_at on public.sinking_fund_payouts;
    create trigger sf_payouts_set_updated_at
      before update on public.sinking_fund_payouts
      for each row execute function public.set_updated_at();
  end if;
end $$;
