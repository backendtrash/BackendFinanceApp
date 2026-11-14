"""
Defect 30: the Recurring screen estimated a month as amount x 4.33 a week.
A $500 rule every Monday showed $2,165 for November 2026, which has five
Mondays: the scheduler writes $2,500. GET /recurring/monthly counts the
charges a rule really makes in the month.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.database import bind_db
from app.main import app
from app.recurring.service import charge_dates_in_month, get_monthly_recurring
from fakes import FakeSupabase

USER = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"
MXN = "11111111-1111-1111-1111-111111111111"
USD = "44444444-4444-4444-4444-444444444444"


def rule(rid, amount, frequency, next_due, start=None, end=None, kind="expense",
         dow=None, dom=None, currency=MXN, active=True, user=USER):
    return {"id": rid, "user_id": user, "type": kind, "amount": str(amount),
            "currency_id": currency, "frequency": frequency,
            "start_date": start or next_due, "end_date": end, "next_due_date": next_due,
            "day_of_week": dow, "day_of_month": dom, "is_active": active,
            "created_at": "2026-10-01T00:00:00+00:00"}


def test_a_weekly_rule_charges_every_seven_days_from_its_cursor():
    monday = rule("r", 500, "weekly", "2026-11-02", start="2026-10-05", dow=0)
    assert charge_dates_in_month(monday, 2026, 11) == [
        date(2026, 11, d) for d in (2, 9, 16, 23, 30)]
    assert len(charge_dates_in_month(monday, 2026, 12)) == 4      # 7, 14, 21, 28


def test_charges_respect_start_and_end_dates():
    late_start = rule("r", 100, "weekly", "2026-11-16", start="2026-11-10")
    assert charge_dates_in_month(late_start, 2026, 11) == [
        date(2026, 11, 16), date(2026, 11, 23), date(2026, 11, 30)]
    ended = rule("r", 100, "weekly", "2026-11-02", start="2026-10-01", end="2026-11-15")
    assert charge_dates_in_month(ended, 2026, 11) == [date(2026, 11, 2), date(2026, 11, 9)]


def test_a_monthly_rule_charges_once_on_its_day_clamped_to_the_month():
    on_31 = rule("r", 1200, "monthly", "2026-10-31", start="2026-10-31", dom=31)
    assert charge_dates_in_month(on_31, 2026, 11) == [date(2026, 11, 30)]
    no_day = rule("r", 1200, "monthly", "2026-11-12", start="2026-10-12")
    assert charge_dates_in_month(no_day, 2027, 2) == [date(2027, 2, 12)]


async def test_monthly_totals_by_type_in_mxn():
    bind_db(FakeSupabase(
        recurring_rules=[
            rule("mon", 500, "weekly", "2026-11-02", start="2026-10-05", dow=0),
            rule("rent", 100, "monthly", "2026-11-01", start="2026-10-01", dom=1, currency=USD),
            rule("pay", 8000, "monthly", "2026-11-15", start="2026-10-15", dom=15, kind="income"),
            rule("off", 999, "weekly", "2026-11-02", active=False),
            rule("theirs", 999, "weekly", "2026-11-02", user=OTHER),
        ],
        currencies=[{"id": MXN, "exchange_rate": "1"}, {"id": USD, "exchange_rate": "18"}],
    ))

    result = await get_monthly_recurring(USER, 2026, 11)

    assert result["rules"]["mon"] == {"charges": 5, "amount_mxn": Decimal("2500")}
    assert result["rules"]["rent"]["amount_mxn"] == Decimal("1800")
    assert result["expense_total"] == Decimal("4300")
    assert result["income_total"] == Decimal("8000")
    assert result["net"] == Decimal("3700")
    assert set(result["rules"]) == {"mon", "rent", "pay"}


@pytest.fixture
def as_user(client):
    fake = FakeSupabase(
        recurring_rules=[rule("mon", 500, "weekly", "2026-11-02", start="2026-10-05", dow=0)],
        currencies=[{"id": MXN, "exchange_rate": "1"}],
    )

    async def fake_user():
        bind_db(fake)
        return AuthenticatedUser(user_id=USER, email="a@example.com", db=fake)
    app.dependency_overrides[get_current_user] = fake_user
    yield client
    app.dependency_overrides.clear()


def test_the_route_is_not_taken_for_a_rule_id(as_user):
    response = as_user.get("/api/v1/recurring/monthly", params={"year": 2026, "month": 11})
    assert response.status_code == 200, response.text[:200]
    assert Decimal(str(response.json()["expense_total"])) == Decimal("2500")
