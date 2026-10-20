# Defects

| # | Defecto | Severidad | Encontrado | Cerrado | Estado | Commit |
|---|---|---|---|---|---|---|
| 1 | Token malformado devolvía 500 | Alta | 11/10/2026 | 11/10/2026 | Corregido | 2a8b06d |
| 2 | Confusión de algoritmo en JWT | Alta | 11/10/2026 | 11/10/2026 | Corregido | 2a8b06d |
| 3 | Recurrentes duplicaban movimientos | Alta | 11/10/2026 | 11/10/2026 | Corregido | bb9b2c8 |
| 4 | POST /process recorría todos los usuarios | Media | 11/10/2026 | 11/10/2026 | Corregido | bb9b2c8 |
| 5 | Borrar categoría reescribía historial | Media | 11/10/2026 | 11/10/2026 | Corregido | bb9b2c8 |
| 6 | API no aplica políticas por fila | Alta | 11/10/2026 | 18/10/2026 | Corregido y desplegado | 9311557 |
| 7–10 | Cálculos de analítica | Media | 11/10/2026 | | Abierto (xfail) | |
| 11 | Tasa de cambio guardaba `"now()"` como fecha | Alta | 11/10/2026 | 18/10/2026 | Corregido | 725600c |
| 12 | Front: recargar cerraba la sesión en desarrollo | Media | 18/10/2026 | 18/10/2026 | Corregido | front 82571c6 |
| 13 | Front: el 409 de categorías no mostraba el motivo | Baja | 18/10/2026 | 18/10/2026 | Corregido | front e6c88aa |
| 14 | Front: Vista semanal llamaba a un módulo retirado (404) | Baja | 18/10/2026 | 18/10/2026 | Corregido | front bf537dc |
| 15 | Front: "Eliminar cuenta" llama a un endpoint inexistente | Media | 18/10/2026 | 19/10/2026 | Corregido | 5fa2838 |
| 16 | Cualquier usuario puede refrescar las tasas de cambio | Baja | 11/10/2026 | 19/10/2026 | Corregido | e55a21c |
| 17 | La prueba del defecto 10 nunca verificó el defecto | Media | 18/10/2026 | 18/10/2026 | Corregido | 4765c90 |
| 18 | Leer o borrar una fila ajena o inexistente daba 500, no 404 | Media | 18/10/2026 | 18/10/2026 | Corregido | 22bda2b |
| 19 | Usuario nuevo: sus preferencias daban 500 y nunca se creaban | Media | 18/10/2026 | 18/10/2026 | Corregido | 22bda2b |
| 20 | El simulador de pruebas no fallaba como la base real | Media | 18/10/2026 | 18/10/2026 | Corregido | 22bda2b |
| 21 | La prueba de aislamiento pedía una ruta inexistente | Baja | 18/10/2026 | 18/10/2026 | Corregido | a0c0de5 |
| 22 | El workflow de CI nunca llegó a ejecutar una prueba | Alta | 18/10/2026 | 18/10/2026 | Corregido | c43e7c6 |
| 23 | Front: la pantalla de inicio mostraba el apodo interno "BudgetTrash" | Baja | 19/10/2026 | 19/10/2026 | Corregido | front 7873adb |
| 24 | El registro no pedía aceptar el Aviso de Privacidad (RF01) | Alta | 19/10/2026 | 19/10/2026 | Corregido | 2a92fbe · front 4055134 |

Commits marked *front* are in
[`backendtrash/FrontendFinanceApp-`](https://github.com/backendtrash/FrontendFinanceApp-);
the rest are in this repository.

**"Cerrado" is the date the fix reached `main`**, not the date of its
commit: a fix sitting on a branch is not yet in the product.

**Hashes assume merge commits.** Merging a PR with *Squash* or *Rebase*
rewrites its commits and these hashes stop resolving. Merge with
*Create a merge commit*.

**Defect 6 is fixed, deployed and verified.** On 18/10 a new Supabase
project was built from `migrations/` (10 tables with RLS, 13 policies) and
the API was deployed against it on Railway, from this repository's `main`.
That pair became the project's production: the earlier proof-of-concept
deployment (`BudgetTracker`, from another repository) stays as it was and
is not part of this codebase. The two-account isolation suite passed
against this deployment: **24 passed**, no skips. It now also runs in CI on
every pull request (`.github/workflows/isolation.yml`). On 19/10 the
frontend went live on Vercel against this API. Account A was checked in the
browser; both accounts were checked against the production API — A sees its
expense, B sees none. The browser capture of account B is still pending.

The isolation suite's first run on staging found defects 18 to 21. None of
them was a leak — user B never received, changed or deleted a row of user
A's — but they had to be fixed before the suite could pass.

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

### 17. The test pinning defect 10 never tested defect 10

**Severity:** medium — false evidence for risk R4
**Found and fixed:** 18/10, commit `4765c90` (PR #3)

`test_weekly_projection_should_match_the_monthly_rollup` read a key named
`projected` from each week bucket; the field is `projected_weekly`. The
`KeyError` made it fail, and `xfail` accepts any exception, so the suite
reported an expected failure for defect 10 while asserting nothing about it.

Found while measuring current values for the coach's decision record:
running the function directly raised the error the test had been hiding.

The four analytics `xfail` markers now carry `raises=AssertionError`, so a
test only counts as an expected failure when its assertion fails. With
that, defects 7–9 still xfail — their tests were sound — and the defect 10
test, fixed to read the real field, fails on exactly the defect:
`2500.00 != 2166.67`.

### 18. A missing or foreign row answered 500 instead of 404

**Severity:** medium
**Found:** 18/10, first two-account isolation run on staging
**Fixed:** 18/10, commit `22bda2b`

User B asking for user A's expense got a 500. Nothing leaked: the query
correctly matched no row. But every by-id lookup used `.single()`, which
raises on zero rows instead of returning nothing, so "not yours" and "not
found" both crashed. Six modules on read, plus the lookup inside
`delete_goal`.

**Not caused by the RLS change.** With the admin client and the `user_id`
filter the query matched zero rows too, so production answers these with a
500 today.

The services had been written expecting a miss — each site checks the
result and falls back to `None`, "Uncategorized" or a rate of 1 — but
`.single()` raised before that code ran. `app.database.fetch_one()` runs
`.maybe_single()` and returns the row or `None`; 13 lookups use it now.
Confirmed live: the same request went from 500 to 404 on staging after the
redeploy.

### 19. A new user's preferences crashed instead of being created

**Severity:** medium · **Found and fixed:** 18/10, commit `22bda2b`

`get_preferences` is meant to create the default row on a user's first
read. Its lookup used `.single()`, which raised on the missing row before
the creation code ran, so every new user got a 500 — which the frontend
swallowed, falling back to its own default week start. Same fix as 18.

### 20. The test stub was kinder than the database

**Severity:** medium · **Found and fixed:** 18/10, commit `22bda2b`

`tests/fakes.py` returned `None` from `.single()` on zero rows, where the
real client raises. So the unit tests could not see defects 18 and 19, and
passed while production returned 500s. The stub now raises like
postgrest-py, and `.maybe_single()` returns `None` from `execute()` itself,
also like the real one. Making it stricter immediately surfaced one more
case: the dashboard's category lookup for the largest expense.

### 21. The isolation suite asked for a route that does not exist

**Severity:** low · **Found and fixed:** 18/10, commit `a0c0de5`

The suite read every module's rows with `GET /{id}`, but projected costs
have no such route, so two cases failed on a 405 that said nothing about
isolation. Projected is now checked through the listing and through a write
attempt: B tries to rename A's projected cost and is refused.

### 22. CI never ran a single test

**Severity:** high — the safety net was not there
**Found and fixed:** 18/10, commit `c43e7c6`

Every run of the `tests` workflow failed with exit code 4, pytest's code
for "could not start" rather than "tests failed". `conftest.py` could not
import the `app` package: `python -m pytest` adds the current directory to
`sys.path`, plain `pytest` does not. The suite had only been run the first
way locally; the workflow and the README use the second.

So the first four runs on GitHub — including the ones on the PRs that were
merged — checked nothing. `pythonpath = .` in `pytest.ini` fixes both
invocations. Verified with the exact workflow command and no Supabase
variables: exit 4 before, 219 passed after.

The lesson for the process: a check is only evidence once it has been seen
to pass *and* seen to fail for the right reason.

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

### 15. "Delete account" called an endpoint that did not exist

**Severity:** medium · **Found:** 18/10 · **Fixed:** commit `5fa2838` on 18/10, in `main` on 19/10 (PR #6)

Settings → Delete account called `DELETE /api/v1/auth/account`; the backend
had no such route, so the button always failed. The route exists now.
Deleting an Auth user needs the service role, so the call lives in
`app/database.py` as `delete_auth_user()`, one of the two modules allowed to
use it. Every user table references `auth.users(id) ON DELETE CASCADE`, so
the user's data goes in the same transaction as the account. The id comes
only from the verified token, never from the request.

### 16. Any authenticated user could trigger an exchange rate refresh

**Severity:** low · **Found:** 11/10, recorded 18/10 · **Fixed:** commit `e55a21c` on 18/10, in `main` on 19/10 (PR #6)

`POST /currencies/update-rates` was open to every signed-in user while it
writes the shared `currencies` table as the system and spends the rate
API's quota. It now requires the caller's email in `ADMIN_EMAILS` and
answers 403 otherwise; empty means nobody. A daily job at 06:00 UTC
refreshes rates on its own, so no one has to.

### 23. The sign-in screen showed the internal nickname

**Severity:** low · **Repo:** frontend
**Found and fixed:** 19/10, commit `7873adb`

The first sign-in on the production frontend greeted the user with
"Welcome back to BudgetTrash", an internal nickname. The rename on 18/10
had searched only for "Budget Tracker", so eight occurrences of this one
survived — sign-in, registration, Settings, the header's fallback title,
the iOS home-screen title and the data export's file name. All now say
BackendFinance; a search for both old names finds nothing.

### 24. Registration did not ask for consent to the privacy notice (RF01)

**Severity:** high — RF01 could not count as verified
**Found:** 19/10, by review against E1 · **Fixed:** 19/10, commits `2a92fbe` (API) and `4055134` (frontend)

RF01 requires accepting the privacy notice to create an account. Neither
the registration screen nor the API asked. Now the API answers 422 to any
registration without `accepted_privacy: true`, and stores the consent in
the account's Supabase metadata: the time, set by the server, and the
notice version. The registration screen shows the short notice, a required
checkbox worded exactly as the notice ("He leído y acepto el Aviso de
Privacidad") and an optional one for the voluntary purposes, never
pre-ticked. The full notice is public at `/privacidad`.

The responsible party's details in the notice — name, address, privacy
email, the area in charge, the people with access, the deletion period —
are still placeholders, shown highlighted under a draft banner.

**Merged in the wrong order.** The API change (backend PR #8) was meant to
be merged after the frontend one and was merged first. With *Wait for CI*
on, Railway only deployed it once the checks on `main` passed, which left
little room for harm. Measured in production: the API was not yet
enforcing consent at 18:30:31 and was at 18:32:17; the frontend that sends
the field was live by 18:31. If registration failed at all, it was for
seconds to a couple of minutes, not hours — but zero cannot be shown.

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
