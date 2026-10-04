-- ══════════════════════════════════════════════════════════════════════════
-- Savings goals
-- Run once in the Supabase SQL editor. Idempotent — safe to re-run.
--
-- Two kinds of goal share this table:
--   fixed_amount -> save target_amount by deadline
--   monthly_rate -> save target_rate_pct of income every month
--
-- Progress is never stored. Contributions are ordinary expenses filed under
-- savings_category_id, which is what makes a contribution reduce the net
-- balance and count toward the goal in the same movement. The service layer
-- sums those expenses on read.
--
-- initial_amount is the exception: money already saved before the goal
-- existed. It is held here precisely because it must NOT create an expense
-- and must not move the net balance.
-- ══════════════════════════════════════════════════════════════════════════


-- ── 1. Table ──────────────────────────────────────────────────────────────
create table if not exists public.goals (
  id      uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,

  name text not null check (length(btrim(name)) between 1 and 100),

  type text not null check (type in ('fixed_amount', 'monthly_rate')),

  -- Required for fixed_amount goals, meaningless for monthly_rate ones.
  target_amount numeric(12,2) check (target_amount is null or target_amount > 0),
  currency_id   uuid references public.currencies(id),
  deadline      date,

  -- Required for monthly_rate goals. 1-100 mirrors goals/schemas.py.
  target_rate_pct numeric(5,2)
    check (target_rate_pct is null or target_rate_pct between 1 and 100),

  notes text,

  -- The "<name>" expense category created with the goal. Contributions are
  -- found by this category, so set null on delete would orphan the progress
  -- calculation rather than destroy it — the goal survives at zero progress.
  savings_category_id uuid references public.categories(id) on delete set null,

  -- Money saved before the goal was created. Never backed by an expense.
  initial_amount numeric(12,2) not null default 0 check (initial_amount >= 0),

  is_active  boolean     not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  -- Each goal type needs its own fields present to be answerable.
  constraint goals_type_fields check (
       (type = 'fixed_amount' and target_amount   is not null)
    or (type = 'monthly_rate' and target_rate_pct is not null)
  )
);

create index if not exists goals_user_active_idx
  on public.goals(user_id, is_active);
create index if not exists goals_savings_category_idx
  on public.goals(savings_category_id) where savings_category_id is not null;


-- ── 2. Row level security ─────────────────────────────────────────────────
alter table public.goals enable row level security;
drop policy if exists goals_owner on public.goals;
create policy goals_owner on public.goals
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);


-- ── 3. updated_at trigger ─────────────────────────────────────────────────
drop trigger if exists goals_set_updated_at on public.goals;
create trigger goals_set_updated_at
  before update on public.goals
  for each row execute function public.set_updated_at();
