-- ══════════════════════════════════════════════════════════════════════════
-- Expenses
-- Run once in the Supabase SQL editor. Idempotent — safe to re-run.
--
-- Money is stored twice on purpose. amount is what the user typed, in their
-- chosen currency; amount_mxn is that value converted at the rate in force
-- when the row was written. Every analytics aggregation sums amount_mxn, so
-- a later exchange rate change cannot silently rewrite past months.
--
-- week_number and week_year are generated columns, not application fields.
-- PostgREST cannot write a generated column, which is why changing an
-- expense date goes through the update_expense_date function in 011 rather
-- than a plain PATCH.
-- ══════════════════════════════════════════════════════════════════════════


-- ── 1. Table ──────────────────────────────────────────────────────────────
create table if not exists public.expenses (
  id      uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,

  amount      numeric(12,2) not null check (amount > 0),
  currency_id uuid not null references public.currencies(id),
  -- Snapshot of amount at the exchange rate on the date of writing.
  amount_mxn  numeric(12,2) not null check (amount_mxn > 0),

  -- set null, not cascade: deleting a category must never destroy financial
  -- history. The row survives and reads as uncategorised.
  category_id uuid references public.categories(id) on delete set null,

  "date" date not null,

  -- ISO week, derived in the database so every client agrees on the bucket.
  -- The expression has to be immutable, which rules out anything that reads
  -- the user's week_start_day preference; that is applied in Python on read.
  week_number smallint generated always as (extract(week   from "date")::smallint) stored,
  week_year   smallint generated always as (extract(isoyear from "date")::smallint) stored,

  notes text,

  -- Set when the row was produced by a recurring rule rather than by hand.
  -- The pair (recurring_rule_id, date) is what migration 012 makes unique.
  is_recurring      boolean not null default false,
  recurring_rule_id uuid references public.recurring_rules(id) on delete set null,

  -- Set when the user paid a planned cost, so the forecast can show it.
  projected_cost_id uuid references public.projected_costs(id) on delete set null,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- The listing query: every expense for a user, newest first.
create index if not exists expenses_user_date_idx
  on public.expenses(user_id, "date" desc);

-- The week view.
create index if not exists expenses_user_week_idx
  on public.expenses(user_id, week_year, week_number);

-- Category analytics, and the reference check before a category delete.
create index if not exists expenses_user_category_idx
  on public.expenses(user_id, category_id);

create index if not exists expenses_recurring_rule_idx
  on public.expenses(recurring_rule_id) where recurring_rule_id is not null;


-- ── 2. Row level security ─────────────────────────────────────────────────
alter table public.expenses enable row level security;
drop policy if exists expenses_owner on public.expenses;
create policy expenses_owner on public.expenses
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);


-- ── 3. updated_at trigger ─────────────────────────────────────────────────
drop trigger if exists expenses_set_updated_at on public.expenses;
create trigger expenses_set_updated_at
  before update on public.expenses
  for each row execute function public.set_updated_at();
