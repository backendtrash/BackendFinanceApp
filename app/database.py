from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator, Optional

from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions

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

# Anon client — used only by the auth router for sign-in, sign-up and refresh
supabase: Client = create_supabase_client()

# Admin client — bypasses RLS. Only app/scheduler.py may use it, and
# tests/test_db_boundary.py fails if anything else imports it.
supabase_admin: Client = create_supabase_admin_client()

# ── Per-request client ────────────────────────────────────────────────────
# Every request made on behalf of a user goes through a client that carries
# that user's own JWT, so Supabase runs the query as the `authenticated` role
# with auth.uid() set — and the row level security policies in migrations/
# actually apply.
#
# The admin client above used to serve user requests too, which meant those
# policies were never exercised: isolation rested entirely on each query
# remembering its .eq("user_id", ...). That was defect 6.
#
# How the client reaches the services: get_current_user binds it into a
# ContextVar, and services call db(). Every protected endpoint and dependency
# is async, so a value bound in the dependency is visible to the endpoint and
# everything it awaits, and each request runs in its own context, so one
# request can never see another's client.

_db: ContextVar[Optional[Client]] = ContextVar("db", default=None)


def create_user_client(access_token: str) -> Client:
    """
    A client that acts as the user who owns `access_token`.

    Built with the ANON key, with the user's JWT as the Authorization header.
    supabase-py prefers an Authorization header passed in the options over
    the one it would derive from the key, so PostgREST sees the user's token.

    One per request. auto_refresh_token and persist_session are off: the
    token arrives already verified and dies with the request, so there is no
    session to keep or refresh.
    """
    return create_client(
        settings.supabase_url,
        settings.supabase_anon_key,
        options=ClientOptions(
            headers={"Authorization": f"Bearer {access_token}"},
            auto_refresh_token=False,
            persist_session=False,
        ),
    )


def bind_db(client: Client) -> Token:
    """Makes `client` the one db() returns for the rest of this context."""
    return _db.set(client)


@contextmanager
def using_db(client: Client) -> Iterator[Client]:
    """
    Runs a block with `client` bound, restoring the previous one afterwards.

    The scheduler uses this to run background jobs as the system, which is
    the only legitimate use of supabase_admin left in the application.
    """
    token = _db.set(client)
    try:
        yield client
    finally:
        _db.reset(token)


def db() -> Client:
    """
    The client for the current request or job.

    Fails closed. If nothing has been bound — a route that forgot its
    authentication dependency, a job that forgot its system context — this
    raises instead of falling back to the admin client. A silent fallback
    would quietly reintroduce defect 6.
    """
    client = _db.get()
    if client is None:
        raise RuntimeError(
            "No database client bound to this context. User requests get one "
            "from get_current_user; background jobs must use using_db()."
        )
    return client
