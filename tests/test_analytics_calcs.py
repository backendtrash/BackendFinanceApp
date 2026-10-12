"""
The analytics arithmetic, checked against known inputs.

This is the cover for risk R4 — "the analytics numbers are wrong and nobody
notices". The dashboard is the most-read surface in the product and the
least verifiable by eye: every figure is a Decimal sum over rows the user
cannot see, so a wrong total looks exactly like a right one.

Four tests at the end are marked xfail. They are not scaffolding. Each
encodes the value the function should return, fails against what it returns
today, and names the defect. strict=True means they flip to failures the
moment a fix lands, so none can be quietly forgotten.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.analytics import service
from fakes import FakeSupabase


CURRENCY_MXN = "11111111-1111-1111-1111-111111111111"
CAT_FOOD = "22222222-2222-2222-2222-222222222222"
CAT_RENT = "33333333-3333-3333-3333-333333333333"
USER = "00000000-0000-0000-0000-000000000001"


def _use(monkeypatch, fake: FakeSupabase) -> FakeSupabase:
    monkeypatch.setattr(service, "supabase_admin", fake)
    return fake


def _expense(amount, day, category_id=None, year=2026, month=6):
    return {
        "amount_mxn": str(amount),
        "date": date(year, month, day).isoformat(),
        "category_id": category_id,
        "user_id": USER,
    }


def _earning(amount, day, year=2026, month=6):
    return {
        "amount_mxn": str(amount),
        "date": date(year, month, day).isoformat(),
        "user_id": USER,
    }


def _months_ago(n: int) -> tuple[int, int]:
    today = date.today()
    month = today.month - n
    year = today.year
    while month <= 0:
        month += 12
        year -= 1
    return year, month


# ── get_dashboard_summary ─────────────────────────────────────────────────

async def test_dashboard_totals_and_savings_rate(monkeypatch):
    _use(monkeypatch, FakeSupabase(
        expenses=[_expense(300, 2, CAT_FOOD), _expense(200, 10, CAT_RENT)],
        earnings=[_earning(1000, 1)],
        projected_costs=[],
        currencies=[{"id": CURRENCY_MXN, "exchange_rate": "1"}],
        categories=[{"id": CAT_FOOD, "name": "Food"}, {"id": CAT_RENT, "name": "Rent"}],
    ))

    result = await service.get_dashboard_summary(USER, 2026, 6)

    assert result["total_expenses"] == Decimal("500")
    assert result["total_income"] == Decimal("1000")
    assert result["net_balance"] == Decimal("500")
    # 500 saved out of 1000 earned
    assert result["savings_rate"] == Decimal("50.00")
    assert result["period_label"] == "Jun 2026"


async def test_dashboard_only_counts_the_month_asked_for(monkeypatch):
    """The date window is a filter, not a suggestion."""
    _use(monkeypatch, FakeSupabase(
        expenses=[
            _expense(100, 15, CAT_FOOD, month=6),
            _expense(999, 15, CAT_FOOD, month=5),   # before the window
            _expense(999, 15, CAT_FOOD, month=7),   # after it
        ],
        earnings=[], projected_costs=[], currencies=[], categories=[],
    ))

    result = await service.get_dashboard_summary(USER, 2026, 6)
    assert result["total_expenses"] == Decimal("100")


async def test_dashboard_reports_the_largest_expense_with_its_category(monkeypatch):
    _use(monkeypatch, FakeSupabase(
        expenses=[_expense(50, 1, CAT_FOOD), _expense(900, 2, CAT_RENT)],
        earnings=[], projected_costs=[], currencies=[],
        categories=[{"id": CAT_FOOD, "name": "Food"}, {"id": CAT_RENT, "name": "Rent"}],
    ))

    result = await service.get_dashboard_summary(USER, 2026, 6)
    assert result["largest_expense"] == Decimal("900")
    assert result["largest_category"] == "Rent"


async def test_dashboard_handles_an_expense_with_no_category(monkeypatch):
    _use(monkeypatch, FakeSupabase(
        expenses=[_expense(900, 2, None)],
        earnings=[], projected_costs=[], currencies=[], categories=[],
    ))

    result = await service.get_dashboard_summary(USER, 2026, 6)
    assert result["largest_category"] == "Uncategorized"


async def test_dashboard_empty_month_is_all_zeros_not_an_error(monkeypatch):
    _use(monkeypatch, FakeSupabase(
        expenses=[], earnings=[], projected_costs=[], currencies=[], categories=[],
    ))

    result = await service.get_dashboard_summary(USER, 2026, 6)
    assert result["total_expenses"] == 0
    assert result["total_income"] == 0
    assert result["savings_rate"] == Decimal("0")
    assert result["largest_expense"] is None
    assert result["largest_category"] is None


async def test_dashboard_savings_rate_goes_negative_when_overspending(monkeypatch):
    """
    Spending more than you earn gives a negative rate rather than a clamp.
    Recorded because the label says "savings rate" and -200% reads oddly in
    a progress ring, but the arithmetic is the honest answer.
    """
    _use(monkeypatch, FakeSupabase(
        expenses=[_expense(300, 2, CAT_FOOD)],
        earnings=[_earning(100, 1)],
        projected_costs=[], currencies=[],
        categories=[{"id": CAT_FOOD, "name": "Food"}],
    ))

    result = await service.get_dashboard_summary(USER, 2026, 6)
    assert result["net_balance"] == Decimal("-200")
    assert result["savings_rate"] == Decimal("-200.00")


async def test_dashboard_converts_weekly_projections_at_4_333333(monkeypatch):
    """
    A weekly cost is annualised as 52/12 weeks per month. The same constant
    appears in four separate functions, so pin it once here.
    """
    _use(monkeypatch, FakeSupabase(
        expenses=[], earnings=[],
        projected_costs=[
            {"amount": "100", "frequency": "monthly", "currency_id": CURRENCY_MXN,
             "month": None, "year": None, "user_id": USER, "is_active": True},
            {"amount": "100", "frequency": "weekly", "currency_id": CURRENCY_MXN,
             "month": None, "year": None, "user_id": USER, "is_active": True},
            {"amount": "500", "frequency": "one_time", "currency_id": CURRENCY_MXN,
             "month": 6, "year": 2026, "user_id": USER, "is_active": True},
        ],
        currencies=[{"id": CURRENCY_MXN, "exchange_rate": "1"}],
        categories=[],
    ))

    result = await service.get_dashboard_summary(USER, 2026, 6)
    # 100 monthly + 100 * 4.333333 weekly; the one_time cost is excluded
    assert result["projected_monthly"] == Decimal("533.33")


async def test_dashboard_ignores_inactive_projected_costs(monkeypatch):
    _use(monkeypatch, FakeSupabase(
        expenses=[], earnings=[],
        projected_costs=[
            {"amount": "100", "frequency": "monthly", "currency_id": CURRENCY_MXN,
             "month": None, "year": None, "user_id": USER, "is_active": False},
        ],
        currencies=[{"id": CURRENCY_MXN, "exchange_rate": "1"}],
        categories=[],
    ))

    result = await service.get_dashboard_summary(USER, 2026, 6)
    assert result["projected_monthly"] == Decimal("0")


# ── get_net_worth_history ─────────────────────────────────────────────────

async def test_net_worth_accumulates_month_on_month(monkeypatch):
    y2, m2 = _months_ago(2)
    y1, m1 = _months_ago(1)
    y0, m0 = _months_ago(0)

    _use(monkeypatch, FakeSupabase(
        earnings=[
            _earning(1000, 1, year=y2, month=m2),
            _earning(1000, 1, year=y1, month=m1),
            _earning(1000, 1, year=y0, month=m0),
        ],
        expenses=[
            _expense(400, 2, CAT_FOOD, year=y2, month=m2),
            _expense(400, 2, CAT_FOOD, year=y1, month=m1),
            _expense(400, 2, CAT_FOOD, year=y0, month=m0),
        ],
    ))

    result = await service.get_net_worth_history(USER, months_back=3)
    worths = [m["net_worth"] for m in result["months"]]

    assert worths == [Decimal("600"), Decimal("1200"), Decimal("1800")]
    assert result["current_worth"] == Decimal("1800")
    assert all(m["monthly_delta"] == Decimal("600") for m in result["months"])


# ── Known defects ─────────────────────────────────────────────────────────
# Each of the four below asserts the correct answer and fails today.

@pytest.mark.xfail(
    strict=True,
    reason="net worth ignores everything before the window: the queries have "
           "no lower bound, but the buckets are pre-seeded only for the "
           "months in range, so earlier rows are fetched and then dropped "
           "(analytics/service.py:892-907)",
)
async def test_net_worth_should_include_history_before_the_window(monkeypatch):
    """
    Someone with 50,000 saved over years, who then has a flat month, has a
    net worth of 50,000 — not 0.

    The function fetches every row ever written (lte end_date, no gte), so
    it pays the full cost of reading that history and then discards it,
    because `if key in monthly` only keeps months inside the window.
    """
    y0, _ = _months_ago(0)

    _use(monkeypatch, FakeSupabase(
        earnings=[_earning(50000, 1, year=y0 - 3, month=1)],   # long before
        expenses=[],
    ))

    result = await service.get_net_worth_history(USER, months_back=3)
    assert result["current_worth"] == Decimal("50000")


@pytest.mark.xfail(
    strict=True,
    reason="spending trends average over months the category did not exist, "
           "counting them as zero and dragging the average down "
           "(analytics/service.py:1082)",
)
async def test_spending_trend_average_should_ignore_months_with_no_data(monkeypatch):
    """
    A category created last month, with 500 spent in its only full month,
    has an average of 500 — not 100.

    past_values fills every month in range with Decimal("0") via
    monthly.get(m, 0), so four months of non-existence are averaged in. The
    average lands at a fifth of the truth and pct_vs_avg is inflated to
    match, which is what drives the up/down arrow on the dashboard.
    """
    y1, m1 = _months_ago(1)
    y0, m0 = _months_ago(0)

    _use(monkeypatch, FakeSupabase(
        expenses=[
            _expense(500, 1, CAT_FOOD, year=y1, month=m1),
            _expense(500, 1, CAT_FOOD, year=y0, month=m0),
        ],
        categories=[{"id": CAT_FOOD, "name": "Food", "color": "#FF0000"}],
    ))

    result = await service.get_spending_trends(USER, months_back=5)
    food = next(t for t in result["trends"] if t["category_id"] == CAT_FOOD)

    assert food["avg_monthly"] == Decimal("500.00")
    assert food["direction"] == "stable"


@pytest.mark.xfail(
    strict=True,
    reason="total_variance subtracts real spending over past months from "
           "projected spending over past AND future months "
           "(analytics/service.py:730-732, 748)",
)
async def test_projected_total_variance_should_compare_like_with_like(monkeypatch):
    """
    With 100/month projected and nothing actually spent, the variance over
    the three past months is -300.

    It reports -600, because total_projected accumulates across all six
    months in the response while total_real only accumulates across the
    three that have happened. The two totals cover different spans, so the
    difference between them does not describe anything.
    """
    _use(monkeypatch, FakeSupabase(
        projected_costs=[
            {"amount": "100", "frequency": "monthly", "currency_id": CURRENCY_MXN,
             "user_id": USER, "is_active": True},
        ],
        currencies=[{"id": CURRENCY_MXN, "exchange_rate": "1"}],
        expenses=[],
    ))

    result = await service.get_projected_analytics(USER, months_ahead=3, months_back=3)

    assert result["total_real"] == Decimal("0")
    assert result["total_variance"] == Decimal("-300")


@pytest.mark.xfail(
    strict=True,
    reason="a weekly projected cost with no day_of_week is added in full to "
           "every week of the month, so the weekly view and the monthly "
           "rollup of the same cost disagree (analytics/service.py:1289-1293)",
)
async def test_weekly_projection_should_match_the_monthly_rollup(monkeypatch):
    """
    One 500/week cost is 500 * 4.333333 = 2166.67 a month. The dashboard's
    monthly figure says exactly that.

    The weekly breakdown of the same month adds the full 500 to each week
    bucket, so a month spanning five weeks totals 2500 and one spanning four
    totals 2000. The same response disagrees with itself depending on which
    number the user reads.
    """
    _use(monkeypatch, FakeSupabase(
        expenses=[], earnings=[],
        projected_costs=[
            {"amount": "500", "frequency": "weekly", "currency_id": CURRENCY_MXN,
             "day_of_week": None, "day_of_month": None,
             "month": None, "year": None, "user_id": USER, "is_active": True},
        ],
        currencies=[{"id": CURRENCY_MXN, "exchange_rate": "1"}],
        categories=[], user_preferences=[],
    ))

    result = await service.get_dashboard_weekly(USER, 2026, 5, week_start_day=1)
    total = sum(Decimal(str(w["projected"])) for w in result["weeks"])

    assert total == Decimal("2166.67")
