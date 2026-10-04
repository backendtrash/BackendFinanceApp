from decimal import Decimal
from datetime import date, timedelta
from typing import Optional
import calendar
import logging

from app.database import supabase_admin

# ── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ── Month label helper ────────────────────────────────────────────────────
MONTH_NAMES = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
]


def month_label(year: int, month: int) -> str:
    """Formats a year+month into a readable label e.g. 'Jan 2025'."""
    return f"{MONTH_NAMES[month]} {year}"


def get_month_range(months_back: int) -> list[tuple[int, int]]:
    """
    Returns a list of (year, month) tuples for the last N months.
    Ordered chronologically from oldest to most recent.

    Example: months_back=3, today=March 2025
    Returns: [(2024,12), (2025,1), (2025,2), (2025,3)]
    """
    today   = date.today()
    result  = []
    year    = today.year
    month   = today.month

    for _ in range(months_back):
        result.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1

    # Reverse to get chronological order (oldest first)
    return list(reversed(result))


async def get_dashboard_summary(
    user_id: str,
    year: int,
    month: int,
) -> dict:
    """
    Calculates summary card data for a specific month.

    Returns total income, total expenses, net balance,
    savings rate, largest expense amount and its category.
    All amounts in MXN.
    """
    first_day = date(year, month, 1)
    last_day  = date(year, month, calendar.monthrange(year, month)[1])

    # ── Fetch expenses for the month ──────────────────────────────────────
    exp_result = (
        supabase_admin
        .table("expenses")
        .select("amount_mxn, category_id")
        .eq("user_id", user_id)
        .gte("date", first_day.isoformat())
        .lte("date", last_day.isoformat())
        .execute()
    )

    # ── Fetch earnings for the month ──────────────────────────────────────
    # No exclusions needed — goal contributions are now expenses
    # not earnings, so all earnings count toward income
    inc_result = (
        supabase_admin
        .table("earnings")
        .select("amount_mxn")
        .eq("user_id", user_id)
        .gte("date", first_day.isoformat())
        .lte("date", last_day.isoformat())
        .execute()
    )

    expenses = exp_result.data or []
    earnings = inc_result.data or []

    total_expenses = sum(
        Decimal(str(e["amount_mxn"])) for e in expenses
    )
    total_income = sum(
        Decimal(str(e["amount_mxn"])) for e in earnings
    )

    net_balance  = total_income - total_expenses
    savings_rate = (
        round((net_balance / total_income) * 100, 2)
        if total_income > 0
        else Decimal("0")
    )

    # ── Find largest expense and its category ─────────────────────────────
    largest_expense  = Decimal("0")
    largest_cat_id   = None

    for exp in expenses:
        amount = Decimal(str(exp["amount_mxn"]))
        if amount > largest_expense:
            largest_expense = amount
            largest_cat_id  = exp.get("category_id")

    # Resolve category name if exists
    largest_category = "Uncategorized"
    if largest_cat_id:
        cat_result = (
            supabase_admin
            .table("categories")
            .select("name")
            .eq("id", largest_cat_id)
            .single()
            .execute()
        )
        if cat_result.data:
            largest_category = cat_result.data["name"]

    # ── Calculate projected monthly expenses from recurring rules ──────────
    # Use projected_costs table instead of recurring rules
    # Projected costs are explicit forecasts, not transaction generators
    costs_result = (
        supabase_admin
        .table("projected_costs")
        .select("amount, frequency, currency_id, month, year")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .execute()
    )

    currencies_result = (
        supabase_admin
        .table("currencies")
        .select("id, exchange_rate")
        .execute()
    )
    currency_map = {
        c["id"]: Decimal(str(c["exchange_rate"]))
        for c in (currencies_result.data or [])
    }

    WEEKLY_PER_MONTH  = Decimal("4.333333")
    projected_monthly = Decimal("0")

    for cost in (costs_result.data or []):
        rate   = currency_map.get(cost.get("currency_id"), Decimal("1"))
        amount = Decimal(str(cost["amount"])) * rate
        freq   = cost["frequency"]

        if freq == "monthly":
            projected_monthly += amount
        elif freq == "weekly":
            projected_monthly += amount * WEEKLY_PER_MONTH
        # one_time costs are not included in monthly projection average

    return {
        "period_label":       month_label(year, month),
        "total_income":       total_income,
        "total_expenses":     total_expenses,
        "net_balance":        net_balance,
        "savings_rate":       savings_rate,
        "largest_expense":    largest_expense if largest_expense > 0 else None,
        "largest_category":   largest_category if largest_expense > 0 else None,
        "projected_monthly":  round(projected_monthly, 2),
        "vs_projected":       round(total_expenses - projected_monthly, 2),
    }


async def _get_carry_forward_notes(prev_year: int, prev_month: int) -> str:
    return f"Carry-forward · {month_label(prev_year, prev_month)}"


async def _check_carry_forward_applied(user_id: str, year: int, month: int, notes_key: str) -> bool:
    first_day = date(year, month, 1)
    last_day  = date(year, month, calendar.monthrange(year, month)[1])

    earn_check = (
        supabase_admin.table("earnings")
        .select("id")
        .eq("user_id", user_id)
        .eq("notes", notes_key)
        .gte("date", first_day.isoformat())
        .lte("date", last_day.isoformat())
        .execute()
    )
    exp_check = (
        supabase_admin.table("expenses")
        .select("id")
        .eq("user_id", user_id)
        .eq("notes", notes_key)
        .gte("date", first_day.isoformat())
        .lte("date", last_day.isoformat())
        .execute()
    )
    return bool(earn_check.data) or bool(exp_check.data)


async def get_carry_forward_status(user_id: str, year: int, month: int) -> dict:
    """Returns carry-forward status for a month without creating any entry."""
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    prev_summary = await get_dashboard_summary(user_id, prev_year, prev_month)
    balance      = prev_summary["net_balance"]
    notes_key    = await _get_carry_forward_notes(prev_year, prev_month)
    applied      = await _check_carry_forward_applied(user_id, year, month, notes_key)

    if balance > 0:
        entry_type = "income"
    elif balance < 0:
        entry_type = "expense"
    else:
        entry_type = "none"

    return {
        "source_period": month_label(prev_year, prev_month),
        "balance":       balance,
        "entry_type":    entry_type,
        "applied":       applied if balance != 0 else True,
    }


async def apply_carry_forward(user_id: str, year: int, month: int) -> dict:
    """
    Idempotent: creates a carry-forward income/expense entry for the target
    month if the previous month had a non-zero net balance and the entry
    does not already exist.
    """
    status = await get_carry_forward_status(user_id, year, month)
    balance   = status["balance"]
    notes_key = await _get_carry_forward_notes(
        year - 1 if month == 1 else year,
        12       if month == 1 else month - 1,
    )

    if status["applied"] or balance == 0:
        return status

    # Fetch MXN currency id
    mxn_result = (
        supabase_admin.table("currencies")
        .select("id")
        .eq("code", "MXN")
        .execute()
    )
    if not mxn_result.data:
        return {**status, "applied": False}

    mxn_id    = mxn_result.data[0]["id"]
    first_day = date(year, month, 1).isoformat()

    if balance > 0:
        supabase_admin.table("earnings").insert({
            "user_id":      user_id,
            "amount":       str(balance),
            "currency_id":  mxn_id,
            "amount_mxn":   str(balance),
            "date":         first_day,
            "notes":        notes_key,
            "is_recurring": False,
        }).execute()
    else:
        abs_balance = abs(balance)
        supabase_admin.table("expenses").insert({
            "user_id":      user_id,
            "amount":       str(abs_balance),
            "currency_id":  mxn_id,
            "amount_mxn":   str(abs_balance),
            "date":         first_day,
            "notes":        notes_key,
            "is_recurring": False,
        }).execute()

    return {**status, "applied": True}


async def get_monthly_analytics(
    user_id: str,
    months_back: int = 12,
) -> dict:
    """
    Calculates monthly income vs expenses for the last N months.

    Fetches all expenses and earnings in the date range once,
    then aggregates in Python by month — avoids N separate DB queries.
    One bulk fetch is always faster than N individual queries.
    """
    month_range = get_month_range(months_back)
    first_month = month_range[0]
    last_month  = month_range[-1]

    start_date = date(first_month[0], first_month[1], 1)
    end_date   = date(
        last_month[0],
        last_month[1],
        calendar.monthrange(last_month[0], last_month[1])[1]
    )

    # ── Single bulk fetch for all expenses in range ───────────────────────
    exp_result = (
        supabase_admin
        .table("expenses")
        .select("amount_mxn, date")
        .eq("user_id", user_id)
        .gte("date", start_date.isoformat())
        .lte("date", end_date.isoformat())
        .execute()
    )

    # ── Fetch earnings for the period ─────────────────────────────────────
    inc_result = (
        supabase_admin
        .table("earnings")
        .select("amount_mxn, date")
        .eq("user_id", user_id)
        .gte("date", start_date.isoformat())
        .lte("date", end_date.isoformat())
        .execute()
    )

    expenses = exp_result.data or []
    earnings = inc_result.data or []

    # ── Aggregate by month in Python ──────────────────────────────────────
    # Initialize all months with zero values
    monthly: dict = {
        (y, m): {"income": Decimal("0"), "expenses": Decimal("0")}
        for y, m in month_range
    }

    for exp in expenses:
        d      = date.fromisoformat(exp["date"])
        key    = (d.year, d.month)
        if key in monthly:
            monthly[key]["expenses"] += Decimal(str(exp["amount_mxn"]))

    for inc in earnings:
        d      = date.fromisoformat(inc["date"])
        key    = (d.year, d.month)
        if key in monthly:
            monthly[key]["income"] += Decimal(str(inc["amount_mxn"]))

    # ── Build response data points ────────────────────────────────────────
    data_points = []
    total_income    = Decimal("0")
    total_expenses  = Decimal("0")

    for year, month in month_range:
        income   = round(monthly[(year, month)]["income"],   2)
        expenses = round(monthly[(year, month)]["expenses"], 2)
        balance  = income - expenses

        total_income   += income
        total_expenses += expenses

        data_points.append({
            "month_label":    month_label(year, month),
            "year":           year,
            "month":          month,
            "total_income":   income,
            "total_expenses": expenses,
            "net_balance":    balance,
        })

    # ── Calculate projected monthly from recurring rules ──────────────────
    # Use projected_costs table instead of recurring rules
    # Projected costs are explicit forecasts, not transaction generators
    costs_result = (
        supabase_admin
        .table("projected_costs")
        .select("amount, frequency, currency_id, month, year")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .execute()
    )

    currencies_result = (
        supabase_admin
        .table("currencies")
        .select("id, exchange_rate")
        .execute()
    )
    currency_map = {
        c["id"]: Decimal(str(c["exchange_rate"]))
        for c in (currencies_result.data or [])
    }

    WEEKLY_PER_MONTH  = Decimal("4.333333")
    projected_monthly = Decimal("0")

    for cost in (costs_result.data or []):
        rate   = currency_map.get(cost.get("currency_id"), Decimal("1"))
        amount = Decimal(str(cost["amount"])) * rate
        freq   = cost["frequency"]

        if freq == "monthly":
            projected_monthly += amount
        elif freq == "weekly":
            projected_monthly += amount * WEEKLY_PER_MONTH
        # one_time costs are not included in monthly projection average

    projected_monthly = round(projected_monthly, 2)

    # Add projected to each month data point
    today = date.today()
    for point in data_points:
        point["projected_monthly"] = str(projected_monthly)

    return {
        "months":             data_points,
        "total_income":       round(total_income,   2),
        "total_expenses":     round(total_expenses, 2),
        "net_balance":        round(total_income - total_expenses, 2),
        "period_months":      months_back,
        "projected_monthly":  projected_monthly,
    }


async def get_weekly_analytics(
    user_id: str,
    weeks_back: int = 12,
) -> dict:
    """
    Calculates weekly income vs expenses for the last N weeks.
    Uses week_number + week_year generated columns for fast grouping.
    """
    today      = date.today()
    start_date = today - timedelta(weeks=weeks_back)

    # ── Bulk fetch expenses and earnings in range ─────────────────────────
    exp_result = (
        supabase_admin
        .table("expenses")
        .select("amount_mxn, week_number, week_year")
        .eq("user_id", user_id)
        .gte("date", start_date.isoformat())
        .execute()
    )

    # ── Fetch earnings for the period ─────────────────────────────────────
    inc_result = (
        supabase_admin
        .table("earnings")
        .select("amount_mxn, week_number, week_year")
        .eq("user_id", user_id)
        .gte("date", start_date.isoformat())
        .execute()
    )

    expenses = exp_result.data or []
    earnings = inc_result.data or []

    # ── Aggregate by week ─────────────────────────────────────────────────
    weekly: dict = {}

    for exp in expenses:
        key = (exp["week_year"], exp["week_number"])
        if key not in weekly:
            weekly[key] = {"income": Decimal("0"), "expenses": Decimal("0")}
        weekly[key]["expenses"] += Decimal(str(exp["amount_mxn"]))

    for inc in earnings:
        key = (inc["week_year"], inc["week_number"])
        if key not in weekly:
            weekly[key] = {"income": Decimal("0"), "expenses": Decimal("0")}
        weekly[key]["income"] += Decimal(str(inc["amount_mxn"]))

    # ── Build response sorted chronologically ─────────────────────────────
    data_points     = []
    total_income    = Decimal("0")
    total_expenses  = Decimal("0")

    for (week_year, week_number), values in sorted(weekly.items()):
        income   = round(values["income"],   2)
        expenses = round(values["expenses"], 2)
        balance  = income - expenses

        total_income   += income
        total_expenses += expenses

        data_points.append({
            "week_label":     f"W{week_number:02d} {week_year}",
            "week_number":    week_number,
            "week_year":      week_year,
            "total_income":   income,
            "total_expenses": expenses,
            "net_balance":    balance,
        })

    return {
        "weeks":          data_points,
        "total_income":   round(total_income,   2),
        "total_expenses": round(total_expenses, 2),
        "net_balance":    round(total_income - total_expenses, 2),
    }


async def get_category_analytics(
    user_id: str,
    months_back: int = 1,
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> dict:
    """
    Calculates expense breakdown by category for a given period.
    Fetches all category names in one query to avoid N+1 queries.
    Sorts by total_amount descending so largest categories appear first.
    """
    today = date.today()
    year  = year  or today.year
    month = month or today.month

    first_day = date(year, month, 1)
    last_day  = date(
        year, month,
        calendar.monthrange(year, month)[1]
    )

    # ── Fetch expenses with category_id ───────────────────────────────────
    exp_result = (
        supabase_admin
        .table("expenses")
        .select("amount_mxn, category_id")
        .eq("user_id", user_id)
        .gte("date", first_day.isoformat())
        .lte("date", last_day.isoformat())
        .execute()
    )

    expenses = exp_result.data or []

    # ── Aggregate by category ─────────────────────────────────────────────
    category_totals: dict = {}

    for exp in expenses:
        cat_id  = exp.get("category_id") or "uncategorized"
        amount  = Decimal(str(exp["amount_mxn"]))

        if cat_id not in category_totals:
            category_totals[cat_id] = {
                "total": Decimal("0"),
                "count": 0,
            }

        category_totals[cat_id]["total"] += amount
        category_totals[cat_id]["count"] += 1

    total_expenses = sum(v["total"] for v in category_totals.values())

    # ── Fetch all category names in one query — avoids N+1 ───────────────
    cat_ids = [
        cid for cid in category_totals.keys()
        if cid != "uncategorized"
    ]

    category_map: dict = {}

    if cat_ids:
        cat_result = (
            supabase_admin
            .table("categories")
            .select("id, name, color")
            .in_("id", cat_ids)
            .execute()
        )
        for cat in (cat_result.data or []):
            category_map[cat["id"]] = cat

    # ── Build response sorted by amount descending ────────────────────────
    data_points = []

    for cat_id, values in sorted(
        category_totals.items(),
        key=lambda x: x[1]["total"],
        reverse=True,
    ):
        cat_info = category_map.get(cat_id, {})
        pct = (
            round(values["total"] / total_expenses * 100, 2)
            if total_expenses > 0
            else Decimal("0")
        )

        data_points.append({
            "category_id":        cat_id if cat_id != "uncategorized" else None,
            "category_name":      cat_info.get("name", "Uncategorized"),
            "color":              cat_info.get("color", "#6B7280"),
            "total_amount":       round(values["total"], 2),
            "pct_of_total":       pct,
            "transaction_count":  values["count"],
        })

    return {
        "categories":     data_points,
        "total_expenses": round(total_expenses, 2),
        "period_label":   month_label(year, month),
    }


async def get_projected_analytics(
    user_id: str,
    months_ahead: int = 3,
    months_back: int = 3,
) -> dict:
    """
    Compares projected spending (from recurring rules) vs real spending.

    Past months:   shows real expenses vs what recurring rules projected
    Future months: shows only projected amounts from active recurring rules

    Projection logic:
      For each active recurring rule with type=expense:
        - Calculate how many times it fires per month based on frequency
        - weekly:  ~4.33 times per month (52 weeks / 12 months)
        - monthly: exactly 1 time per month
        - Sum all rule amounts → projected monthly expense
    """
    today       = date.today()
    past_range  = get_month_range(months_back)
    future_months = []

    # Build future months list
    year  = today.year
    month = today.month
    for _ in range(months_ahead):
        month += 1
        if month > 12:
            month = 1
            year += 1
        future_months.append((year, month))

    all_months = past_range + future_months

    # ── Fetch projected costs instead of recurring rules ──────────────────
    # Projected costs are explicit forecasts — not transaction generators
    costs_result = (
        supabase_admin
        .table("projected_costs")
        .select("amount, frequency, currency_id")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .execute()
    )

    costs = costs_result.data or []

    # ── Fetch all currencies once ─────────────────────────────────────────
    currencies_result = (
        supabase_admin
        .table("currencies")
        .select("id, exchange_rate")
        .execute()
    )
    currency_map = {
        c["id"]: Decimal(str(c["exchange_rate"]))
        for c in (currencies_result.data or [])
    }

    WEEKLY_PER_MONTH  = Decimal("4.333333")
    monthly_projected = Decimal("0")

    for cost in costs:
        rate   = currency_map.get(cost.get("currency_id"), Decimal("1"))
        amount = Decimal(str(cost["amount"])) * rate
        freq   = cost["frequency"]

        if freq == "monthly":
            monthly_projected += amount
        elif freq == "weekly":
            monthly_projected += amount * WEEKLY_PER_MONTH
        # one_time excluded from monthly average projection

    monthly_projected = round(monthly_projected, 2)

    # ── Fetch real expenses for past months ───────────────────────────────
    if past_range:
        first_past = past_range[0]
        last_past  = past_range[-1]
        start_date = date(first_past[0], first_past[1], 1)
        end_date   = date(
            last_past[0], last_past[1],
            calendar.monthrange(last_past[0], last_past[1])[1]
        )

        real_result = (
            supabase_admin
            .table("expenses")
            .select("amount_mxn, date")
            .eq("user_id", user_id)
            .gte("date", start_date.isoformat())
            .lte("date", end_date.isoformat())
            .execute()
        )

        real_expenses = real_result.data or []
    else:
        real_expenses = []

    # ── Aggregate real expenses by month ──────────────────────────────────
    real_by_month: dict = {(y, m): Decimal("0") for y, m in past_range}

    for exp in real_expenses:
        d   = date.fromisoformat(exp["date"])
        key = (d.year, d.month)
        if key in real_by_month:
            real_by_month[key] += Decimal(str(exp["amount_mxn"]))

    # ── Build response data points ────────────────────────────────────────
    data_points     = []
    total_projected = Decimal("0")
    total_real      = Decimal("0")

    for year, month in all_months:
        is_future = (year, month) > (today.year, today.month)
        real      = round(real_by_month.get((year, month), Decimal("0")), 2)
        projected = monthly_projected
        variance  = real - projected if not is_future else Decimal("0")

        total_projected += projected
        if not is_future:
            total_real += real

        data_points.append({
            "month_label":      month_label(year, month),
            "year":             year,
            "month":            month,
            "projected_amount": projected,
            "real_amount":      real,
            "variance":         round(variance, 2),
            "is_future":        is_future,
        })

    return {
        "months":                data_points,
        "total_projected":       round(total_projected,   2),
        "total_real":            round(total_real,        2),
        "total_variance":        round(total_real - total_projected, 2),
        "avg_monthly_projected": monthly_projected,
    }


async def get_budget_progress_analytics(user_id: str) -> dict:
    """
    Returns all active budgets with spending progress for the current period.
    Joins with categories to get names and colors for display.
    Flags budgets that are over their limit.
    """
    # ── Fetch active budgets ──────────────────────────────────────────────
    budgets_result = (
        supabase_admin
        .table("budgets")
        .select("*")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .execute()
    )

    budgets = budgets_result.data or []

    if not budgets:
        return {
            "budgets":          [],
            "total_limit":      Decimal("0"),
            "total_spent":      Decimal("0"),
            "over_budget_count": 0,
        }

    # ── Fetch all relevant categories in one query ────────────────────────
    cat_ids = [
        b["category_id"] for b in budgets
        if b.get("category_id")
    ]

    category_map: dict = {}

    if cat_ids:
        cat_result = (
            supabase_admin
            .table("categories")
            .select("id, name, color")
            .in_("id", cat_ids)
            .execute()
        )
        for cat in (cat_result.data or []):
            category_map[cat["id"]] = cat

    # ── Calculate spending for each budget ────────────────────────────────
    from app.budgets.service import calculate_spent_amount

    items         = []
    total_limit   = Decimal("0")
    total_spent   = Decimal("0")
    over_budget   = 0

    for budget in budgets:
        cat_id   = budget.get("category_id")
        cat_info = category_map.get(cat_id, {}) if cat_id else {}

        spent = await calculate_spent_amount(
            user_id=user_id,
            category_id=cat_id,
            period=budget["period"],
        )

        limit      = Decimal(str(budget["limit_amount"]))
        pct_spent  = round(spent / limit * 100, 2) if limit > 0 else Decimal("0")
        remaining  = round(limit - spent, 2)
        is_over    = spent > limit

        total_limit += limit
        total_spent += spent

        if is_over:
            over_budget += 1

        items.append({
            "budget_id":       budget["id"],
            "category_name":   cat_info.get("name", "All Categories"),
            "color":           cat_info.get("color", "#6366F1"),
            "period":          budget["period"],
            "limit_amount":    limit,
            "spent_amount":    round(spent, 2),
            "pct_spent":       pct_spent,
            "remaining":       remaining,
            "alert_threshold": budget["alert_threshold"],
            "is_over_budget":  is_over,
        })

    # Sort by pct_spent descending — most critical budgets first
    items.sort(key=lambda x: x["pct_spent"], reverse=True)

    return {
        "budgets":           items,
        "total_limit":       round(total_limit, 2),
        "total_spent":       round(total_spent, 2),
        "over_budget_count": over_budget,
    }

async def get_net_worth_history(
    user_id:     str,
    months_back: int = 12,
) -> dict:
    """
    Calculates cumulative net worth month by month.

    Net worth at month M = sum of all earnings - sum of all expenses
    from the beginning of time up to end of month M.

    This shows wealth accumulation trajectory — not just monthly cash flow.
    A positive slope means the user is building wealth.
    """
    month_range = get_month_range(months_back)
    last_month  = month_range[-1]

    end_date = date(
        last_month[0],
        last_month[1],
        calendar.monthrange(last_month[0], last_month[1])[1]
    )

    # Fetch ALL earnings and expenses up to end of period
    all_earnings = (
        supabase_admin
        .table("earnings")
        .select("amount_mxn, date")
        .eq("user_id", user_id)
        .lte("date", end_date.isoformat())
        .execute()
    ).data or []

    all_expenses = (
        supabase_admin
        .table("expenses")
        .select("amount_mxn, date")
        .eq("user_id", user_id)
        .lte("date", end_date.isoformat())
        .execute()
    ).data or []

    # Aggregate by month
    monthly: dict = {
        (y, m): {"income": Decimal("0"), "expenses": Decimal("0")}
        for y, m in month_range
    }

    for e in all_earnings:
        d   = date.fromisoformat(e["date"])
        key = (d.year, d.month)
        if key in monthly:
            monthly[key]["income"] += Decimal(str(e["amount_mxn"]))

    for e in all_expenses:
        d   = date.fromisoformat(e["date"])
        key = (d.year, d.month)
        if key in monthly:
            monthly[key]["expenses"] += Decimal(str(e["amount_mxn"]))

    # Build cumulative net worth
    data_points      = []
    cumulative       = Decimal("0")

    for y, m in month_range:
        income   = monthly[(y, m)]["income"]
        expenses = monthly[(y, m)]["expenses"]
        cumulative += income - expenses

        data_points.append({
            "month_label": month_label(y, m),
            "year":        y,
            "month":       m,
            "net_worth":   round(cumulative, 2),
            "monthly_delta": round(income - expenses, 2),
        })

    return {
        "months":          data_points,
        "current_worth":   data_points[-1]["net_worth"] if data_points else Decimal("0"),
        "period_months":   months_back,
    }

async def get_year_over_year(
    user_id: str,
    year:    int,
    month:   int,
) -> dict:
    """
    Compares the same month across two consecutive years.
    Shows income, expenses, and net balance for:
      - This year's month
      - Last year's same month
      - % change for each metric
    """
    prev_year = year - 1

    async def fetch_month(y: int, m: int) -> dict:
        first = date(y, m, 1)
        last  = date(y, m, calendar.monthrange(y, m)[1])

        inc = (
            supabase_admin
            .table("earnings")
            .select("amount_mxn")
            .eq("user_id", user_id)
            .gte("date", first.isoformat())
            .lte("date", last.isoformat())
            .execute()
        ).data or []

        exp = (
            supabase_admin
            .table("expenses")
            .select("amount_mxn")
            .eq("user_id", user_id)
            .gte("date", first.isoformat())
            .lte("date", last.isoformat())
            .execute()
        ).data or []

        income   = Decimal("0") + sum(Decimal(str(e["amount_mxn"])) for e in inc)
        expenses = Decimal("0") + sum(Decimal(str(e["amount_mxn"])) for e in exp)

        return {
            "income":   round(income, 2),
            "expenses": round(expenses, 2),
            "balance":  round(income - expenses, 2),
        }

    def pct_change(current: Decimal, previous: Decimal) -> Decimal:
        if previous == 0:
            return Decimal("0")
        return round((current - previous) / previous * 100, 1)

    current  = await fetch_month(year,      month)
    previous = await fetch_month(prev_year, month)

    return {
        "current_year":    year,
        "previous_year":   prev_year,
        "month":           month,
        "month_label":     month_label(year, month),
        "current":         current,
        "previous":        previous,
        "changes": {
            "income":   pct_change(current["income"],   previous["income"]),
            "expenses": pct_change(current["expenses"], previous["expenses"]),
            "balance":  pct_change(current["balance"],  previous["balance"]),
        },
    }

async def get_spending_trends(
    user_id:     str,
    months_back: int = 6,
) -> dict:
    """
    Detects spending trends per category.

    For each category calculates:
      - Average monthly spend over the period
      - Current month spend
      - % change vs average → trend indicator
      - Direction: up/down/stable

    Stable = within ±10% of average
    Up     = more than +10% above average
    Down   = more than -10% below average
    """
    today       = date.today()
    month_range = get_month_range(months_back)
    first_month = month_range[0]

    start_date = date(first_month[0], first_month[1], 1)
    end_date   = date(
        today.year, today.month,
        calendar.monthrange(today.year, today.month)[1]
    )

    # Fetch all expenses with category in range
    exp_result = (
        supabase_admin
        .table("expenses")
        .select("amount_mxn, date, category_id")
        .eq("user_id", user_id)
        .gte("date", start_date.isoformat())
        .lte("date", end_date.isoformat())
        .execute()
    ).data or []

    # Fetch category names
    cat_ids    = list({e["category_id"] for e in exp_result if e.get("category_id")})
    cat_result = (
        supabase_admin
        .table("categories")
        .select("id, name, color")
        .in_("id", cat_ids)
        .execute()
    ).data or [] if cat_ids else []

    cat_map = {c["id"]: c for c in cat_result}

    # Aggregate by category and month
    # Structure: {cat_id: {(year, month): total}}
    cat_monthly: dict = {}

    for exp in exp_result:
        cat_id = exp.get("category_id") or "uncategorized"
        d      = date.fromisoformat(exp["date"])
        key    = (d.year, d.month)
        amount = Decimal(str(exp["amount_mxn"]))

        if cat_id not in cat_monthly:
            cat_monthly[cat_id] = {}
        cat_monthly[cat_id][key] = (
            cat_monthly[cat_id].get(key, Decimal("0")) + amount
        )

    # Calculate trends
    current_key   = (today.year, today.month)
    past_months   = [k for k in month_range if k != current_key]
    trends        = []

    for cat_id, monthly in cat_monthly.items():
        current_spend = monthly.get(current_key, Decimal("0"))
        past_values   = [
            monthly.get(m, Decimal("0"))
            for m in past_months
        ]

        if not past_values:
            continue

        avg_spend = sum(past_values) / len(past_values)

        if avg_spend > 0:
            pct_vs_avg = round((current_spend - avg_spend) / avg_spend * 100, 1)
        else:
            pct_vs_avg = Decimal("0")

        if pct_vs_avg > 10:
            direction = "up"
        elif pct_vs_avg < -10:
            direction = "down"
        else:
            direction = "stable"

        cat_info = cat_map.get(cat_id, {})

        trends.append({
            "category_id":    cat_id,
            "category_name":  cat_info.get("name", "Uncategorized"),
            "color":          cat_info.get("color", "#6B7280"),
            "current_month":  round(current_spend, 2),
            "avg_monthly":    round(avg_spend, 2),
            "pct_vs_avg":     pct_vs_avg,
            "direction":      direction,
        })

    # Sort by absolute % change descending
    trends.sort(key=lambda x: abs(float(x["pct_vs_avg"])), reverse=True)

    return {
        "trends":       trends,
        "period_months": months_back,
        "current_month": month_label(today.year, today.month),
    }

async def get_dashboard_weekly(
    user_id:        str,
    year:           int,
    month:          int,
    week_start_day: int = 1,  # 0=Sun, 1=Mon, 2=Tue ... 6=Sat
) -> dict:
    """
    Returns weekly income vs expenses vs projected
    for all weeks within a given month.

    Used by the dashboard weekly chart.
    Shows 4-5 bars per week with income/expenses/projected.
    Projected is the same monthly projection divided by 4.333.
    """
    import calendar as cal_mod
    from datetime import timedelta

    first_day = date(year, month, 1)
    last_day  = date(year, month, cal_mod.monthrange(year, month)[1])

    # ── Fetch expenses for the month ──────────────────────────────────
    exp_result = (
        supabase_admin
        .table("expenses")
        .select("amount_mxn, date")
        .eq("user_id", user_id)
        .gte("date", first_day.isoformat())
        .lte("date", last_day.isoformat())
        .execute()
    ).data or []

    # ── Fetch earnings for the month ──────────────────────────────────
    inc_result = (
        supabase_admin
        .table("earnings")
        .select("amount_mxn, date")
        .eq("user_id", user_id)
        .gte("date", first_day.isoformat())
        .lte("date", last_day.isoformat())
        .execute()
    ).data or []

    # ── Fetch projected monthly total ─────────────────────────────────
    costs_result = (
        supabase_admin
        .table("projected_costs")
        .select("amount, frequency, currency_id")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .execute()
    ).data or []

    currencies_result = (
        supabase_admin
        .table("currencies")
        .select("id, exchange_rate")
        .execute()
    ).data or []

    currency_map = {
        c["id"]: Decimal(str(c["exchange_rate"]))
        for c in currencies_result
    }

    WEEKLY_PER_MONTH  = Decimal("4.333333")
    projected_monthly = Decimal("0")

    for cost in costs_result:
        rate   = currency_map.get(cost.get("currency_id"), Decimal("1"))
        amount = Decimal(str(cost["amount"])) * rate
        if cost["frequency"] == "monthly":
            projected_monthly += amount
        elif cost["frequency"] == "weekly":
            projected_monthly += amount * WEEKLY_PER_MONTH

    # ── Calculate projected amount per specific week ───────────────────
    # Instead of dividing monthly by 4.333 uniformly,
    # calculate what actually falls in each week:
    #   weekly costs → only count if their day_of_week falls in that week
    #   monthly costs → only count if their day_of_month falls in that week
    #   one_time costs → only count if their month/year matches

    # Fetch full projected costs with day fields
    costs_full_result = (
        supabase_admin
        .table("projected_costs")
        .select("amount, frequency, currency_id, day_of_week, day_of_month, month, year")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .execute()
    ).data or []

    # ── Build week boundaries based on week_start_day ─────────────────
    # Find all week start dates within this month.
    # A week starts on the day matching week_start_day.
    # Week 1 always starts on the 1st of the month (may be partial).
    # Subsequent weeks start on the next occurrence of week_start_day.

    week_boundaries: list[date] = [first_day]
    current = first_day + timedelta(days=1)

    while current <= last_day:
        # Python weekday(): Mon=0 ... Sun=6
        # Our week_start_day: Sun=0, Mon=1 ... Sat=6
        # Convert our format to Python weekday format
        py_weekday = (week_start_day - 1) % 7  # Sun(0)->6, Mon(1)->0 ... Sat(6)->5

        if current.weekday() == py_weekday:
            week_boundaries.append(current)
        current += timedelta(days=1)

    # Build week ranges: [(start, end), ...]
    week_ranges: list[tuple[date, date]] = []
    for i, start in enumerate(week_boundaries):
        end = (
            week_boundaries[i + 1] - timedelta(days=1)
            if i + 1 < len(week_boundaries)
            else last_day
        )
        week_ranges.append((start, end))

    max_week = len(week_ranges)

    # ── Assign transactions to week buckets ───────────────────────────
    def get_week_index(d: date) -> int:
        """Returns 0-based week index for a given date."""
        for i, (start, end) in enumerate(week_ranges):
            if start <= d <= end:
                return i
        return max_week - 1  # fallback to last week

    weeks: dict = {
        f"W{i + 1}": {"income": Decimal("0"), "expenses": Decimal("0")}
        for i in range(max_week)
    }

    for exp in exp_result:
        d   = date.fromisoformat(exp["date"])
        key = f"W{get_week_index(d) + 1}"
        weeks[key]["expenses"] += Decimal(str(exp["amount_mxn"]))

    for inc in inc_result:
        d   = date.fromisoformat(inc["date"])
        key = f"W{get_week_index(d) + 1}"
        weeks[key]["income"] += Decimal(str(inc["amount_mxn"]))

    # ── Build response ─────────────────────────────────────────────────
    data_points = []
    for i, (w_start, w_end) in enumerate(week_ranges):
        key   = f"W{i + 1}"
        label = f"W{i + 1} ({w_start.strftime('%b %d')})"

        # Days in this week (day numbers of the month)
        week_days = set(range(w_start.day, w_end.day + 1))

        # Weekday numbers in this week (0=Mon, 6=Sun Python format)
        week_weekdays = set()
        current = w_start
        while current <= w_end:
            week_weekdays.add(current.weekday())
            current += timedelta(days=1)

        # Calculate projected for this specific week
        week_projected = Decimal("0")
        for cost in costs_full_result:
            rate   = currency_map.get(cost.get("currency_id"), Decimal("1"))
            amount = Decimal(str(cost["amount"])) * rate
            freq   = cost["frequency"]

            if freq == "weekly":
                # Include if this cost's day_of_week falls in this week
                dow = cost.get("day_of_week")
                if dow is not None and dow in week_weekdays:
                    week_projected += amount
                elif dow is None:
                    # No specific day set → distribute evenly
                    week_projected += amount

            elif freq == "monthly":
                # Include if this cost's day_of_month falls in this week
                dom = cost.get("day_of_month")
                if dom is not None and dom in week_days:
                    week_projected += amount
                elif dom is None:
                    # No specific day → distribute evenly across 4.333 weeks
                    week_projected += amount / WEEKLY_PER_MONTH

            elif freq == "one_time":
                # Include if this one-time cost is in this month/year
                cost_month = cost.get("month")
                cost_year  = cost.get("year")
                if cost_month == month and cost_year == year:
                    # Spread one-time cost across all weeks evenly
                    week_projected += amount / Decimal(str(max_week))

        data_points.append({
            "week_label":       label,
            "week_number":      i + 1,
            "week_start":       w_start.isoformat(),
            "week_end":         w_end.isoformat(),
            "total_income":     round(weeks[key]["income"],   2),
            "total_expenses":   round(weeks[key]["expenses"], 2),
            "projected_weekly": round(week_projected,         2),
        })

    return {
        "weeks":              data_points,
        "projected_monthly":  projected_monthly,
        "projected_per_week": Decimal("0"),  # no longer used
    }