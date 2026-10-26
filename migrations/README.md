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
| `012_recurring_idempotency.sql` | one transaction per recurring rule per day (unique index) |
| `013_analytics_aggregates.sql` | `net_balance_before`, `category_first_expense` (analytics, defects 7 and 8) |

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

**The backend exercises these policies** since 18/10 (defect 6). Each
request gets a Supabase client carrying the user's own token, so every
query — the RPC functions included, which are `security invoker` — runs
under the user's policies, on top of the `.eq("user_id", ...)` filter each
service still writes. Only the scheduler and account deletion use the
service role, which bypasses RLS.

Policies are verified the only way that counts: the API, tested with two
real accounts, in `tests/test_isolation.py`.

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

## Executed

On 18/10/2026 files 000 to 012 ran start to finish, in order, on a fresh
Supabase project, which is now the project's production database. Every
later file runs there before the pull request that needs it is merged.
`.github/workflows/schema-check.yml` compares production with this folder
on every change to it and fails if they differ. Checked
afterwards in the SQL editor:

```sql
select tablename, rowsecurity from pg_tables where schemaname = 'public';
--> 10 rows, all true

select count(*) from pg_policies where schemaname = 'public';
--> 13
```

They were reconstructed from the insert payloads and the Pydantic
validators, because the proof-of-concept database had been built by hand.
That earlier database is not used by this repository and was not migrated.
