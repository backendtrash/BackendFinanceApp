-- ══════════════════════════════════════════════════════════════════════════
-- One transaction per rule per day
-- Run once in the Supabase SQL editor, after 005 and 006.
-- Idempotent — safe to re-run.
--
-- The application now claims an occurrence before writing it, by advancing
-- next_due_date with a conditional update and only inserting if that update
-- matched a row. That closes the race in normal operation.
--
-- This index is the backstop underneath it. Application-level guards hold
-- only while every writer goes through the application; a manual insert, a
-- restored backup, a future second worker or a bug in the claim logic would
-- all slip past. Duplicated money is the one error here that is both easy to
-- cause and hard to notice, because the row looks exactly like a real one.
--
-- Partial, so hand-entered transactions are unaffected: they have a null
-- recurring_rule_id and never collide with each other.
-- ══════════════════════════════════════════════════════════════════════════


-- ── 1. Clean up any duplicates already written ────────────────────────────
-- The index cannot be created while duplicates exist. These rows were
-- produced by the old insert-then-advance order; keep the earliest of each
-- group, which is the one any later edit would have been applied to.
--
-- Review the rows this would remove before running it:
--
--   select recurring_rule_id, "date", count(*)
--     from public.expenses
--    where recurring_rule_id is not null
--    group by 1, 2 having count(*) > 1;

delete from public.expenses e
 where e.recurring_rule_id is not null
   and e.id <> (
     select keep.id
       from public.expenses keep
      where keep.recurring_rule_id = e.recurring_rule_id
        and keep."date"            = e."date"
      order by keep.created_at, keep.id
      limit 1
   );

delete from public.earnings e
 where e.recurring_rule_id is not null
   and e.id <> (
     select keep.id
       from public.earnings keep
      where keep.recurring_rule_id = e.recurring_rule_id
        and keep."date"            = e."date"
      order by keep.created_at, keep.id
      limit 1
   );


-- ── 2. The constraint ─────────────────────────────────────────────────────
create unique index if not exists expenses_one_per_rule_per_day_idx
  on public.expenses(recurring_rule_id, "date")
  where recurring_rule_id is not null;

create unique index if not exists earnings_one_per_rule_per_day_idx
  on public.earnings(recurring_rule_id, "date")
  where recurring_rule_id is not null;
