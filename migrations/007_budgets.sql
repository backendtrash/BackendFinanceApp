-- ══════════════════════════════════════════════════════════════════════════
-- Budgets
-- Run once in the Supabase SQL editor. Idempotent — safe to re-run.
--
-- A budget is a limit plus a window. Nothing about what has been spent is
-- stored here: spent_amount, pct_spent and remaining are recomputed on every
-- read by the service layer, so a budget can never go stale against the
-- transactions it measures.
--
-- category_id is nullable and that distinction is load bearing:
--   set  -> the budget tracks one category
--   null -> the budget tracks everything the user spends
-- ══════════════════════════════════════════════════════════════════════════


-- ── 1. Table ──────────────────────────────────────────────────────────────
create table if not exists public.budgets (
  id      uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,

  -- Null means a global budget across all categories. Note the consequence:
  -- if a category is deleted and this were set null by the FK, the budget
  -- would silently change meaning from one category to everything. That is
  -- why migration 012 and the API both refuse to delete a referenced
  -- category rather than letting the FK quietly rewrite the budget.
  category_id uuid references public.categories(id) on delete set null,

  limit_amount numeric(12,2) not null check (limit_amount > 0),
  currency_id  uuid not null references public.currencies(id),

  period public.budget_period not null default 'monthly',

  -- Percentage of the limit at which an alert fires. 1-100 mirrors the
  -- validator in budgets/schemas.py.
  alert_threshold smallint not null default 80
    check (alert_threshold between 1 and 100),

  is_active  boolean     not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists budgets_user_active_idx
  on public.budgets(user_id, is_active);
create index if not exists budgets_user_category_idx
  on public.budgets(user_id, category_id);


-- ── 2. Row level security ─────────────────────────────────────────────────
alter table public.budgets enable row level security;
drop policy if exists budgets_owner on public.budgets;
create policy budgets_owner on public.budgets
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);


-- ── 3. updated_at trigger ─────────────────────────────────────────────────
drop trigger if exists budgets_set_updated_at on public.budgets;
create trigger budgets_set_updated_at
  before update on public.budgets
  for each row execute function public.set_updated_at();
