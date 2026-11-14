# BackendFinance — Backend API

FastAPI REST API for the BackendFinance personal finance application.

Built for Studio JJPT, the responsible party named in the privacy notice. The
course documents (Evidencias, actas) call the same company Studio A.

## Tech Stack

- **Runtime:** Python 3.12
- **Framework:** FastAPI 0.111.0
- **Database:** Supabase (PostgreSQL) with Row Level Security
- **Auth:** Supabase Auth, ES256 JWT verified via JWKS
- **Scheduler:** APScheduler 3.10.4 (recurring rules + budget alerts)
- **Deploy:** Railway

## Project Structure

```
app/
├── main.py              # FastAPI app, middleware, router registration
├── config.py            # Pydantic settings from environment variables
├── database.py          # Supabase client instances (anon + service role)
├── scheduler.py         # APScheduler jobs (midnight + 8am daily)
│
├── auth/                # JWT verification, login, register, refresh
├── expenses/            # CRUD, bulk delete, import, month summary
├── earnings/            # CRUD, bulk delete, import, month summary
├── categories/          # System + user categories (expense/income)
├── currencies/          # MXN base, exchange rates, conversion
├── budgets/             # CRUD, alerts, spending progress
├── recurring/           # Rules engine, process due rules
├── analytics/           # Dashboard, monthly, weekly, category,
│                        # projected, net worth, YoY, trends
├── goals/               # Fixed amount + monthly rate goals,
│                        # auto-creates savings category
├── projected/           # Projected cost rules for forecasting
└── preferences/         # Per-user settings (week start day)

migrations/              # Versioned SQL for all 10 tables + RLS + functions
tests/                   # pytest suite; see tests/README.md
```

## Environment Variables

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
APP_NAME=BackendFinance API
APP_VERSION=0.1.0
DEBUG=False
ALLOWED_ORIGINS=https://your-frontend.vercel.app,http://localhost:5173
EXCHANGE_RATE_BASE_CURRENCY=MXN
EXCHANGE_RATE_API_KEY=               # optional; without it the rate refresh is skipped
ADMIN_EMAILS=you@example.com         # who may refresh exchange rates by hand
SCHEDULER_ENABLED=true               # false only where the API runs just to be tested
```

No JWT secret is needed. Tokens are ES256 and verified against the public
keys Supabase publishes at `$SUPABASE_URL/auth/v1/.well-known/jwks.json`.

## Local Development

```bash
git clone https://github.com/backendtrash/BackendFinanceApp.git
cd BackendFinanceApp

python -m venv venv
venv\Scripts\activate         # Windows
source venv/bin/activate      # Mac/Linux

pip install -r requirements.txt

# Create .env with the variables above

uvicorn app.main:app --reload --port 8000
```

### The whole system on one machine

To run API and frontend locally (H4 asks for exactly this), against the
project's Supabase:

1. **`.env`** with the variables above. Two lines matter locally:

   ```env
   SCHEDULER_ENABLED=false
   ALLOWED_ORIGINS=http://localhost:5173
   ```

   **`SCHEDULER_ENABLED=false` is not optional.** The project has a single
   Supabase database, production. With the scheduler on, a laptop would run
   the startup catch-up and the nightly jobs — recurring rules, budget
   alerts, exchange rates — against real users' data, alongside the server.

2. **API:** `uvicorn app.main:app --reload --port 8000`. `GET
   http://localhost:8000/health` answers `{"status": "healthy", ...}` and the
   startup log says `Scheduler disabled`.

3. **Frontend:** in the other repository, `corepack pnpm dev`; it calls
   `http://localhost:8000` by default. Open `http://localhost:5173`.

4. **Sign in with a test account** (`prueba-a` or `prueba-b`), not a personal
   one: everything you do locally writes to the production database.

Sign-up from a local frontend works, but the confirmation email links to the
Site URL set in Supabase → Authentication → URL Configuration, which is the
deployed frontend.

### Scripts against the test accounts

`scripts/` holds tools that sign in as `prueba-a` through the API, with the
credentials in an env file kept outside the repository:

| Script | What it does |
|---|---|
| `seed_prueba_a.py` | Loads a year of tagged data; a second run adds nothing |
| `verificar_graficas.py` | The five essential charts against the account's rows (`docs/verificacion-graficas.md`) |
| `e2e_api.py` | The main flows end to end, cleaning up after each (`docs/flujos-e2e.md`) |

### Database

The schema lives in `migrations/`, numbered in dependency order. On a fresh
Supabase project run them in filename order in the SQL editor; each file is
idempotent. See `migrations/README.md`.

### Tests

```bash
pytest
```

No credentials needed and nothing reaches the network. Two-account
isolation is a separate, opt-in suite — see `tests/README.md`.

## API Endpoints

| Module      | Base Path              | Endpoints | Description                      |
|-------------|------------------------|-----------|----------------------------------|
| Auth        | `/api/v1/auth`         | 6         | Login, register, refresh, me, delete account |
| Expenses    | `/api/v1/expenses`     | 10        | CRUD + import + months + split   |
| Earnings    | `/api/v1/earnings`     | 9         | CRUD + import + months           |
| Categories  | `/api/v1/categories`   | 6         | Expense + income categories      |
| Currencies  | `/api/v1/currencies`   | 4         | List + convert + update rates    |
| Budgets     | `/api/v1/budgets`      | 9         | CRUD + alerts + progress         |
| Recurring   | `/api/v1/recurring`    | 7         | Rules engine + process           |
| Analytics   | `/api/v1/analytics`    | 12        | Dashboard + charts + trends      |
| Goals       | `/api/v1/goals`        | 6         | Financial goals + progress       |
| Projected   | `/api/v1/projected`    | 6         | Forecast costs                   |
| Preferences | `/api/v1/preferences`  | 3         | Week start day                   |

81 endpoints in total: 78 above plus `/`, `/health` and `/scheduler`.
75 require authentication; the 6 that do not are register, login, refresh
and the three health routes.

> Docs available at `/docs` when `DEBUG=True`

## Scheduler Jobs

| Job                      | Schedule        | Description                        |
|--------------------------|-----------------|------------------------------------|
| `process_recurring_rules`| Daily 00:00 UTC | Creates transactions from rules    |
| `refresh_exchange_rates` | Daily 06:00 UTC | Pulls current rates into `currencies` |
| `check_budget_alerts`    | Daily 08:00 UTC | Checks budgets for threshold breach|

On startup the server also runs a **catchup** — processing any rules that
were missed while it was offline. Processing is idempotent: an occurrence is
claimed by advancing `next_due_date` before the transaction is written, and
a unique index on `(recurring_rule_id, date)` backs that up, so a catchup
that overlaps the nightly job cannot double-charge.

## Security

- ES256 JWT verification via the Supabase JWKS endpoint
- Row Level Security policies on every table (see the caveat below)
- Rate limiting: 5 req/min login, 3 req/min register
- Security headers: XSS, clickjacking, MIME sniffing protection
- CORS restricted to known frontend origins
- `DEBUG=False` in production disables `/docs`

**On Row Level Security.** Every table has RLS enabled and a policy, but
the API does not rely on them: all modules use the service role client,
which bypasses RLS. At runtime, isolation between users rests on the
`.eq("user_id", ...)` filter in each service function. The policies protect
direct queries from the frontend and act as a second line of defence. This
is why `tests/test_isolation.py` exercises the API with two real accounts
rather than trusting the policies.

## Deployment (Railway)

```bash
# Push to GitHub → Railway auto-deploys
git push origin main

# Monitor logs
Railway Dashboard → Deployments → View Logs

# Health checks — set RAILWAY_URL to your deployment
curl "$RAILWAY_URL/health"
curl "$RAILWAY_URL/scheduler"
```

## Key Design Decisions

- **MXN as base currency** — all amounts stored as `amount_mxn` at the rate
  in force when the row was written, so analytics stay consistent and a
  later rate change cannot rewrite past months
- **Goal contributions are expenses** — reduces net balance correctly and
  tracks progress in the same movement
- **Projected costs separate from recurring rules** — recurring rules
  generate real transactions; projected costs are forecast only
- **Generated columns** (`week_number`, `week_year`) — ISO week, derived in
  the database. PostgREST cannot write a generated column, so date changes
  go through the RPC functions in `migrations/011_rpc_functions.sql`
- **A category with movements cannot be deleted** — the schema would set
  references to null, which silently reclassifies history and changes what
  a budget measures. The API returns 409 with the counts instead
