-- ══════════════════════════════════════════════════════════════════════════
-- Extensions, enums and shared helpers
-- Run once in the Supabase SQL editor, before every other migration.
-- Idempotent — safe to re-run.
--
-- Everything here is depended on by more than one table, so it has to exist
-- before 001. The enums are not a new invention: the Pydantic layer already
-- documents them as mirrors of Postgres enums, in categories/schemas.py,
-- budgets/schemas.py and recurring/schemas.py.
-- ══════════════════════════════════════════════════════════════════════════


-- ── 1. Extensions ─────────────────────────────────────────────────────────
-- gen_random_uuid() is the default for every primary key in this schema.
create extension if not exists pgcrypto;


-- ── 2. Enums ──────────────────────────────────────────────────────────────
-- create type has no "if not exists", so each one is guarded.

do $$
begin
  if not exists (select 1 from pg_type where typname = 'transaction_type') then
    create type public.transaction_type as enum ('expense', 'income');
  end if;
end $$;

do $$
begin
  if not exists (select 1 from pg_type where typname = 'frequency_type') then
    create type public.frequency_type as enum ('weekly', 'monthly');
  end if;
end $$;

do $$
begin
  if not exists (select 1 from pg_type where typname = 'budget_period') then
    create type public.budget_period as enum ('weekly', 'monthly');
  end if;
end $$;


-- ── 3. updated_at trigger function ────────────────────────────────────────
-- Created unconditionally and first, on purpose.
--
-- The earlier sinking funds migration wrapped its triggers in
--   if exists (select 1 from pg_proc where proname = 'set_updated_at')
-- and never created the function. On a database where it did not already
-- exist that check silently failed and those triggers were never created —
-- no error, just columns that quietly stopped updating. Defining the function
-- here, before anything references it, removes that failure mode.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;
