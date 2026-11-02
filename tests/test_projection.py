"""
The projection rule, option A of the signed analytics acta: a projected cost
is spread over the calendar day by day (app/projection.py).
"""
from datetime import date
from decimal import Decimal

import pytest

from app.analytics import service
from app.database import bind_db
from app.projection import amount_in_range, monthly_amount, split_rounded
from fakes import FakeSupabase

USER = "00000000-0000-0000-0000-000000000001"
MXN = "11111111-1111-1111-1111-111111111111"


def weekly(amount, day=None):
    return {"amount": amount, "frequency": "weekly", "day_of_week": day}


def monthly(amount, day=None):
    return {"amount": amount, "frequency": "monthly", "day_of_month": day}


def one_time(amount, year, month, day=None):
    return {"amount": amount, "frequency": "one_time", "year": year, "month": month,
            "day_of_month": day}


# ── Weekly ────────────────────────────────────────────────────────────────

def test_a_weekly_cost_with_no_day_is_a_seventh_a_day():
    # The acta's example: 31 days of a 500 weekly cost.
    assert round(monthly_amount(weekly("500"), 2026, 5), 2) == Decimal("2214.29")
    # February 2026: 28 days, exactly four weeks.
    assert monthly_amount(weekly("500"), 2026, 2) == Decimal("2000")


def test_a_week_split_between_two_months_is_shared_by_days():
    # Monday 28 Sep to Sunday 4 Oct 2026: three days in September, four in October.
    cost = weekly("700")
    assert amount_in_range(cost, date(2026, 9, 28), date(2026, 9, 30)) == Decimal("300")
    assert amount_in_range(cost, date(2026, 10, 1), date(2026, 10, 4)) == Decimal("400")
    assert amount_in_range(cost, date(2026, 9, 28), date(2026, 10, 4)) == Decimal("700")


def test_a_weekly_cost_on_a_weekday_counts_each_such_day():
    # 0 = Monday. October 2026 has four Mondays (5, 12, 19, 26)
    # and five Thursdays (1, 8, 15, 22, 29).
    assert monthly_amount(weekly("100", day=0), 2026, 10) == Decimal("400")
    assert monthly_amount(weekly("100", day=3), 2026, 10) == Decimal("500")
    # A span without that weekday gets nothing.
    assert amount_in_range(weekly("100", day=0), date(2026, 10, 6), date(2026, 10, 11)) == 0


# ── Monthly ───────────────────────────────────────────────────────────────

def test_a_monthly_cost_on_a_day_lands_whole_on_that_day():
    cost = monthly("1200", day=15)
    assert amount_in_range(cost, date(2026, 6, 1), date(2026, 6, 14)) == 0
    assert amount_in_range(cost, date(2026, 6, 15), date(2026, 6, 15)) == Decimal("1200")
    assert monthly_amount(cost, 2026, 6) == Decimal("1200")


def test_day_31_in_a_shorter_month_falls_on_its_last_day():
    cost = monthly("1200", day=31)
    assert monthly_amount(cost, 2026, 6) == Decimal("1200")             # 30 days
    assert amount_in_range(cost, date(2026, 6, 30), date(2026, 6, 30)) == Decimal("1200")
    assert monthly_amount(cost, 2026, 2) == Decimal("1200")             # 28 days


def test_a_monthly_cost_with_no_day_is_prorated_by_days():
    cost = monthly("300")
    assert monthly_amount(cost, 2026, 6) == Decimal("300")
    assert amount_in_range(cost, date(2026, 6, 1), date(2026, 6, 10)) == Decimal("100")
    # Across a month boundary, each month by its own length.
    assert amount_in_range(cost, date(2026, 6, 21), date(2026, 7, 31)) == Decimal("400")


# ── One-time ──────────────────────────────────────────────────────────────

def test_a_one_time_cost_counts_only_in_its_own_month():
    cost = one_time("999", 2026, 7)
    assert monthly_amount(cost, 2026, 7) == Decimal("999")
    assert monthly_amount(cost, 2026, 6) == 0
    assert monthly_amount(cost, 2027, 7) == 0
    on_a_day = one_time("999", 2026, 7, day=3)
    assert amount_in_range(on_a_day, date(2026, 7, 1), date(2026, 7, 2)) == 0
    assert amount_in_range(on_a_day, date(2026, 7, 3), date(2026, 7, 9)) == Decimal("999")


def test_the_rate_converts_to_mxn():
    assert monthly_amount(monthly("100"), 2026, 6, Decimal("18.5")) == Decimal("1850")


def test_an_empty_or_reversed_span_is_zero():
    assert amount_in_range(weekly("700"), date(2026, 6, 2), date(2026, 6, 1)) == 0


# ── Rounding ──────────────────────────────────────────────────────────────

def test_rounded_parts_add_up_to_the_rounded_whole():
    # Three thirds of 100: rounding each gives 99.99.
    parts = [Decimal("100") / 3] * 3
    rounded = split_rounded(parts)
    assert sum(rounded) == Decimal("100.00")
    assert all(abs(r - p) < Decimal("0.01") for r, p in zip(rounded, parts))


# ── The weekly view against the month, everywhere ─────────────────────────

COSTS = [
    weekly("500"), weekly("80", day=4), monthly("1200", day=31), monthly("300"),
    one_time("999", 2026, 6), one_time("450", 2026, 11, day=3),
]


@pytest.mark.parametrize("month", range(1, 13))
@pytest.mark.parametrize("week_start_day", range(7))
async def test_the_weeks_add_up_to_the_month(month, week_start_day):
    """
    Every month of 2026, every week start, a mix of every kind of cost: the
    weeks of the weekly view add up to the month to the cent.
    """
    rows = [
        {"currency_id": MXN, "user_id": USER, "is_active": True,
         "month": None, "year": None, "day_of_month": None, "day_of_week": None, **c}
        for c in COSTS
    ]
    bind_db(FakeSupabase(
        expenses=[], earnings=[], projected_costs=rows,
        currencies=[{"id": MXN, "exchange_rate": "1"}],
    ))

    result = await service.get_dashboard_weekly(USER, 2026, month, week_start_day)

    weeks = sum(Decimal(str(w["projected_weekly"])) for w in result["weeks"])
    expected = round(sum(monthly_amount(c, 2026, month) for c in rows), 2)
    assert weeks == Decimal(str(result["projected_monthly"])) == expected
