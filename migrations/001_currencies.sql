-- ══════════════════════════════════════════════════════════════════════════
-- Currencies
-- Run once in the Supabase SQL editor. Idempotent — safe to re-run.
--
-- Global reference data, not user data: there is no user_id column and every
-- authenticated user reads the same rows. MXN is the base currency, so every
-- rate is expressed relative to it and MXN itself is always exactly 1.
-- Transactions store amount_mxn using the rate at the time of writing, so a
-- later rate change never rewrites history.
-- ══════════════════════════════════════════════════════════════════════════


-- ── 1. Table ──────────────────────────────────────────────────────────────
create table if not exists public.currencies (
  id uuid primary key default gen_random_uuid(),

  -- ISO 4217. Unique because the service layer looks currencies up by code
  -- with .single(), which errors if the code matches more than one row.
  code   varchar(3) not null unique,
  name   text not null,
  symbol text not null,

  -- Relative to MXN. Six decimals because minor currencies need the
  -- precision; money columns elsewhere stay at numeric(12,2).
  exchange_rate numeric(14,6) not null default 1 check (exchange_rate > 0),

  -- Null until a rate has actually been fetched from the rates API.
  rate_updated_at timestamptz,

  created_at timestamptz not null default now()
);

create index if not exists currencies_code_idx on public.currencies(code);


-- ── 2. Base currency ──────────────────────────────────────────────────────
-- MXN has to exist for amount_mxn to mean anything. Inserted here rather
-- than seeded by the app so a fresh database is usable immediately.
insert into public.currencies (code, name, symbol, exchange_rate)
values ('MXN', 'Mexican Peso', '$', 1)
on conflict (code) do nothing;


-- ── 3. Row level security ─────────────────────────────────────────────────
-- This table cannot use the auth.uid() = user_id policy the user-owned
-- tables use, because it has no user_id. Reads are open to any authenticated
-- user; writes are left to the service role, which bypasses RLS, so only the
-- rate refresh job can change rates.
alter table public.currencies enable row level security;

drop policy if exists currencies_read on public.currencies;
create policy currencies_read on public.currencies
  for select to authenticated using (true);
