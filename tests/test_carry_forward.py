"""
Defect 31, option A: the carry-forward is the month's opening balance —
everything earned minus everything spent before its 1st — computed on
demand and never written as a movement.

It used to be written as a real expense or earning on the 1st, which net
worth, totals, trends and projected vs real then counted again: in the test
account, one real expense of 145 showed as a net worth of -290.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.analytics import service
from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.database import bind_db
from app.main import app
from fakes import FakeSupabase

USER = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"
MXN = "11111111-1111-1111-1111-111111111111"


def _row(amount, day, user=USER):
    return {"amount_mxn": str(amount), "date": day.isoformat(), "user_id": user,
            "category_id": None}


def _db():
    return FakeSupabase(
        earnings=[_row(1000, date(2026, 8, 5)), _row(9999, date(2026, 8, 5), user=OTHER)],
        expenses=[
            _row(145, date(2026, 10, 19)),
            _row(300, date(2026, 9, 2)),
            _row(50, date(2026, 11, 1)),          # in November itself: not before it
            _row(9999, date(2026, 10, 1), user=OTHER),
        ],
        currencies=[{"id": MXN, "code": "MXN", "exchange_rate": "1"}],
    )


async def test_the_carry_forward_is_the_balance_before_the_month():
    bind_db(_db())

    status = await service.get_carry_forward_status(USER, 2026, 11)

    # 1000 earned in August, 300 + 145 spent in September and October.
    assert status["balance"] == Decimal("555.00")
    assert status["entry_type"] == "income"
    assert status["source_period"] == "Oct 2026"


async def test_january_carries_over_from_december_of_the_year_before():
    bind_db(_db())
    status = await service.get_carry_forward_status(USER, 2027, 1)
    assert status["source_period"] == "Dec 2026"
    assert status["balance"] == Decimal("505.00")     # November's 50 now counts


async def test_applying_writes_nothing_however_often_it_is_called():
    """
    Idempotent by construction: there is no movement to create. Called
    twice, or by two Dashboards at once, it changes no row.
    """
    fake = _db()
    bind_db(fake)
    before = {t: [dict(r) for r in fake.rows(t)] for t in ("expenses", "earnings")}

    first = await service.apply_carry_forward(USER, 2026, 11)
    second = await service.apply_carry_forward(USER, 2026, 11)

    assert first == second == await service.get_carry_forward_status(USER, 2026, 11)
    assert first["applied"] is True
    for table in ("expenses", "earnings"):
        assert fake.ops_on(table, "insert") == []
        assert fake.rows(table) == before[table]


async def test_net_worth_is_not_moved_by_the_carry_forward():
    """The regression in the test account: one real expense, counted once."""
    y, m = date.today().year, date.today().month
    prev = (y, m - 1) if m > 1 else (y - 1, 12)
    fake = FakeSupabase(
        earnings=[],
        expenses=[_row(145, date(prev[0], prev[1], 19))],
        currencies=[{"id": MXN, "code": "MXN", "exchange_rate": "1"}],
    )
    bind_db(fake)

    await service.apply_carry_forward(USER, y, m)
    history = await service.get_net_worth_history(USER, months_back=3)

    assert history["current_worth"] == Decimal("-145")


@pytest.fixture
def as_user(client):
    fake = _db()

    async def fake_user():
        bind_db(fake)
        return AuthenticatedUser(user_id=USER, email="a@example.com", db=fake)
    app.dependency_overrides[get_current_user] = fake_user
    yield client, fake
    app.dependency_overrides.clear()


def test_the_post_route_answers_like_get_and_writes_nothing(as_user):
    """The route stays for the frontend from before the fix; it no longer writes."""
    client, fake = as_user

    posted = client.post("/api/v1/analytics/carry-forward", json={"year": 2026, "month": 11})
    got = client.get("/api/v1/analytics/carry-forward", params={"year": 2026, "month": 11})

    assert posted.status_code == got.status_code == 200
    assert posted.json() == got.json()
    assert Decimal(str(got.json()["balance"])) == Decimal("555")
    assert fake.ops_on("expenses", "insert") == fake.ops_on("earnings", "insert") == []
