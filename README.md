# Budget Tracker — Backend API

FastAPI REST API for the Budget Tracker personal finance application.

## Tech Stack

- **Runtime:** Python 3.12
- **Framework:** FastAPI 0.111.0
- **Database:** Supabase (PostgreSQL) with Row Level Security
- **Auth:** Supabase Auth with ES256 JWT verification
- **Scheduler:** APScheduler 3.10.4 (recurring rules + budget alerts)
- **Deploy:** Railway

## Project Structure
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
└── projected/           # Projected cost rules for forecasting

## Environment Variables

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
SUPABASE_JWT_SECRET=your_jwt_secret
APP_NAME=Budget Tracker API
APP_VERSION=0.1.0
DEBUG=False
ALLOWED_ORIGINS=https://your-frontend.vercel.app,http://localhost:5173
EXCHANGE_RATE_BASE_CURRENCY=MXN
```

## Local Development

```bash
# Clone the repo
git clone https://github.com/backendtrash/ExpOsBackend.git
cd ExpOsBackend

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Create .env file with variables above

# Run dev server
uvicorn app.main:app --reload --port 8000
```

## API Endpoints

| Module       | Base Path                | Description                        |
|--------------|--------------------------|------------------------------------|
| Auth         | `/api/v1/auth`           | Login, register, refresh, me       |
| Expenses     | `/api/v1/expenses`       | CRUD + import + months             |
| Earnings     | `/api/v1/earnings`       | CRUD + import + months             |
| Categories   | `/api/v1/categories`     | Expense + income categories        |
| Currencies   | `/api/v1/currencies`     | List + convert + update rates      |
| Budgets      | `/api/v1/budgets`        | CRUD + alerts + progress           |
| Recurring    | `/api/v1/recurring`      | Rules engine + process             |
| Analytics    | `/api/v1/analytics`      | Dashboard + charts + trends        |
| Goals        | `/api/v1/goals`          | Financial goals + progress         |
| Projected    | `/api/v1/projected`      | Forecast costs                     |

> Docs available at `/docs` when `DEBUG=True`

## Scheduler Jobs

| Job                      | Schedule       | Description                        |
|--------------------------|----------------|------------------------------------|
| `process_recurring_rules`| Daily 00:00 UTC| Creates transactions from rules    |
| `check_budget_alerts`    | Daily 08:00 UTC| Checks budgets for threshold breach|

On startup the server also runs a **catchup** — processes any rules
that were missed while the server was offline.

## Security

- JWT ES256 verification via Supabase JWKS endpoint
- Row Level Security on all Supabase tables
- Rate limiting: 5 req/min login, 3 req/min register
- Security headers: XSS, clickjacking, MIME sniffing protection
- CORS restricted to known frontend origins
- `DEBUG=False` in production disables `/docs`

## Deployment (Railway)

```bash
# Push to GitHub → Railway auto-deploys
git push origin main

# Monitor logs
Railway Dashboard → Deployments → View Logs

# Check health
curl https://exposbackend-production.up.railway.app/health

# Check scheduler
curl https://exposbackend-production.up.railway.app/scheduler
```

## Key Design Decisions

- **MXN as base currency** — all amounts stored as `amount_mxn` for
  consistent analytics regardless of original currency
- **Goal contributions are expenses** — reduces net balance correctly
  and tracks progress simultaneously
- **Projected costs separate from recurring rules** — recurring rules
  generate real transactions; projected costs are forecast-only
- **Generated columns** (`week_number`, `week_year`) — cannot be
  updated via REST; use RPC functions for date changes