-- ══════════════════════════════════════════════════════════════════════════
-- Categories
-- Run once in the Supabase SQL editor. Idempotent — safe to re-run.
--
-- One table holds two kinds of row:
--   user_id is null -> a system category, shared by everyone, read only
--   user_id is set  -> a category that user created
--
-- The service layer reads both at once with
--   .or_("user_id.is.null,user_id.eq.<uid>")
-- and writes is_system into the response in Python. is_system is therefore
-- NOT a column here, even though it appears on CategoryResponse.
-- ══════════════════════════════════════════════════════════════════════════


-- ── 1. Table ──────────────────────────────────────────────────────────────
create table if not exists public.categories (
  id uuid primary key default gen_random_uuid(),

  -- Nullable, and that is the whole design: null marks a system category.
  -- Every write path filters on .eq("user_id", uid), which can never match
  -- null, so system rows are unreachable for update and delete through the
  -- API without needing a separate flag.
  user_id uuid references auth.users(id) on delete cascade,

  -- Lengths mirror the Pydantic validators in categories/schemas.py exactly.
  name  varchar(50) not null check (length(btrim(name)) between 1 and 50),
  color varchar(7)  not null default '#6366F1' check (color ~ '^#[0-9A-F]{6}$'),
  icon  varchar(50) not null default 'tag' check (length(btrim(icon)) between 1 and 50),

  type public.transaction_type not null default 'expense',

  created_at timestamptz not null default now()
);

create index if not exists categories_user_type_idx
  on public.categories(user_id, type);

-- Partial index: system categories are read on every category request.
create index if not exists categories_system_idx
  on public.categories(type) where user_id is null;


-- ── 2. Row level security ─────────────────────────────────────────────────
-- This table cannot use the single "for all" owner policy the other tables
-- use. auth.uid() = user_id is false for every system category, so that
-- policy would hide the shared rows from everyone. Reads therefore have to
-- allow null, while writes stay strictly owner-only.
alter table public.categories enable row level security;

drop policy if exists categories_read on public.categories;
create policy categories_read on public.categories
  for select to authenticated
  using (user_id is null or auth.uid() = user_id);

drop policy if exists categories_insert on public.categories;
create policy categories_insert on public.categories
  for insert to authenticated
  with check (auth.uid() = user_id);

drop policy if exists categories_update on public.categories;
create policy categories_update on public.categories
  for update to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists categories_delete on public.categories;
create policy categories_delete on public.categories
  for delete to authenticated
  using (auth.uid() = user_id);
