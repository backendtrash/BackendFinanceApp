from supabase import create_client, Client
from app.config import settings


def create_supabase_client() -> Client:
    """
    Creates a Supabase client using the ANON key.
    Used for operations that respect RLS policies.
    This is the client the frontend would use directly —
    we use it in FastAPI when we want RLS enforced.
    """
    return create_client(
        settings.supabase_url,
        settings.supabase_anon_key,
    )


def create_supabase_admin_client() -> Client:
    """
    Creates a Supabase client using the SERVICE ROLE key.
    This client BYPASSES all RLS policies completely.
    Use only for:
      - Background jobs (recurring rules cron)
      - Budget alert generation
      - Currency rate updates
      - Any operation that runs without a user context
    NEVER expose this client to user-facing endpoints directly.
    """
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )


# ── Singletons ────────────────────────────────────────────────────────────
# Module-level instances created once at startup
# Reused across all requests — no reconnection overhead per request

# RLS-enforced client — used in most endpoint service calls
supabase: Client = create_supabase_client()

# Admin client — bypasses RLS — used in background jobs only
supabase_admin: Client = create_supabase_admin_client()