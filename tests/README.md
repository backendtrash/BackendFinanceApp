# Tests

```bash
pip install -r requirements.txt
pytest
```

No credentials needed and nothing reaches the network. `conftest.py` sets
placeholder Supabase values before the app is imported, and the client is
built without the application lifespan so the scheduler never starts.

| File | Covers |
|---|---|
| `test_auth_required.py` | every protected endpoint returns 401 without a token |
| `test_auth_tokens.py` | how expired, unsigned and malformed tokens are handled |
| `test_pure_calcs.py` | date and period helpers: month ends, leap years, week bounds |
| `test_analytics_calcs.py` | the dashboard arithmetic (risk R4) |
| `test_isolation.py` | two-account isolation — skipped unless configured |
| `fakes.py` | the stand-in Supabase client, not a test itself |

## The 401 sweep is the H3 evidence

`test_auth_required.py` does not contain a hand-written list of endpoints.
It reads the application's own route table, treats any route whose
dependency tree includes `get_current_user` as protected, and generates one
case per route. Add an endpoint and it is covered the same day; a written
list would have gone stale at the first merge.

```bash
pytest tests/test_auth_required.py -v
```

One line per endpoint, each id reading `module::METHOD /path`. That output
is the artefact for the milestone.

It also pins the six endpoints that are reachable without a token — the
three auth routes and the three health routes. Making anything else public
fails that test, so it has to be a deliberate, reviewed change.

## Known defects are xfail, not skipped

Eight tests are `xfail(strict=True)` — four token-handling cases and
four analytics calculations. Each asserts the value the code
*should* produce, fails against what it produces today, and names the
defect and its line number in the reason.

`strict=True` matters: when a defect is fixed, its test starts passing, and
a strict xfail that passes is reported as a failure. So a fix cannot land
without the test being updated, and a defect cannot be quietly forgotten.

They are listed in `docs/defects.md`. A green run looks like:

```
159 passed, 1 skipped, 8 xfailed
```

The skip is the isolation suite. `xfailed` is expected; `xpassed` or
`failed` is not.

## Two-account isolation needs a real project

`test_isolation.py` skips unless four environment variables are set. It is
the one test that cannot be faked, because of how isolation actually works
here: every module uses the service role client, which bypasses row level
security, so separation rests on a hand-written `.eq("user_id", ...)` in
each query rather than on the database. A stub cannot prove those are all
present — only two real accounts can.

```bash
export EXPOS_TEST_BASE_URL=http://localhost:8000
export EXPOS_TEST_USER_A_EMAIL=a@example.com
export EXPOS_TEST_USER_A_PASSWORD=...
export EXPOS_TEST_USER_B_EMAIL=b@example.com
export EXPOS_TEST_USER_B_PASSWORD=...

pytest tests/test_isolation.py -v
```

It creates a row in each of seven modules as user A, then checks that user B
cannot read it, cannot delete it, does not see it in a listing, and does not
see its amounts in the dashboard totals. Rows are deleted afterwards.

**It writes real data.** Point `EXPOS_TEST_BASE_URL` at a development
project, never at production.

A green run here is what lets the **Verificado** column in the status report
be ticked. Until then that column stays empty, because nothing else in this
suite proves isolation.
