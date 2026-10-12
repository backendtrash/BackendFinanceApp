-- ══════════════════════════════════════════════════════════════════════════
-- Recurring rules
-- Run once in the Supabase SQL editor. Idempotent — safe to re-run.
--
-- A rule is a template. The scheduler reads every active rule whose
-- next_due_date has arrived, writes a real expense or earning from it, and
-- moves next_due_date forward. The generated row carries recurring_rule_id
-- back to its rule, which is what makes the idempotency index in migration
-- 012 possible.
-- ══════════════════════════════════════════════════════════════════════════


-- ── 1. Table ──────────────────────────────────────────────────────────────
create table if not exists public.recurring_rules (
  id      uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,

  type        public.transaction_type not null,
  amount      numeric(12,2) not null check (amount > 0),
  currency_id uuid not null references public.currencies(id),

  -- set null, not cascade: losing a category must never delete the rule.
  category_id uuid references public.categories(id) on delete set null,
  description text,

  frequency  public.frequency_type not null,
  start_date date not null default current_date,
  end_date   date,

  -- The cursor the scheduler reads. Always the date of the next transaction
  -- this rule should produce; advanced after each one is written.
  next_due_date date not null,

  -- 0=Mon .. 6=Sun, matching projected_costs.day_of_week.
  day_of_week  smallint check (day_of_week  between 0 and 6),
  day_of_month smallint check (day_of_month between 1 and 31),

  is_active  boolean     not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint recurring_rules_end_after_start check (
    end_date is null or end_date >= start_date
  )
);

create index if not exists recurring_rules_user_active_idx
  on public.recurring_rules(user_id, is_active);

-- The scheduler scans across all users on this predicate, so this index
-- serves the background job rather than any single request.
create index if not exists recurring_rules_due_idx
  on public.recurring_rules(next_due_date) where is_active;


-- ── 2. Row level security ─────────────────────────────────────────────────
alter table public.recurring_rules enable row level security;
drop policy if exists recurring_rules_owner on public.recurring_rules;
create policy recurring_rules_owner on public.recurring_rules
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);


-- ── 3. updated_at trigger ─────────────────────────────────────────────────
drop trigger if exists recurring_rules_set_updated_at on public.recurring_rules;
create trigger recurring_rules_set_updated_at
  before update on public.recurring_rules
  for each row execute function public.set_updated_at();
