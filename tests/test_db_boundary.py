"""
Who may talk to the database as whom.

Defect 6 was that every user request ran through supabase_admin, the service
role client, which bypasses row level security. The fix gives each request a
client carrying the user's own JWT and confines the admin client to the
scheduler. This file is what keeps it that way.

The first test is the guard the cut-off document asks for: it fails the
moment any module other than app/database.py and app/scheduler.py mentions
supabase_admin. Everything else checks that the replacement actually works —
that the client a service sees is the user's, carrying the user's token,
and that background jobs see the admin client and nothing else does.
"""
import contextvars
import pathlib

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app import database
from app.auth import dependencies
from app.database import db, supabase_admin, using_db
from conftest import TEST_USER_ID, make_token
from fakes import FakeSupabase

APP_DIR = pathlib.Path(__file__).resolve().parent.parent / "app"

# The only two files allowed to name the service role client: the one that
# creates it, and the one that runs background jobs as the system.
ALLOWED = {"database.py", "scheduler.py"}


# ── The guard ─────────────────────────────────────────────────────────────

def test_only_the_scheduler_and_database_module_use_supabase_admin():
    """
    Any user-facing module that imports the admin client brings defect 6
    back for that module: its queries bypass RLS and isolation falls back to
    hand-written filters alone.

    If this fails, the module should read its client through db() instead.
    If it is genuinely background work, it belongs in app/scheduler.py,
    inside using_db(supabase_admin).
    """
    offenders = []
    for path in sorted(APP_DIR.rglob("*.py")):
        relative = path.relative_to(APP_DIR).as_posix()
        if relative in ALLOWED:
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8-sig").splitlines(), start=1
        ):
            if "supabase_admin" in line:
                offenders.append(f"app/{relative}:{number}: {line.strip()}")

    assert not offenders, (
        "supabase_admin used outside the system context:\n  "
        + "\n  ".join(offenders)
    )


# ── db() fails closed ─────────────────────────────────────────────────────

def test_db_raises_when_nothing_is_bound():
    """
    A route that forgot its authentication dependency, or a job that forgot
    its system context, must fail loudly. Falling back to the admin client
    would reintroduce defect 6 without any visible symptom.
    """
    with pytest.raises(RuntimeError, match="No database client bound"):
        contextvars.Context().run(db)


def test_using_db_restores_the_previous_binding():
    outer, inner = FakeSupabase(), FakeSupabase()

    def scenario():
        with using_db(outer):
            with using_db(inner):
                assert db() is inner
            assert db() is outer
        with pytest.raises(RuntimeError):
            db()

    contextvars.Context().run(scenario)


# ── The user's client ─────────────────────────────────────────────────────

def test_the_user_client_sends_the_users_token_and_the_anon_key():
    """
    What makes RLS apply: PostgREST has to receive the user's JWT as the
    Authorization header, with the anon key — never the service role key —
    as the apikey.
    """
    client = database.create_user_client("header.payload.signature")
    headers = client.postgrest.session.headers

    assert headers["Authorization"] == "Bearer header.payload.signature"
    assert headers["apikey"] == database.settings.supabase_anon_key
    assert headers["apikey"] != database.settings.supabase_service_role_key


async def test_get_current_user_binds_a_client_carrying_that_users_token(
    signing_key, published_keys
):
    token = make_token(signing_key)

    user = await dependencies.get_current_user(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    )

    bound = db()
    assert bound is user.db
    assert bound is not supabase_admin
    assert bound.postgrest.session.headers["Authorization"] == f"Bearer {token}"


async def test_get_user_db_returns_the_same_client(signing_key, published_keys):
    token = make_token(signing_key)
    user = await dependencies.get_current_user(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    )

    assert await dependencies.get_user_db(user) is user.db


def test_a_real_request_reaches_the_service_with_the_users_client(
    client, signing_key, published_keys, monkeypatch
):
    """
    End to end through the HTTP stack: route, dependency, binding, service.

    The point is the threading. The TestClient runs the app on its own
    thread, and the binding has to survive from the dependency into the
    service on that thread. If it did not, db() would raise and this would
    be a 500.
    """
    seen_tokens = []
    fake = FakeSupabase(user_preferences=[{
        "id": "p1", "user_id": TEST_USER_ID, "week_start_day": 3,
        "created_at": "2026-10-18T00:00:00", "updated_at": "2026-10-18T00:00:00",
    }])

    def fake_user_client(token):
        seen_tokens.append(token)
        return fake

    monkeypatch.setattr(dependencies, "create_user_client", fake_user_client)

    token = make_token(signing_key)
    response = client.get(
        "/api/v1/preferences/", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["week_start_day"] == 3
    assert seen_tokens == [token], "the service did not get this user's client"
    assert fake.ops_on("user_preferences", "select"), "the fake was never queried"


# ── The system context ────────────────────────────────────────────────────

async def test_startup_catchup_runs_as_the_system(monkeypatch):
    """
    Processing every user's missed rules is background work, so it — and
    only it — sees the admin client.
    """
    from app import scheduler
    from app.recurring import service as recurring_service

    seen = []

    async def fake_process(user_id=None):
        seen.append(db())
        return {"processed": 0, "created": 0, "errors": 0, "transactions": []}

    monkeypatch.setattr(recurring_service, "process_due_rules", fake_process)

    await scheduler.run_startup_catchup()

    assert seen == [supabase_admin]


async def test_rate_refresh_runs_as_the_system(monkeypatch):
    """
    currencies has a read-only policy for users, so a user's own client
    cannot write rates. The refresh runs as the system even when a user's
    request triggers it.
    """
    from app import scheduler
    from app.currencies import service as currencies_service

    seen = []

    async def fake_update():
        seen.append(db())
        return {"status": "success", "updated": [], "count": 0}

    monkeypatch.setattr(currencies_service, "update_exchange_rates", fake_update)

    user_client = FakeSupabase()
    with using_db(user_client):
        await scheduler.refresh_exchange_rates()
        assert db() is user_client, "the system context leaked past the job"

    assert seen == [supabase_admin]
