-- ══════════════════════════════════════════════════════════════════════════
-- User preferences
-- Run once in the Supabase SQL editor. Idempotent — safe to re-run.
--
-- Exactly one row per user, created on first read if absent.
--
-- week_start_day is why this table exists. The week columns on expenses and
-- earnings are generated with the ISO week, which always starts Monday,
-- because a generated expression has to be immutable and cannot read a
-- preference. The user's own week start is therefore applied in Python when
-- building week buckets for the dashboard.
-- ══════════════════════════════════════════════════════════════════════════


-- ── 1. Table ──────────────────────────────────────────────────────────────
create table if not exists public.user_preferences (
  id uuid primary key default gen_random_uuid(),

  -- unique is load bearing, not decorative: the service layer writes with
  -- .upsert(payload, on_conflict="user_id"), which Postgres rejects unless
  -- a unique constraint exists on that column.
  user_id uuid not null unique references auth.users(id) on delete cascade,

  -- 0=Sunday, 1=Monday .. 6=Saturday. Defaults to Monday, matching the ISO
  -- week the generated columns use.
  week_start_day smallint not null default 1
    check (week_start_day between 0 and 6),

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);


-- ── 2. Row level security ─────────────────────────────────────────────────
alter table public.user_preferences enable row level security;
drop policy if exists user_preferences_owner on public.user_preferences;
create policy user_preferences_owner on public.user_preferences
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);


-- ── 3. updated_at trigger ─────────────────────────────────────────────────
drop trigger if exists user_preferences_set_updated_at on public.user_preferences;
create trigger user_preferences_set_updated_at
  before update on public.user_preferences
  for each row execute function public.set_updated_at();
