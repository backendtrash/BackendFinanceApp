-- ══════════════════════════════════════════════════════════════════════════
-- Budget alerts
-- Run once in the Supabase SQL editor. Idempotent — safe to re-run.
--
-- An append-only record of the moments a budget crossed its threshold. Rows
-- are snapshots, not live values: amount_spent and limit_amount are copied
-- in at trigger time so the history still reads correctly after the budget
-- is edited or the underlying expenses change.
-- ══════════════════════════════════════════════════════════════════════════


-- ── 1. Table ──────────────────────────────────────────────────────────────
create table if not exists public.budget_alerts (
  id uuid primary key default gen_random_uuid(),

  -- cascade, unlike most FKs here: an alert has no meaning once the budget
  -- it describes is gone, and it is not financial history worth preserving.
  budget_id uuid not null references public.budgets(id) on delete cascade,
  user_id   uuid not null references auth.users(id)     on delete cascade,

  -- Can exceed 100 — spending past the limit is exactly what this records.
  -- The service layer caps the stored value at 999.99, hence numeric(7,2)
  -- and deliberately no upper bound check.
  pct_spent    numeric(7,2)  not null check (pct_spent >= 0),
  amount_spent numeric(12,2) not null,
  limit_amount numeric(12,2) not null,

  triggered_date date        not null default current_date,
  triggered_at   timestamptz not null default now(),

  -- One alert per budget per day. The service layer already dedupes in
  -- Python before inserting; this makes that guarantee the database's, so a
  -- concurrent scheduler run and manual check cannot both write a row.
  constraint budget_alerts_one_per_day unique (budget_id, triggered_date)
);

create index if not exists budget_alerts_user_triggered_idx
  on public.budget_alerts(user_id, triggered_at desc);


-- ── 2. Row level security ─────────────────────────────────────────────────
alter table public.budget_alerts enable row level security;
drop policy if exists budget_alerts_owner on public.budget_alerts;
create policy budget_alerts_owner on public.budget_alerts
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
