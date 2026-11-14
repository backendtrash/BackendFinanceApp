-- ══════════════════════════════════════════════════════════════════════════
-- Foreign currencies in the catalog (defect 36)
-- Run once in the Supabase SQL editor. Idempotent — existing codes are left
-- untouched.
--
-- 001 created only MXN, and the daily rate job updates the currencies that
-- exist without ever adding one, so production had no currency but the
-- peso. RF05 asks for a catalog of currencies with their rate to MXN, and
-- test case CP-03 records an expense in dollars.
--
-- The rates below are provisional placeholders so the column's check
-- (exchange_rate > 0) holds; rate_updated_at stays null, which is how the
-- table marks a rate never fetched. The daily job at 06:00 UTC, or
-- POST /api/v1/currencies/update-rates by an administrator, replaces them
-- with the API's — both need EXCHANGE_RATE_API_KEY set on the server.
-- Do not record movements in these currencies until rate_updated_at is set.
-- ══════════════════════════════════════════════════════════════════════════

insert into public.currencies (code, name, symbol, exchange_rate)
values
  ('USD', 'US Dollar', 'US$', 18.5),
  ('EUR', 'Euro',      '€',   20.0)
on conflict (code) do nothing;
