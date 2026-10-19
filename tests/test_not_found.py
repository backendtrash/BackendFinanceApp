"""
A row that does not exist, or that belongs to someone else, is a 404 — not a 500.

Found by the two-account isolation run against staging on 18/10. User B
asking for user A's expense got a 500. No data leaked — the query correctly
matched nothing — but every by-id lookup used .single(), which raises on zero
rows, so "not yours" and "not found" both crashed instead of answering 404
(defect 18). A brand-new user's first request for preferences crashed the
same way, before the defaults could be created (defect 19).

The unit tests never saw it because the stub's .single() returned None on no
rows. It now raises, like the real client (defect 20). These tests fail
against the code as it was.
"""
import pytest

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.database import bind_db
from app.main import app
from fakes import FakeSupabase

USER = "00000000-0000-0000-0000-000000000001"
MISSING = "99999999-9999-9999-9999-999999999999"


@pytest.fixture
def as_user_with(client):
    """Authenticates every request as USER, against the given fake database."""
    def use(fake: FakeSupabase):
        async def fake_user():
            bind_db(fake)
            return AuthenticatedUser(user_id=USER, email="a@example.com", db=fake)
        app.dependency_overrides[get_current_user] = fake_user
        return client
    yield use
    app.dependency_overrides.clear()


def _empty() -> FakeSupabase:
    return FakeSupabase(
        expenses=[], earnings=[], categories=[], budgets=[], budget_alerts=[],
        recurring_rules=[], goals=[], projected_costs=[], currencies=[],
        user_preferences=[],
    )


@pytest.mark.parametrize("path", [
    "/api/v1/expenses/{id}",
    "/api/v1/earnings/{id}",
    "/api/v1/categories/{id}",
    "/api/v1/budgets/{id}",
    "/api/v1/recurring/{id}",
    "/api/v1/goals/{id}",
    "/api/v1/currencies/{id}",
])
def test_reading_a_missing_row_is_404(as_user_with, path):
    response = as_user_with(_empty()).get(path.format(id=MISSING))
    assert response.status_code == 404, f"{path}: {response.status_code} {response.text[:120]}"


def test_deleting_a_missing_goal_is_404(as_user_with):
    """delete_goal looked the goal up with .single() before deleting."""
    response = as_user_with(_empty()).delete(f"/api/v1/goals/{MISSING}")
    assert response.status_code == 404, response.text[:120]


def test_a_new_user_gets_default_preferences(as_user_with):
    """
    The service is meant to create the defaults on first read. It never got
    there: the lookup crashed on the missing row first.
    """
    fake = _empty()
    response = as_user_with(fake).get("/api/v1/preferences/")

    assert response.status_code == 200, response.text[:120]
    assert response.json()["week_start_day"] == 1
    assert [r["user_id"] for r in fake.rows("user_preferences")] == [USER], \
        "the default row was not created"


def test_the_stub_raises_on_zero_rows_like_the_real_client():
    """Pins defect 20: the stub must not be kinder than the database."""
    from postgrest.exceptions import APIError

    with pytest.raises(APIError):
        _empty().table("expenses").select("*").eq("id", MISSING).single().execute()

    assert _empty().table("expenses").select("*").maybe_single().execute() is None
