"""
Defect 28: Settings -> "Export all data" called GET /api/v1/export, a route
that did not exist, so the button did nothing.
"""
import pytest

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.database import bind_db
from app.main import app
from fakes import MAX_ROWS, FakeSupabase

USER = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"
SYSTEM_CAT = "44444444-4444-4444-4444-444444444444"
UNUSED_SYSTEM_CAT = "55555555-5555-5555-5555-555555555555"
OWN_CAT = "66666666-6666-6666-6666-666666666666"

TABLES = (
    "expenses", "earnings", "categories", "budgets", "budget_alerts",
    "recurring_rules", "goals", "projected_costs", "user_preferences",
)


@pytest.fixture
def as_user_with(client):
    def use(fake: FakeSupabase):
        async def fake_user():
            bind_db(fake)
            return AuthenticatedUser(user_id=USER, email="a@example.com", db=fake)
        app.dependency_overrides[get_current_user] = fake_user
        return client
    yield use
    app.dependency_overrides.clear()


def _row(table, n, user=USER, **extra):
    return {"id": f"{table}-{user[-1]}-{n:05d}", "user_id": user, **extra}


def _db(**overrides) -> FakeSupabase:
    tables = {t: [_row(t, 1), _row(t, 1, user=OTHER)] for t in TABLES}
    tables["categories"] = [
        {"id": OWN_CAT, "user_id": USER, "name": "Mine"},
        {"id": SYSTEM_CAT, "user_id": None, "name": "Food"},
        {"id": UNUSED_SYSTEM_CAT, "user_id": None, "name": "Travel"},
        {"id": "cat-other", "user_id": OTHER, "name": "Theirs"},
    ]
    tables["expenses"] = [
        _row("expenses", 1, category_id=SYSTEM_CAT),
        _row("expenses", 2, category_id=OWN_CAT),
        _row("expenses", 1, user=OTHER, category_id="cat-other"),
    ]
    tables.update(overrides)
    return FakeSupabase(**tables)


def test_export_returns_every_table_of_the_caller(as_user_with):
    response = as_user_with(_db()).get("/api/v1/export")

    assert response.status_code == 200, response.text[:200]
    body = response.json()
    assert set(body["tables"]) == set(TABLES)
    assert body["account"] == {"id": USER, "email": "a@example.com"}
    assert body["counts"]["expenses"] == 2
    assert all(
        row["user_id"] == USER
        for rows in body["tables"].values() for row in rows
    ), "another user's row is in the export"


def test_export_is_a_download(as_user_with):
    response = as_user_with(_db()).get("/api/v1/export")
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert ".json" in disposition


def test_export_answers_without_a_trailing_slash_redirect(as_user_with):
    """
    The frontend calls /api/v1/export exactly. A 307 to the slashed path
    would point at http:// behind Railway's proxy and be refused by the
    browser on an https page.
    """
    response = as_user_with(_db()).get("/api/v1/export", follow_redirects=False)
    assert response.status_code == 200


def test_export_names_the_system_categories_its_rows_use(as_user_with):
    """
    An expense in a shared category carries only its id. The export lists
    that category, so the file reads on its own, and leaves out shared
    categories nothing points to.
    """
    body = as_user_with(_db()).get("/api/v1/export").json()
    referenced = {c["id"] for c in body["system_categories_referenced"]}
    assert referenced == {SYSTEM_CAT}


def test_export_reads_past_the_1000_row_cap(as_user_with):
    """
    Supabase answers at most 1,000 rows per request and says nothing about
    the rest. The export pages until a page comes back short.
    """
    many = [_row("expenses", n) for n in range(MAX_ROWS * 2 + 500)]
    fake = _db(expenses=many)

    body = as_user_with(fake).get("/api/v1/export").json()

    assert body["counts"]["expenses"] == len(many)
    assert len({r["id"] for r in body["tables"]["expenses"]}) == len(many)


def test_export_requires_a_signed_in_user(raw_client):
    assert raw_client.get("/api/v1/export").status_code == 401
