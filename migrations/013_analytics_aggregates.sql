-- ══════════════════════════════════════════════════════════════════════════
-- Aggregates for the analytics (defects 7 and 8)
-- Run once in the Supabase SQL editor, after 005 and 006.
-- Idempotent — create or replace throughout.
--
-- Both answers are a sum or a minimum over a user's whole history. Reading
-- every row into Python to compute them would grow with the account's age,
-- and PostgREST's own aggregates are disabled on Supabase by default, so
-- they are computed here and called over RPC.
--
-- security invoker: they run as the calling user, so row level security
-- applies on top of the user_id filter. Called with another user's id, they
-- see no rows.
--
-- Both return a table, not a bare value. postgrest-py validates a response's
-- data as a list, and a function returning a scalar would fail that check.
-- ══════════════════════════════════════════════════════════════════════════


-- ── 1. Balance before a date (defect 7) ───────────────────────────────────
-- Income minus expenses, in MXN, strictly before p_before. The net worth
-- history starts its running total here instead of at zero.
create or replace function public.net_balance_before(
  p_user_id uuid,
  p_before  date
)
returns table (balance numeric)
language sql
stable
security invoker
set search_path = public, pg_temp
as $$
  select coalesce((select sum(e.amount_mxn)
                     from public.earnings e
                    where e.user_id = p_user_id
                      and e."date" < p_before), 0)
       - coalesce((select sum(x.amount_mxn)
                     from public.expenses x
                    where x.user_id = p_user_id
                      and x."date" < p_before), 0);
$$;


-- ── 2. First expense per category (defect 8) ──────────────────────────────
-- One row per category the user has spent in, with the date of the first
-- expense. Expenses with no category come back as one row with a null
-- category_id. Spending trends average each category from its first month.
create or replace function public.category_first_expense(
  p_user_id uuid
)
returns table (category_id uuid, first_date date)
language sql
stable
security invoker
set search_path = public, pg_temp
as $$
  select x.category_id, min(x."date")
    from public.expenses x
   where x.user_id = p_user_id
   group by x.category_id;
$$;
