# Migrations

Versioned SQL for the ten tables of the design approved at H2, plus the
database functions the API calls over RPC.

Run them **in filename order**, once each, in the Supabase SQL editor. Every
file is idempotent — `create ... if not exists`, `drop policy if exists`
before `create policy`, `create or replace` for functions — so re-running one
is safe and changes nothing.

| File | Creates |
|---|---|
| `000_extensions_enums_helpers.sql` | `pgcrypto`, the three enums, `set_updated_at()` |
| `001_currencies.sql` | `currencies` + the MXN base row |
| `002_categories.sql` | `categories` |
| `003_recurring_rules.sql` | `recurring_rules` |
| `004_projected_costs.sql` | `projected_costs` |
| `005_expenses.sql` | `expenses` |
| `006_earnings.sql` | `earnings` |
| `007_budgets.sql` | `budgets` |
| `008_budget_alerts.sql` | `budget_alerts` |
| `009_goals.sql` | `goals` |
| `010_user_preferences.sql` | `user_preferences` |
| `011_rpc_functions.sql` | `update_expense_date`, `update_earning_date`, `split_expense` |

The order is a dependency order, not a preference. `currencies` and
`categories` come first because almost everything references them;
`budget_alerts` follows `budgets`; `expenses` and `earnings` follow
`recurring_rules` and `projected_costs`, which they link back to.

## Row level security, and an important caveat

Every table has RLS enabled and a policy. Three shapes are used:

- **Owner tables** — `expenses`, `earnings`, `recurring_rules`,
  `projected_costs`, `budgets`, `budget_alerts`, `goals`,
  `user_preferences`. One `for all` policy, `auth.uid() = user_id`.
- **`categories`** — cannot use that policy. System categories have
  `user_id is null`, and `auth.uid() = null` is never true, so a single
  owner policy would hide the shared categories from every user. Reads allow
  `user_id is null or auth.uid() = user_id`; writes stay owner-only, which
  needs the policy split per command.
- **`currencies`** — no `user_id` at all. Any authenticated user may read;
  writes are left to the service role.

**The backend does not exercise these policies.** Every module imports
`supabase_admin` from `app/database.py`, the service role client, which
bypasses RLS entirely. At runtime, tenant isolation rests on the
`.eq("user_id", ...)` filter written by hand in each service function.

The policies are still worth having — they are what protects the data if the
frontend ever queries Supabase directly with the anon key, and they are a
second line of defence if one of those hand-written filters is ever missed.
But they should not be read as "the backend is protected by RLS". Testing
isolation therefore means testing the API with two real accounts, which is
what `tests/test_isolation.py` does.

## Generated columns

`expenses.week_number`, `expenses.week_year` and their `earnings`
equivalents are `generated always as ... stored`, using the **ISO week**.

A generated expression must be immutable, so it cannot read the user's
`week_start_day` preference. The ISO week always starts on Monday; a user
who prefers another start day gets that applied in Python when the dashboard
builds its week buckets.

PostgREST cannot write a generated column, and it sends every column present
in a request body. That is why changing a transaction date goes through
`update_expense_date` / `update_earning_date` in `011` instead of a plain
`PATCH`.

## Not run yet

These files have been syntax-checked but **not executed** against a
database. The live Supabase project was provisioned by hand before the repo
existed, so its current shape was reconstructed from the insert payloads and
the Pydantic validators in each module, not read from the database.

Before trusting them against the existing project, diff them against what is
actually there. On a fresh project they can be run start to finish.
