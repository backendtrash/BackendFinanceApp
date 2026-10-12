# Defects

Everything found while working through section 3 of the status report.
Ten in total: five fixed, five recorded and deliberately not fixed because
they fall outside the scope of this phase.

Nothing here was found by reading code looking for trouble. Each one
surfaced because something was being tested or migrated and the behaviour
did not match what the design said.

---

## Fixed

### 1. A malformed token returned 500 on every protected endpoint

**Severity:** high — unauthenticated, affects the whole API
**Found by:** `tests/test_auth_tokens.py`, writing the garbage-token case
**Fixed in:** 3.5

`app/auth/dependencies.py` read the JWT header to decide which algorithm to
verify with, and that call sat one line *above* the `try` block. A token
that was not three base64 segments raised `JWTError` there, outside the
handler, and escaped as an unhandled exception.

Any caller, with no credentials at all, could produce a server error on all
74 protected endpoints by sending `Authorization: Bearer x`. The frontend
never saw the 401 its refresh logic waits for, and each one was logged as a
server fault rather than a rejected request.

The header read is inside the `try` now. Regression test:
`test_a_malformed_token_is_401_not_500`.

### 2. Algorithm confusion in JWT verification

**Severity:** high
**Found by:** tracing whether `SUPABASE_JWT_SECRET` was still used (3.5)
**Fixed in:** 3.5

`decode_jwt` chose between ES256 and HS256 by reading `alg` out of the
token's own unverified header, then verified with the key that matched that
choice. The caller therefore influenced how their own token was checked,
which is the shape of an algorithm-confusion attack and defeats the purpose
of verification.

The HS256 branch is gone; verification is `algorithms=["ES256"]` against
the published JWKS, which is what the H2 design specifies. That also made
`SUPABASE_JWT_SECRET` genuinely unused, so it was removed.

### 3. Recurring rules could duplicate transactions

**Severity:** high — writes incorrect financial records
**Found by:** reviewing RF07 against the design (3.3)
**Fixed in:** 3.3

Two independent problems in `process_due_rules`:

The engine inserted the transaction and then advanced `next_due_date`, with
one broad `except` around both. Anything failing in between — a dropped
connection, a restart, a Supabase 5xx — left the transaction committed and
the cursor unmoved, so the next run wrote it again.

And `calculate_next_due_date` advances one interval per call, so a rule five
weeks overdue stayed overdue after processing. Calling `POST /process`
repeatedly in one day kept producing transactions on different dates.

Now the occurrence is claimed first, with an update conditional on
`next_due_date` still holding the value that run read, and the transaction
is only written if the claim matched a row. The backlog drains in one pass.
Migration `012` adds a unique partial index on `(recurring_rule_id, date)`
as the backstop.

### 4. `POST /process` ran across every user's rules

**Severity:** medium
**Found by:** reviewing RF07 (3.3)
**Fixed in:** 3.3

The endpoint was authenticated, but `process_due_rules()` iterated the whole
table. Any authenticated user could drive every other user's scheduling, on
demand and repeatedly — which was the multiplier on defect 3. No rows
leaked, so it was easy to read as harmless.

Now scoped to the caller. The nightly scheduler keeps the global path.

### 5. Deleting a category silently rewrote history

**Severity:** medium — unrecoverable data corruption
**Found by:** reviewing RF04 (3.3)
**Fixed in:** 3.3

Deletion had no referential check, relying on `ON DELETE SET NULL`. The
database accepted it and quietly changed the meaning of existing records:
past transactions became "Uncategorized", a category-scoped budget became a
budget over *all* categories, a recurring rule kept firing uncategorised,
and a goal lost the category its contributions are counted through.

None of it recoverable through the API, because the old `category_id` was
gone. Now returns **409** with per-table counts.

---

## Recorded, not fixed

### 6. The backend bypasses row level security entirely

**Severity:** high in principle, latent in practice
**Why not fixed:** architectural; changing it touches every service

Every module imports `supabase_admin` from `app/database.py` — the service
role client, which bypasses RLS. The docstring on that client says "NEVER
expose this client to user-facing endpoints directly", and all eleven
modules do exactly that.

So the policies written in `migrations/` are never exercised by the API.
Isolation rests entirely on `.eq("user_id", ...)` being present and correct
in every query. It appears to be, but it is a convention rather than a
guarantee: one missed filter is a cross-tenant leak with nothing underneath
to catch it.

Three places where the filter is already absent or partial:

- `app/goals/service.py:360` — `categories.delete().eq("id", ...)` with no
  `user_id` guard, unlike the equivalent at `:663`
- `app/analytics/service.py` — several reads rely on the caller passing the
  right `user_id`, with no defence if it is ever wrong

Proper fix: use the anon client with the user's own JWT for user-facing
requests, so the policies apply, and keep the service role for background
jobs. Until then, `tests/test_isolation.py` is the only check.

### 7-10. Analytics calculations

All four are pinned as `xfail(strict=True)` in
`tests/test_analytics_calcs.py`, so each will turn into a failing test the
moment it is fixed. Not corrected here because they change numbers users
already see, and the right values are a product decision rather than an
obvious bug fix.

**7. Net worth discards the history it fetched.**
`get_net_worth_history` queries with no lower bound — every row the user has
ever written — then buckets only the months inside the requested window and
throws the rest away. The running total starts from zero, so "net worth"
is really "net change over the window". Someone with years of savings and a
flat month sees 0. It also pays the full cost of reading that history to
discard it.

**8. Trend averages count months that did not exist.**
`get_spending_trends` builds its average with `monthly.get(m, 0)` across the
whole window, so a category created last month is averaged over five months
of zeros. The average lands at a fifth of the truth and `pct_vs_avg` is
inflated to match — which is what drives the up/down arrow on the dashboard.

**9. Projected variance compares different spans.**
`get_projected_analytics` accumulates `total_projected` over past *and*
future months but `total_real` over past months only, then reports
`total_real - total_projected`. With the defaults that is three months of
real spending minus six months of projection. The number does not describe
anything.

**10. The weekly view disagrees with the monthly rollup.**
A weekly projected cost with no `day_of_week` is added in full to every week
bucket, so a 500/week cost shows 2500 in a five-week month. The monthly
figure for the same cost is 500 × 4.333 = 2166.67. The same response
contains both.

---

## Smaller things, noted in passing

- `app/currencies/service.py:183` writes the literal string `"now()"` into
  `rate_updated_at`. Postgres accepts `'now'` as special timestamp input but
  not `'now()'`, so that update likely errors or the column never advances.
- `migrations/001_sinking_funds.sql` (now on `feat/sinking-funds`) guarded
  its `updated_at` triggers on `set_updated_at()` already existing, and
  never created it. Where it did not exist the triggers were silently
  skipped. `000_extensions_enums_helpers.sql` creates it unconditionally.
- `get_month_range`'s docstring says `months_back=3` returns four tuples and
  shows four. The loop returns three. Pinned by
  `test_month_range_docstring_example_is_wrong`.
- `app/auth/router.py:4` imports `limiter` from `app.main` while `main.py`
  imports the router back. It only works because the router imports sit at
  the bottom of `main.py`. Moving them up breaks startup.
- `budget_alerts` deduplicates in Python before inserting. Migration `008`
  adds a unique constraint on `(budget_id, triggered_date)` so a concurrent
  scheduler run and manual check cannot both write a row.
