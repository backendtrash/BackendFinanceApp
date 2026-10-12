from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config      import settings
from app.scheduler   import setup_scheduler, scheduler
from slowapi         import Limiter
from slowapi.util    import get_remote_address
from slowapi.errors  import RateLimitExceeded
from fastapi.responses import JSONResponse

# ── Rate Limiter ──────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)


# ── Lifespan ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown events.
    Code before yield runs on startup.
    Code after yield runs on shutdown.
    """
    # ── Startup ───────────────────────────────────────────────────────────
    print(f"🚀 Starting {settings.app_name} v{settings.app_version}")
    print(f"📦 Debug mode: {settings.debug}")
    print(f"🌐 Allowed origins: {settings.allowed_origins_list}")

    # Start the background scheduler
    setup_scheduler()
    scheduler.start()
    print(f"📅 Scheduler started with {len(scheduler.get_jobs())} jobs")

    # On startup immediately process any overdue recurring rules
    # This catches up rules that were missed while the server was down
    try:
        from app.recurring.service import process_due_rules
        result = await process_due_rules()
        if result["created"] > 0:
            print(
                f"⚡ Startup catchup: created {result['created']} "
                f"recurring transactions"
            )
    except Exception as e:
        print(f"⚠️ Startup catchup failed: {e}")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    scheduler.shutdown(wait=False)
    print(f"👋 Shutting down {settings.app_name}")


# ── App Instance ──────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="BackendFinance REST API",

    # Disable docs in production — avoids exposing API structure
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,

    lifespan=lifespan,
)

# Attach rate limiter to app state
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please wait before trying again."}
    )


# ── CORS Middleware ───────────────────────────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to every response.
    Prevents common web attacks:
      XSS, clickjacking, MIME sniffing, info leakage
    """
    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"]  = "nosniff"
        response.headers["X-Frame-Options"]          = "DENY"
        response.headers["X-XSS-Protection"]         = "1; mode=block"
        response.headers["Referrer-Policy"]           = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"]        = "geolocation=(), microphone=()"
        if not settings.debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,

    # Only allow requests from our frontend origins
    allow_origins=settings.allowed_origins_list,

    # Allow cookies and authorization headers to be sent cross-origin
    allow_credentials=True,

    # Allow all HTTP methods (GET, POST, PUT, DELETE, PATCH, OPTIONS)
    allow_methods=["*"],

    # Allow all headers including Authorization (needed for JWT)
    allow_headers=["*"],
)


# ── Health Check ──────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    """
    Simple health check endpoint.
    Used by Railway to verify the app is running.
    Returns 200 OK if the app is healthy.
    """
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
    }

# ── Scheduler Status ──────────────────────────────────────────────────────
@app.get("/scheduler", tags=["Health"])
async def scheduler_status():
    """
    Returns current scheduler status and next run times for all jobs.
    Useful for verifying the scheduler is running correctly.
    """
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id":       job.id,
            "name":     job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
        })
    return {
        "running": scheduler.running,
        "jobs":    jobs,
    }


# ── Root ──────────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
async def root():
    """
    Root endpoint — confirms API is reachable.
    """
    return {
        "message": f"Welcome to {settings.app_name}",
        "docs": "/docs" if settings.debug else "Disabled in production",
    }


# ── Routers ───────────────────────────────────────────────────────────────
# Routers are imported here as modules are built in later phases
# Each router is registered with a prefix and tag for OpenAPI grouping

from app.auth.router       import router as auth_router
from app.expenses.router   import router as expenses_router
from app.earnings.router   import router as earnings_router
from app.categories.router import router as categories_router
from app.currencies.router import router as currencies_router
from app.budgets.router    import router as budgets_router
from app.recurring.router  import router as recurring_router
from app.analytics.router  import router as analytics_router
from app.goals.router import router as goals_router
from app.projected.router import router as projected_router
from app.preferences.router  import router as preferences_router


app.include_router(auth_router,       prefix="/api/v1/auth",       tags=["Auth"])
app.include_router(expenses_router,   prefix="/api/v1/expenses",   tags=["Expenses"])
app.include_router(earnings_router,   prefix="/api/v1/earnings",   tags=["Earnings"])
app.include_router(categories_router, prefix="/api/v1/categories", tags=["Categories"])
app.include_router(currencies_router, prefix="/api/v1/currencies", tags=["Currencies"])
app.include_router(budgets_router,    prefix="/api/v1/budgets",    tags=["Budgets"])
app.include_router(recurring_router,  prefix="/api/v1/recurring",  tags=["Recurring"])
app.include_router(analytics_router,  prefix="/api/v1/analytics",  tags=["Analytics"])
app.include_router(goals_router,      prefix="/api/v1/goals",      tags=["Goals"])
app.include_router(projected_router,  prefix="/api/v1/projected",  tags=["Projected Costs"])
app.include_router(preferences_router, prefix="/api/v1/preferences", tags=["Preferences"])
