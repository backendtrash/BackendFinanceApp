"""
Two-account isolation: one user must never reach another user's rows.

This is the evidence the status report asks for before the Verificado
column can be ticked, and it is the only test here that needs a real
Supabase project. Everything else in tests/ runs against stubs.

Why it cannot be a unit test
----------------------------
Every module imports supabase_admin, the service role client, which
bypasses row level security completely. So isolation is not enforced by the
database at runtime — it is enforced by a hand-written .eq("user_id", ...)
on each query. A stub cannot prove those filters are all present and
correct, because a stub is not what would leak. Only two real accounts
against the real stack can.

Running it
----------
Create two throwaway accounts in the Supabase project, then:

    export EXPOS_TEST_BASE_URL=http://localhost:8000
    export EXPOS_TEST_USER_A_EMAIL=a@example.com
    export EXPOS_TEST_USER_A_PASSWORD=...
    export EXPOS_TEST_USER_B_EMAIL=b@example.com
    export EXPOS_TEST_USER_B_PASSWORD=...

    pytest tests/test_isolation.py -v

Without those variables the whole module skips, so the default suite stays
runnable with no credentials and no network.

These tests write real rows to whichever project BASE_URL points at. Point
it at a development project, never at production.
"""
import os
import uuid
from datetime import date

import httpx
import pytest

pytestmark = pytest.mark.integration

BASE_URL = os.environ.get("EXPOS_TEST_BASE_URL", "http://localhost:8000")

_REQUIRED = [
    "EXPOS_TEST_USER_A_EMAIL",
    "EXPOS_TEST_USER_A_PASSWORD",
    "EXPOS_TEST_USER_B_EMAIL",
    "EXPOS_TEST_USER_B_PASSWORD",
]
_MISSING = [name for name in _REQUIRED if not os.environ.get(name)]

pytest.importorskip("httpx")

if _MISSING:
    pytest.skip(
        "two-account isolation needs a live project; missing: "
        + ", ".join(_MISSING),
        allow_module_level=True,
    )


# ── Session helpers ───────────────────────────────────────────────────────

def _login(email: str, password: str) -> str:
    response = httpx.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert response.status_code == 200, (
        f"could not log in as {email}: {response.status_code} {response.text[:200]}"
    )
    token = response.json().get("access_token")
    assert token, f"login for {email} returned no access_token"
    return token


@pytest.fixture(scope="module")
def token_a() -> str:
    return _login(
        os.environ["EXPOS_TEST_USER_A_EMAIL"],
        os.environ["EXPOS_TEST_USER_A_PASSWORD"],
    )


@pytest.fixture(scope="module")
def token_b() -> str:
    return _login(
        os.environ["EXPOS_TEST_USER_B_EMAIL"],
        os.environ["EXPOS_TEST_USER_B_PASSWORD"],
    )


@pytest.fixture(scope="module")
def client_a(token_a) -> httpx.Client:
    with httpx.Client(
        base_url=BASE_URL, headers={"Authorization": f"Bearer {token_a}"}, timeout=30
    ) as c:
        yield c


@pytest.fixture(scope="module")
def client_b(token_b) -> httpx.Client:
    with httpx.Client(
        base_url=BASE_URL, headers={"Authorization": f"Bearer {token_b}"}, timeout=30
    ) as c:
        yield c


@pytest.fixture(scope="module")
def currency_id(client_a) -> str:
    response = client_a.get("/api/v1/currencies/")
    assert response.status_code == 200, "could not read currencies"
    currencies = response.json()
    assert currencies, "no currencies seeded; run migrations/001_currencies.sql"
    mxn = next((c for c in currencies if c["code"] == "MXN"), currencies[0])
    return mxn["id"]


def _tag() -> str:
    """Marks every row this suite creates, so leftovers are identifiable."""
    return f"isolation-test-{uuid.uuid4().hex[:8]}"


# ── Per-module fixtures: user A creates one row in each module ────────────

@pytest.fixture(scope="module")
def owned_rows(client_a, currency_id) -> dict:
    """
    One row per module, all owned by user A. Created once and reused, then
    cleaned up at the end of the module.
    """
    created: dict[str, tuple[str, str]] = {}

    r = client_a.post("/api/v1/categories/", json={
        "name": _tag()[:40], "color": "#FF5733", "icon": "tag", "type": "expense",
    })
    assert r.status_code in (200, 201), f"category create failed: {r.text[:200]}"
    category_id = r.json()["id"]
    created["categories"] = ("/api/v1/categories", category_id)

    r = client_a.post("/api/v1/expenses/", json={
        "amount": "123.45", "currency_id": currency_id,
        "date": date.today().isoformat(), "notes": _tag(),
    })
    assert r.status_code in (200, 201), f"expense create failed: {r.text[:200]}"
    created["expenses"] = ("/api/v1/expenses", r.json()["id"])

    r = client_a.post("/api/v1/earnings/", json={
        "amount": "678.90", "currency_id": currency_id,
        "date": date.today().isoformat(), "notes": _tag(),
    })
    assert r.status_code in (200, 201), f"earning create failed: {r.text[:200]}"
    created["earnings"] = ("/api/v1/earnings", r.json()["id"])

    r = client_a.post("/api/v1/budgets/", json={
        "limit_amount": "1000.00", "currency_id": currency_id,
        "period": "monthly", "alert_threshold": 80,
    })
    assert r.status_code in (200, 201), f"budget create failed: {r.text[:200]}"
    created["budgets"] = ("/api/v1/budgets", r.json()["id"])

    r = client_a.post("/api/v1/recurring/", json={
        "type": "expense", "amount": "50.00", "currency_id": currency_id,
        "frequency": "monthly", "day_of_month": 1, "description": _tag(),
    })
    assert r.status_code in (200, 201), f"recurring create failed: {r.text[:200]}"
    created["recurring"] = ("/api/v1/recurring", r.json()["id"])

    r = client_a.post("/api/v1/goals/", json={
        "name": _tag()[:40], "type": "fixed_amount",
        "target_amount": "5000.00", "currency_id": currency_id,
    })
    assert r.status_code in (200, 201), f"goal create failed: {r.text[:200]}"
    created["goals"] = ("/api/v1/goals", r.json()["id"])

    r = client_a.post("/api/v1/projected/", json={
        "name": _tag()[:40], "amount": "200.00",
        "currency_id": currency_id, "frequency": "monthly",
    })
    assert r.status_code in (200, 201), f"projected create failed: {r.text[:200]}"
    created["projected"] = ("/api/v1/projected", r.json()["id"])

    yield created

    for prefix, row_id in created.values():
        try:
            client_a.delete(f"{prefix}/{row_id}")
        except Exception:
            pass


MODULES = ["categories", "expenses", "earnings", "budgets",
           "recurring", "goals", "projected"]


# ── The isolation assertions ──────────────────────────────────────────────

@pytest.mark.parametrize("module", MODULES)
def test_user_b_cannot_read_user_a_row(client_b, owned_rows, module):
    prefix, row_id = owned_rows[module]
    response = client_b.get(f"{prefix}/{row_id}")

    assert response.status_code in (403, 404), (
        f"user B read user A's {module} row: {response.status_code} "
        f"{response.text[:200]}"
    )


@pytest.mark.parametrize("module", MODULES)
def test_user_b_cannot_delete_user_a_row(client_b, client_a, owned_rows, module):
    prefix, row_id = owned_rows[module]
    response = client_b.delete(f"{prefix}/{row_id}")

    assert response.status_code in (403, 404), (
        f"user B deleted user A's {module} row: {response.status_code}"
    )

    # The row must still be there afterwards.
    still_there = client_a.get(f"{prefix}/{row_id}")
    assert still_there.status_code == 200, (
        f"user A's {module} row disappeared after user B tried to delete it"
    )


@pytest.mark.parametrize("module", MODULES)
def test_user_b_listing_excludes_user_a_rows(client_b, owned_rows, module):
    prefix, row_id = owned_rows[module]
    response = client_b.get(f"{prefix}/")
    assert response.status_code == 200

    payload = response.json()
    rows = payload if isinstance(payload, list) else payload.get("items", payload)
    if isinstance(rows, dict):
        rows = next((v for v in rows.values() if isinstance(v, list)), [])

    ids = {row.get("id") for row in rows if isinstance(row, dict)}
    assert row_id not in ids, f"user A's {module} row appeared in user B's list"


def test_user_b_analytics_excludes_user_a_amounts(client_b, owned_rows):
    """
    The dashboard aggregates without returning row ids, so leakage there
    would be invisible to the per-row checks above.
    """
    response = client_b.get("/api/v1/analytics/dashboard")
    assert response.status_code == 200

    body = response.json()
    assert str(body.get("total_expenses", "0")) != "123.45", (
        "user A's expense amount surfaced in user B's dashboard"
    )
    assert str(body.get("total_income", "0")) != "678.90", (
        "user A's earning amount surfaced in user B's dashboard"
    )


def test_each_user_has_their_own_preferences(client_a, client_b):
    """
    Preferences are one row per user. Writing A's must not move B's.
    """
    a_before = client_a.get("/api/v1/preferences/").json()
    b_before = client_b.get("/api/v1/preferences/").json()
    assert a_before["user_id"] != b_before["user_id"]

    new_value = 0 if b_before["week_start_day"] != 0 else 6
    client_a.patch("/api/v1/preferences/", json={"week_start_day": new_value})

    b_after = client_b.get("/api/v1/preferences/").json()
    assert b_after["week_start_day"] == b_before["week_start_day"], (
        "changing user A's preferences changed user B's"
    )

    client_a.patch(
        "/api/v1/preferences/", json={"week_start_day": a_before["week_start_day"]}
    )


def test_me_returns_the_right_identity_for_each_token(client_a, client_b):
    a = client_a.get("/api/v1/auth/me")
    b = client_b.get("/api/v1/auth/me")

    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["email"] == os.environ["EXPOS_TEST_USER_A_EMAIL"]
    assert b.json()["email"] == os.environ["EXPOS_TEST_USER_B_EMAIL"]
