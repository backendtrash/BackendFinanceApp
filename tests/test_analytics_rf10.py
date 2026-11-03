"""
The RF10 functions that had no calculation test when RF10 was reviewed
against E1 (docs/verificacion-RF09-RF10.md): monthly income vs expenses,
weekly cash flow, spending by category, budget progress and the comparison
with the same month a year before. Each is checked against rows whose
answer is known.
"""
from datetime import date, timedelta
from decimal import Decimal

from app.analytics import service
from app.database import bind_db
from fakes import FakeSupabase

USER = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"
FOOD = "22222222-2222-2222-2222-222222222222"
RENT = "33333333-3333-3333-3333-333333333333"
MXN = "11111111-1111-1111-1111-111111111111"


def _months_ago(n):
    t = date.today()
    m, y = t.month - n, t.year
    while m <= 0:
        m += 12
        y -= 1
    return y, m


def _move(amount, d, category=None, user=USER):
    iso = d.isocalendar()
    return {"amount_mxn": str(amount), "date": d.isoformat(), "category_id": category,
            "user_id": user, "week_number": iso.week, "week_year": iso.year}


# ── Monthly income vs expenses ────────────────────────────────────────────

async def test_monthly_analytics_buckets_by_month_and_counts_only_the_window():
    (y2, m2), (y1, m1), (y0, m0) = _months_ago(2), _months_ago(1), _months_ago(0)
    old_y, old_m = _months_ago(5)
    bind_db(FakeSupabase(
        expenses=[_move(300, date(y2, m2, 3)), _move(200, date(y0, m0, 1)),
                  _move(999, date(old_y, old_m, 3)), _move(999, date(y0, m0, 1), user=OTHER)],
        earnings=[_move(1000, date(y2, m2, 1)), _move(500, date(y0, m0, 1))],
        projected_costs=[], currencies=[],
    ))

    result = await service.get_monthly_analytics(USER, months_back=3)
    months = {(p["year"], p["month"]): p for p in result["months"]}

    assert list(months) == [(y2, m2), (y1, m1), (y0, m0)]
    assert months[(y2, m2)]["total_expenses"] == Decimal("300")
    assert months[(y2, m2)]["net_balance"] == Decimal("700")
    assert months[(y1, m1)]["total_income"] == months[(y1, m1)]["total_expenses"] == 0
    assert result["total_income"] == Decimal("1500")
    assert result["total_expenses"] == Decimal("500")
    assert result["net_balance"] == Decimal("1000")


async def test_monthly_analytics_projects_each_month_by_its_own_days():
    """A weekly cost is more in a 31-day month than in a 30-day one."""
    bind_db(FakeSupabase(
        expenses=[], earnings=[], currencies=[{"id": MXN, "exchange_rate": "1"}],
        projected_costs=[{"amount": "700", "frequency": "weekly", "currency_id": MXN,
                          "user_id": USER, "is_active": True}],
    ))

    result = await service.get_monthly_analytics(USER, months_back=12)

    import calendar
    for point in result["months"]:
        days = calendar.monthrange(point["year"], point["month"])[1]
        assert point["projected_monthly"] == Decimal(100 * days)
    assert result["projected_monthly"] == result["months"][-1]["projected_monthly"]


# ── Weekly cash flow ──────────────────────────────────────────────────────

async def test_weekly_analytics_groups_by_iso_week_in_order():
    today = date.today()
    this_week = today - timedelta(days=today.weekday())
    two_ago = this_week - timedelta(weeks=2)
    bind_db(FakeSupabase(
        expenses=[_move(100, this_week), _move(50, this_week + timedelta(days=1)),
                  _move(70, two_ago), _move(999, today - timedelta(weeks=20)),
                  _move(999, this_week, user=OTHER)],
        earnings=[_move(400, two_ago)],
    ))

    result = await service.get_weekly_analytics(USER, weeks_back=12)
    weeks = [(w["week_year"], w["week_number"]) for w in result["weeks"]]

    assert weeks == sorted(weeks)
    assert len(weeks) == 2                                  # the 20-week-old row is outside
    first, last = result["weeks"]
    assert (first["total_income"], first["total_expenses"]) == (Decimal("400"), Decimal("70"))
    assert last["total_expenses"] == Decimal("150")
    assert result["net_balance"] == Decimal("180")


# ── Spending by category ──────────────────────────────────────────────────

async def test_category_analytics_shares_and_order():
    bind_db(FakeSupabase(
        expenses=[_move(300, date(2026, 6, 2), FOOD), _move(100, date(2026, 6, 9), FOOD),
                  _move(600, date(2026, 6, 3), RENT), _move(1000, date(2026, 6, 4)),
                  _move(999, date(2026, 5, 31), RENT), _move(999, date(2026, 6, 3), RENT, user=OTHER)],
        categories=[{"id": FOOD, "name": "Food", "color": "#f00"},
                    {"id": RENT, "name": "Rent", "color": "#00f"}],
    ))

    result = await service.get_category_analytics(USER, year=2026, month=6)
    rows = result["categories"]

    assert result["total_expenses"] == Decimal("2000")
    assert [r["category_name"] for r in rows] == ["Uncategorized", "Rent", "Food"]
    assert [r["pct_of_total"] for r in rows] == [Decimal("50.00"), Decimal("30.00"), Decimal("20.00")]
    assert rows[0]["category_id"] is None
    assert rows[2]["transaction_count"] == 2


# ── Budget progress ───────────────────────────────────────────────────────

def _budget(bid, limit, category=None, period="monthly", active=True, user=USER):
    return {"id": bid, "user_id": user, "category_id": category, "period": period,
            "limit_amount": str(limit), "alert_threshold": 80, "is_active": active}


async def test_budget_progress_by_category_and_overall():
    today = date.today()
    last_month = today.replace(day=1) - timedelta(days=1)
    bind_db(FakeSupabase(
        budgets=[_budget("b-food", 500, FOOD), _budget("b-all", 1000),
                 _budget("b-off", 10, FOOD, active=False)],
        categories=[{"id": FOOD, "name": "Food", "color": "#f00"}],
        expenses=[_move(600, today.replace(day=1), FOOD), _move(150, today.replace(day=1)),
                  _move(999, last_month, FOOD), _move(999, today.replace(day=1), FOOD, user=OTHER)],
    ))

    result = await service.get_budget_progress_analytics(USER)
    by_id = {b["budget_id"]: b for b in result["budgets"]}

    assert set(by_id) == {"b-food", "b-all"}                 # the inactive one is left out
    food, overall = by_id["b-food"], by_id["b-all"]
    assert (food["spent_amount"], food["pct_spent"], food["is_over_budget"]) == (
        Decimal("600"), Decimal("120.00"), True)
    assert food["remaining"] == Decimal("-100")
    assert (overall["spent_amount"], overall["pct_spent"]) == (Decimal("750"), Decimal("75.00"))
    assert overall["category_name"] == "All Categories"
    assert [b["budget_id"] for b in result["budgets"]] == ["b-food", "b-all"]   # most critical first
    assert result["over_budget_count"] == 1
    assert (result["total_limit"], result["total_spent"]) == (Decimal("1500"), Decimal("1350"))


async def test_no_budgets_is_empty_not_an_error():
    bind_db(FakeSupabase(budgets=[], expenses=[], categories=[]))
    result = await service.get_budget_progress_analytics(USER)
    assert result["budgets"] == [] and result["over_budget_count"] == 0


# ── The same month a year before ──────────────────────────────────────────

async def test_year_over_year_compares_the_same_month():
    bind_db(FakeSupabase(
        expenses=[_move(500, date(2026, 6, 10)), _move(400, date(2025, 6, 10)),
                  _move(999, date(2025, 7, 1))],
        earnings=[_move(2000, date(2026, 6, 1)), _move(1000, date(2025, 6, 1))],
    ))

    result = await service.get_year_over_year(USER, 2026, 6)

    assert result["current"] == {"income": Decimal("2000"), "expenses": Decimal("500"),
                                 "balance": Decimal("1500")}
    assert result["previous"]["expenses"] == Decimal("400")
    assert result["changes"] == {"income": Decimal("100.0"), "expenses": Decimal("25.0"),
                                 "balance": Decimal("150.0")}


async def test_year_over_year_with_nothing_a_year_before_reports_no_change():
    bind_db(FakeSupabase(expenses=[_move(500, date(2026, 6, 10))], earnings=[]))
    result = await service.get_year_over_year(USER, 2026, 6)
    assert result["changes"]["expenses"] == Decimal("0")
