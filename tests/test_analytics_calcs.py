"""
The analytics arithmetic, checked against known inputs.

This is the cover for risk R4 — "the analytics numbers are wrong and nobody
notices". The dashboard is the most-read surface in the product and the
least verifiable by eye: every figure is a Decimal sum over rows the user
cannot see, so a wrong total looks exactly like a right one.

Two tests at the end are marked xfail. They are not scaffolding. Each
encodes the value the function should return, fails against what it returns
today, and names the defect. strict=True means they flip to failures the
moment a fix lands, so none can be quietly forgotten.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.analytics import service
from app.database import bind_db
from fakes import FakeSupabase


CURRENCY_MXN = "11111111-1111-1111-1111-111111111111"
CAT_FOOD = "22222222-2222-2222-2222-222222222222"
CAT_RENT = "33333333-3333-3333-3333-333333333333"
USER = "00000000-0000-0000-0000-000000000001"


def _use(monkeypatch, fake: FakeSupabase) -> FakeSupabase:
    # Services read their client through db(). Each async test runs in its
    # own task, so a binding made here is visible to the service calls the
    # test awaits and cannot leak into the next test.
    bind_db(fake)
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


async def test_net_worth_includes_history_before_the_window(monkeypatch):
    """
    Defect 7. Someone with 50,000 saved over years, who then has a flat
    month, has a net worth of 50,000 — not 0.

    It used to fetch every row ever written (no lower bound), then drop the
    ones before the window and start the running total at zero.
    """
    y0, _ = _months_ago(0)

    _use(monkeypatch, FakeSupabase(
        earnings=[_earning(50000, 1, year=y0 - 3, month=1)],   # long before
        expenses=[],
    ))

    result = await service.get_net_worth_history(USER, months_back=3)
    assert result["current_worth"] == Decimal("50000")
    assert result["opening_balance"] == Decimal("50000")


async def test_net_worth_starts_at_the_opening_balance_and_reads_only_the_window(monkeypatch):
    """
    The opening balance nets earlier income against earlier spending, and
    the window's months add to it. The history itself is summed in the
    database: the row queries carry a lower bound, so an old account does
    not mean reading every row it ever had.
    """
    y2, m2 = _months_ago(2)
    y1, m1 = _months_ago(1)
    y0, m0 = _months_ago(0)

    fake = _use(monkeypatch, FakeSupabase(
        earnings=[
            _earning(50000, 1, year=y0 - 3, month=1),
            _earning(1000, 1, year=y2, month=m2),
            _earning(1000, 1, year=y1, month=m1),
            _earning(1000, 1, year=y0, month=m0),
        ],
        expenses=[
            _expense(20000, 1, CAT_RENT, year=y0 - 2, month=1),
            _expense(400, 2, CAT_FOOD, year=y2, month=m2),
            _expense(400, 2, CAT_FOOD, year=y1, month=m1),
            _expense(400, 2, CAT_FOOD, year=y0, month=m0),
        ],
    ))

    result = await service.get_net_worth_history(USER, months_back=3)

    assert result["opening_balance"] == Decimal("30000")
    assert [m["net_worth"] for m in result["months"]] == [
        Decimal("30600"), Decimal("31200"), Decimal("31800"),
    ]
    window_start = date(y2, m2, 1).isoformat()
    for table in ("earnings", "expenses"):
        assert ("gte", "date", window_start) in fake.filters_for(table)[0]


# ── get_spending_trends ───────────────────────────────────────────────────

def _food_trend(result):
    return next(t for t in result["trends"] if t["category_id"] == CAT_FOOD)


async def test_spending_trend_averages_from_the_category_first_month(monkeypatch):
    """
    Defect 8. A category first used last month, with 500 spent in its only
    full month, has an average of 500.

    It used to report 125: with months_back=5 there are four past months,
    and the three before the category existed counted as zeros. The
    current month's 500 then read as +300% and the arrow said "up" for
    spending that is flat.
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

    food = _food_trend(await service.get_spending_trends(USER, months_back=5))

    assert food["avg_monthly"] == Decimal("500.00")
    assert food["direction"] == "stable"


async def test_spending_trend_counts_a_month_without_spending_after_the_first(monkeypatch):
    """
    Option A, not B: a month with no spending after the category's first
    expense is a real zero, and stays in the average.

    600, nothing, 600 → 400. Ignoring the empty month would give 600; the
    old code, counting the month before the first expense too, gave 300.
    """
    y3, m3 = _months_ago(3)
    y1, m1 = _months_ago(1)
    y0, m0 = _months_ago(0)

    _use(monkeypatch, FakeSupabase(
        expenses=[
            _expense(600, 1, CAT_FOOD, year=y3, month=m3),
            _expense(600, 1, CAT_FOOD, year=y1, month=m1),
            _expense(400, 1, CAT_FOOD, year=y0, month=m0),
        ],
        categories=[{"id": CAT_FOOD, "name": "Food", "color": "#FF0000"}],
    ))

    food = _food_trend(await service.get_spending_trends(USER, months_back=5))

    assert food["avg_monthly"] == Decimal("400.00")
    assert food["direction"] == "stable"


async def test_spending_trend_uses_the_whole_window_for_an_older_category(monkeypatch):
    """
    A category first used before the window averages over every past month
    of the window, empty ones included. The expense a year ago only says
    when the category started; its amount is outside the window.
    """
    y12, m12 = _months_ago(12)
    y1, m1 = _months_ago(1)
    y0, m0 = _months_ago(0)

    _use(monkeypatch, FakeSupabase(
        expenses=[
            _expense(9999, 1, CAT_FOOD, year=y12, month=m12),
            _expense(400, 1, CAT_FOOD, year=y1, month=m1),
            _expense(100, 1, CAT_FOOD, year=y0, month=m0),
        ],
        categories=[{"id": CAT_FOOD, "name": "Food", "color": "#FF0000"}],
    ))

    food = _food_trend(await service.get_spending_trends(USER, months_back=5))

    # 400 over the four past months
    assert food["avg_monthly"] == Decimal("100.00")
    assert food["current_month"] == Decimal("100.00")
    assert food["direction"] == "stable"


async def test_spending_trend_for_a_category_first_used_this_month(monkeypatch):
    """No past months to average: the average is 0 and the trend stable."""
    y0, m0 = _months_ago(0)

    _use(monkeypatch, FakeSupabase(
        expenses=[_expense(300, 1, CAT_FOOD, year=y0, month=m0)],
        categories=[{"id": CAT_FOOD, "name": "Food", "color": "#FF0000"}],
    ))

    food = _food_trend(await service.get_spending_trends(USER, months_back=5))

    assert food["avg_monthly"] == Decimal("0")
    assert food["direction"] == "stable"


async def test_spending_trend_treats_uncategorized_expenses_as_one_category(monkeypatch):
    """Expenses with no category share one first month, from the same function."""
    y2, m2 = _months_ago(2)
    y0, m0 = _months_ago(0)

    _use(monkeypatch, FakeSupabase(
        expenses=[
            _expense(300, 1, None, year=y2, month=m2),
            _expense(100, 1, None, year=y0, month=m0),
        ],
        categories=[],
    ))

    result = await service.get_spending_trends(USER, months_back=5)
    other = next(t for t in result["trends"] if t["category_id"] == "uncategorized")

    # 300 and an empty month since its first use → 150
    assert other["avg_monthly"] == Decimal("150.00")
    assert other["category_name"] == "Uncategorized"


# ── Known defects ─────────────────────────────────────────────────────────
# Each of the two below asserts the correct answer and fails today.


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
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
    raises=AssertionError,
    reason="a weekly projected cost with no day_of_week is added in full to "
           "every week of the month, so the weekly view and the monthly "
           "rollup of the same cost disagree (analytics/service.py:1289-1293)",
)
async def test_weekly_projection_should_match_the_monthly_rollup(monkeypatch):
    """
    One 500/week cost is 500 * 4.333333 = 2166.67 a month, and that is what
    the response's own projected_monthly says.

    The weekly breakdown of the same month adds the full 500 to each week
    bucket. May 2026 has five buckets, so they total 2500. The same response
    disagrees with itself depending on which number the user reads.

    This test used to read a key named "projected", which does not exist —
    the field is projected_weekly — so it raised KeyError and the xfail
    swallowed it. It never checked the defect. raises=AssertionError on the
    marker now means an xfail only counts when the assertion itself fails.
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
    weekly_total = sum(Decimal(str(w["projected_weekly"])) for w in result["weeks"])
    monthly = round(Decimal(str(result["projected_monthly"])), 2)

    assert monthly == Decimal("2166.67"), "precondition: the monthly figure"
    assert weekly_total == monthly
