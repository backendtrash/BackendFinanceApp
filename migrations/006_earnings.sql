-- ══════════════════════════════════════════════════════════════════════════
-- Earnings
-- Run once in the Supabase SQL editor. Idempotent — safe to re-run.
--
-- Structurally the mirror of expenses, minus projected_cost_id: a planned
-- cost is a cost, so there is nothing for income to link back to.
-- The same generated week columns apply, so changing an earning date also
-- has to go through a function — update_earning_date in 011.
-- ══════════════════════════════════════════════════════════════════════════


-- ── 1. Table ──────────────────────────────────────────────────────────────
create table if not exists public.earnings (
  id      uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,

  amount      numeric(12,2) not null check (amount > 0),
  currency_id uuid not null references public.currencies(id),
  amount_mxn  numeric(12,2) not null check (amount_mxn > 0),

  category_id uuid references public.categories(id) on delete set null,

  "date" date not null,

  week_number smallint generated always as (extract(week    from "date")::smallint) stored,
  week_year   smallint generated always as (extract(isoyear from "date")::smallint) stored,

  notes text,

  is_recurring      boolean not null default false,
  recurring_rule_id uuid references public.recurring_rules(id) on delete set null,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists earnings_user_date_idx
  on public.earnings(user_id, "date" desc);
create index if not exists earnings_user_week_idx
  on public.earnings(user_id, week_year, week_number);
create index if not exists earnings_user_category_idx
  on public.earnings(user_id, category_id);
create index if not exists earnings_recurring_rule_idx
  on public.earnings(recurring_rule_id) where recurring_rule_id is not null;


-- ── 2. Row level security ─────────────────────────────────────────────────
alter table public.earnings enable row level security;
drop policy if exists earnings_owner on public.earnings;
create policy earnings_owner on public.earnings
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);


-- ── 3. updated_at trigger ─────────────────────────────────────────────────
drop trigger if exists earnings_set_updated_at on public.earnings;
create trigger earnings_set_updated_at
  before update on public.earnings
  for each row execute function public.set_updated_at();
