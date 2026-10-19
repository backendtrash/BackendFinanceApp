# Defects

| # | Defecto | Severidad | Encontrado | Cerrado | Estado | Commit |
|---|---|---|---|---|---|---|
| 1 | Token malformado devolvía 500 | Alta | 11/10/2026 | 11/10/2026 | Corregido | 2a8b06d |
| 2 | Confusión de algoritmo en JWT | Alta | 11/10/2026 | 11/10/2026 | Corregido | 2a8b06d |
| 3 | Recurrentes duplicaban movimientos | Alta | 11/10/2026 | 11/10/2026 | Corregido | bb9b2c8 |
| 4 | POST /process recorría todos los usuarios | Media | 11/10/2026 | 11/10/2026 | Corregido | bb9b2c8 |
| 5 | Borrar categoría reescribía historial | Media | 11/10/2026 | 11/10/2026 | Corregido | bb9b2c8 |
| 6 | API no aplica políticas por fila | Alta | 11/10/2026 | 18/10/2026 | Corregido, sin desplegar | 9311557 |
| 7–10 | Cálculos de analítica | Media | 11/10/2026 | | Abierto (xfail) | |
| 11 | Tasa de cambio guardaba `"now()"` como fecha | Alta | 11/10/2026 | 18/10/2026 | Corregido | 725600c |
| 12 | Front: recargar cerraba la sesión en desarrollo | Media | 18/10/2026 | 18/10/2026 | Corregido | front 82571c6 |
| 13 | Front: el 409 de categorías no mostraba el motivo | Baja | 18/10/2026 | 18/10/2026 | Corregido | front e6c88aa |
| 14 | Front: Vista semanal llamaba a un módulo retirado (404) | Baja | 18/10/2026 | 18/10/2026 | Corregido | front bf537dc |
| 15 | Front: "Eliminar cuenta" llama a un endpoint inexistente | Media | 18/10/2026 | | Abierto | |
| 16 | Cualquier usuario puede refrescar las tasas de cambio | Baja | 11/10/2026 | | Abierto | |

Commits marked *front* are in
[`backendtrash/FrontendFinanceApp`](https://github.com/backendtrash/FrontendFinanceApp);
the rest are in this repository.

**Hashes assume merge commits.** Merging a PR with *Squash* or *Rebase*
rewrites its commits and these hashes stop resolving. Merge with
*Create a merge commit*.

**Defect 6 is fixed in code but not deployed.** The fix makes the API apply
the row level security policies — which means it now depends on them being
right in the live Supabase project, and the migrations in `migrations/` have
never been run there. PR #2 stays unmerged until those policies are checked;
Railway deploys every push to `main`.

Nothing here was found by reading code looking for trouble. Each defect
surfaced because something was being tested, migrated or wired up, and the
behaviour did not match the design.

---

## Fixed

### 1. A malformed token returned 500 on every protected endpoint

**Severity:** high — unauthenticated, affects the whole API
**Found by:** `tests/test_auth_tokens.py`, writing the garbage-token case

`app/auth/dependencies.py` read the JWT header to decide which algorithm to
verify with, and that call sat one line *above* the `try` block. A token
that was not three base64 segments raised `JWTError` there, outside the
handler, and escaped as an unhandled exception.

Any caller, with no credentials at all, could produce a server error on all
74 protected endpoints by sending `Authorization: Bearer x`. The frontend
never saw the 401 its refresh logic waits for.

The header read is inside the `try` now. Regression test:
`test_a_malformed_token_is_401_not_500`.

### 2. Algorithm confusion in JWT verification

**Severity:** high
**Found by:** tracing whether `SUPABASE_JWT_SECRET` was still used

`decode_jwt` chose between ES256 and HS256 by reading `alg` out of the
token's own unverified header, then verified with the key that matched that
choice. The caller therefore influenced how their own token was checked.

The HS256 branch is gone; verification is `algorithms=["ES256"]` against the
published JWKS, which is what the H2 design specifies. That also made
`SUPABASE_JWT_SECRET` genuinely unused, so it was removed.

### 3. Recurring rules could duplicate transactions

**Severity:** high — writes incorrect financial records

The engine inserted the transaction and then advanced `next_due_date`, with
one broad `except` around both; anything failing in between left the
transaction committed and the cursor unmoved. And the cursor advanced one
interval per call, so a rule five weeks overdue kept producing transactions
on repeated calls.

The occurrence is now claimed first, with an update conditional on
`next_due_date` still holding the value that run read, and the transaction
is only written if the claim matched a row. The backlog drains in one pass.
Migration `012` adds a unique index on `(recurring_rule_id, date)`.

### 4. `POST /process` ran across every user's rules

**Severity:** medium

The endpoint was authenticated, but `process_due_rules()` iterated the whole
table, letting any user drive everyone's scheduling on demand — the
multiplier on defect 3. Now scoped to the caller; the nightly job keeps the
global path.

### 5. Deleting a category silently rewrote history

**Severity:** medium — unrecoverable data corruption

Deletion had no referential check and relied on `ON DELETE SET NULL`, which
quietly reclassified past transactions, turned a category budget into a
budget over everything and reset goal progress. Now returns **409** with
per-table counts.

### 6. The API did not apply the row level security policies

**Severity:** high
**Found:** 11/10 · **Fixed:** 18/10, commits `f7041d0`, `9311557`, `76f3aa6`
**Not deployed:** see the note at the top

Every module imported `supabase_admin`, the service role client, which
bypasses RLS. The policies written in `migrations/` were never exercised,
and isolation rested entirely on `.eq("user_id", ...)` being present in
every query — a convention, not a guarantee.

Each request now gets a client built with the anon key and **the user's own
JWT**, so PostgREST runs the query as that user and the policies apply.
`get_current_user` creates it once the token is verified and binds it in a
`ContextVar`; services read it through `db()`. `db()` fails closed: with
nothing bound it raises instead of falling back to the admin client.

`supabase_admin` is left only in `app/database.py`, which creates it, and
`app/scheduler.py`, which runs the background jobs as the system with
`using_db(supabase_admin)`. The `user_id` filters stay as a second layer.

`tests/test_db_boundary.py` fails if any other module mentions
`supabase_admin`, naming the file and line. It was checked by putting the
import back into `goals/service.py`, which the test caught, then reverting.

Fixed alongside it: the rollback that deletes an auto-created savings
category in `goals/service.py` had no `user_id` filter, unlike the delete
next to it.

### 11. Exchange rate refresh wrote `"now()"` as a timestamp

**Severity:** high
**Found:** 11/10, listed under *smaller things* below until today
**Fixed:** 18/10, commit `725600c`

`update_exchange_rates` set `rate_updated_at` to the string `"now()"`. That
is SQL, not a value. PostgREST passes it to Postgres as a string, and
`'now()'` is not valid timestamp input — the special value is `'now'`,
without parentheses. So the update failed on the first non-MXN currency and
the refresh never completed: rates stayed as seeded, and every conversion
used them.

Now writes `datetime.now(timezone.utc).isoformat()`. `tests/test_currencies.py`
fails against the old code and passes against the new.

Rated high rather than medium because it breaks RF05 silently: nothing in
the app says the rates are stale.

### 12. Frontend: reloading a protected screen logged the user out

**Severity:** medium · **Repo:** frontend
**Found and fixed:** 18/10, commit `82571c6`

`useAuth` restored the session against
`` `${import.meta.env.VITE_API_BASE_URL}/api/v1/auth/refresh` ``. That
variable is only set for production builds, so in development the URL was
the literal string `undefined/api/v1/auth/refresh`, the request failed, and
the session was cleared. `client.ts` had fixed the same bug in its own
refresh path; `useAuth` now uses the same base URL.

### 13. Frontend: the 409 for a category in use showed no reason

**Severity:** low · **Repo:** frontend
**Found and fixed:** 18/10, commit `e6c88aa`

Defect 5's fix answers with a structured 409 — the reason in `message`,
counts per table in `references`. The frontend's error helper only
understood `detail` as a string or an array, so it showed axios's own
"Request failed with status code 409". It now shows the reason and the
counts.

### 14. Frontend: Week View called a module the backend no longer serves

**Severity:** low · **Repo:** frontend
**Found and fixed:** 18/10, commit `bf537dc`

The sinking funds module left the backend's `main` on 11/10, out of the H2
scope. The frontend still linked to it and Week View — one of the design's
eleven screens — requested it on every visit, getting a 404. Its route and
menu entries are gone and its query is disabled; the code stays on
`feat/sinking-funds`.

---

## Open

### 7–10. Analytics calculations

**Waiting on:** the coach's decision (`docs/decisiones/`). Until it exists,
the four `xfail(strict=True)` tests in `tests/test_analytics_calcs.py` stay
as they are.

**7. Net worth discards the history it fetched.** `get_net_worth_history`
queries every row with no lower bound, then keeps only the months inside the
window and starts the running total at zero. Someone with years of savings
and a flat month sees 0.

**8. Trend averages count months that did not exist.**
`get_spending_trends` averages with `monthly.get(m, 0)`, so a category
created last month is averaged over months of zeros, deflating the average
and inflating `pct_vs_avg`.

**9. Projected variance compares different spans.** `total_projected`
accumulates past and future months, `total_real` only past ones, and the
response reports the difference.

**10. The weekly view disagrees with the monthly rollup.** A weekly
projected cost with no `day_of_week` is added in full to every week bucket,
so a 500/week cost shows 2500 in a five-week month against 2166.67 monthly.

### 15. Frontend: "Delete account" calls an endpoint that does not exist

**Severity:** medium · **Repo:** frontend and backend
**Found:** 18/10

Settings → Delete account calls `DELETE /api/v1/auth/account`. The backend
has no such route, so the button fails. Not fixed today because the fix is
backend work with a design question in it: deleting a user from Supabase
Auth needs the service role, which now belongs only to the system context,
so the endpoint has to be designed rather than wired up.

### 16. Any authenticated user can trigger an exchange rate refresh

**Severity:** low
**Found:** 11/10, during the exploration for defect 6; recorded 18/10

`POST /currencies/update-rates` is open to every authenticated user and
writes the shared `currencies` table as the system. Fixing defect 6 kept
that behaviour exactly — it now goes through `scheduler.refresh_exchange_rates()`
— but did not decide who should be allowed to do it. Candidates: an admin
role check, or moving the refresh to a scheduled job and removing the
endpoint.

---

## Smaller things, noted in passing

- `migrations/001_sinking_funds.sql` (now on `feat/sinking-funds`) guarded
  its `updated_at` triggers on `set_updated_at()` already existing and never
  created it. `000_extensions_enums_helpers.sql` creates it unconditionally.
- `get_month_range`'s docstring says `months_back=3` returns four tuples.
  The loop returns three. Pinned by `test_month_range_docstring_example_is_wrong`.
- `app/auth/router.py:4` imports `limiter` from `app.main` while `main.py`
  imports the router back. It only works because the router imports sit at
  the bottom of `main.py`.
- The frontend's `pnpm lint` reports 168 problems (148 errors, 20 warnings),
  almost all `no-explicit-any`. All of them predate this week: the count is
  identical on the import commit. Not a defect in behaviour, but it means
  the linter cannot gate a pull request until they are cleared.
