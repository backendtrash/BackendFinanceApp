-- ══════════════════════════════════════════════════════════════════════════
-- Projected costs
-- Run once in the Supabase SQL editor. Idempotent — safe to re-run.
--
-- Forecast only. Unlike recurring rules these never generate a transaction;
-- they are what real spending is compared against. That is why there is no
-- next_due_date here, and why the only link to reality is the optional
-- projected_cost_id an expense carries when the user pays one.
--
-- amount_mxn is deliberately NOT a column. The service layer converts on
-- read, so a forecast always reflects today's exchange rate. Real
-- transactions do the opposite and snapshot the rate at write time.
-- ══════════════════════════════════════════════════════════════════════════


-- ── 1. Table ──────────────────────────────────────────────────────────────
create table if not exists public.projected_costs (
  id      uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,

  name   text not null check (length(btrim(name)) > 0),
  amount numeric(12,2) not null check (amount > 0),

  -- Nullable: a projection entered without a currency is read as MXN.
  currency_id uuid references public.currencies(id),

  frequency text not null default 'monthly'
    check (frequency in ('monthly', 'weekly', 'one_time')),

  -- Only meaningful for one_time costs, which land in a specific month.
  month smallint check (month between 1 and 12),
  year  smallint check (year  between 2000 and 2100),

  category_id uuid references public.categories(id) on delete set null,
  is_active   boolean not null default true,
  notes       text,

  -- Drives the three-way split on the planning screen.
  plan_group text not null default 'committed'
    check (plan_group in ('committed', 'living', 'lifestyle')),

  -- 0=Mon .. 6=Sun. Places a weekly cost into one week bucket; when null the
  -- analytics layer spreads the cost across every week of the month.
  day_of_week  smallint check (day_of_week  between 0 and 6),
  day_of_month smallint check (day_of_month between 1 and 31),

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists projected_costs_user_active_idx
  on public.projected_costs(user_id, is_active);
create index if not exists projected_costs_user_period_idx
  on public.projected_costs(user_id, year, month);


-- ── 2. Row level security ─────────────────────────────────────────────────
alter table public.projected_costs enable row level security;
drop policy if exists projected_costs_owner on public.projected_costs;
create policy projected_costs_owner on public.projected_costs
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);


-- ── 3. updated_at trigger ─────────────────────────────────────────────────
drop trigger if exists projected_costs_set_updated_at on public.projected_costs;
create trigger projected_costs_set_updated_at
  before update on public.projected_costs
  for each row execute function public.set_updated_at();
