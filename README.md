# BackendFinance — Backend API

FastAPI REST API for the BackendFinance personal finance application.

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
| Auth        | `/api/v1/auth`         | 5         | Login, register, refresh, me     |
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

80 endpoints in total: 77 above plus `/`, `/health` and `/scheduler`.
74 require authentication; the 6 that do not are register, login, refresh
and the three health routes.

> Docs available at `/docs` when `DEBUG=True`

## Scheduler Jobs

| Job                      | Schedule        | Description                        |
|--------------------------|-----------------|------------------------------------|
| `process_recurring_rules`| Daily 00:00 UTC | Creates transactions from rules    |
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
