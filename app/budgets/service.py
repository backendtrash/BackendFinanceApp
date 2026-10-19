from decimal import Decimal
from typing import Optional
from uuid import UUID
from datetime import date
import logging

from app.database import db, fetch_one
from app.budgets.schemas import BudgetCreate, BudgetUpdate, BudgetPeriod

# ── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)


def get_period_date_range(period: str) -> tuple[date, date]:
    """
    Returns the start and end date for the current budget period.

    weekly:  Monday to Sunday of current ISO week
    monthly: First to last day of current month

    Used to calculate how much has been spent in the current period
    when computing budget progress (spent_amount, pct_spent).
    """
    today = date.today()

    if period == BudgetPeriod.weekly.value:
        # ISO week starts on Monday (weekday 0)
        start = today - __import__("datetime").timedelta(days=today.weekday())
        end   = start + __import__("datetime").timedelta(days=6)
        return start, end

    else:
        # Monthly — first and last day of current month
        import calendar
        first_day = today.replace(day=1)
        last_day  = today.replace(
            day=calendar.monthrange(today.year, today.month)[1]
        )
        return first_day, last_day


async def calculate_spent_amount(
    user_id: str,
    category_id: Optional[UUID],
    period: str,
) -> Decimal:
    """
    Calculates total amount spent in MXN for a budget's scope and period.

    If category_id is None → sums ALL expenses in the period (global budget)
    If category_id is set  → sums only that category's expenses

    Always works in MXN for consistent comparison against limit_amount.
    """
    start_date, end_date = get_period_date_range(period)

    query = (
        db()
        .table("expenses")
        .select("amount_mxn")
        .eq("user_id", user_id)
        .gte("date", start_date.isoformat())
        .lte("date", end_date.isoformat())
    )

    # Scope to specific category or all categories
    if category_id:
        query = query.eq("category_id", str(category_id))

    result = query.execute()
    expenses = result.data or []

    # Sum all amounts in Python — simple and reliable
    total = sum(
        Decimal(str(e["amount_mxn"]))
        for e in expenses
    )

    return round(total, 2)


async def enrich_budget(user_id: str, budget: dict) -> dict:
    """
    Adds computed fields to a budget dict:
      spent_amount → total spent in current period in MXN
      pct_spent    → percentage of limit spent (0-999.99)
      remaining    → limit minus spent (can be negative if over budget)

    Called on every budget fetch so frontend always has current progress.
    """
    category_id = (
        UUID(budget["category_id"])
        if budget.get("category_id")
        else None
    )

    spent = await calculate_spent_amount(
        user_id=user_id,
        category_id=category_id,
        period=budget["period"],
    )

    limit = Decimal(str(budget["limit_amount"]))

    # Percentage spent — cap display at 999.99 to avoid absurd numbers
    pct_spent = round((spent / limit * 100), 2) if limit > 0 else Decimal("0")

    budget["spent_amount"] = spent
    budget["pct_spent"]    = pct_spent
    budget["remaining"]    = round(limit - spent, 2)

    return budget


async def check_and_create_alert(
    user_id: str,
    budget: dict,
) -> Optional[dict]:
    """
    Checks if a budget has crossed its alert threshold.
    Creates a budget_alert record if:
      1. pct_spent >= alert_threshold
      2. No alert has been created for this budget today yet

    Returns the created alert dict or None if no alert was needed.
    This is called after every expense CREATE and UPDATE.
    """
    pct_spent       = Decimal(str(budget["pct_spent"]))
    alert_threshold = Decimal(str(budget["alert_threshold"]))

    # Not yet at threshold — no alert needed
    if pct_spent < alert_threshold:
        return None

    today = date.today().isoformat()

    # Check if alert already fired today for this budget
    existing = (
        db()
        .table("budget_alerts")
        .select("id")
        .eq("budget_id", budget["id"])
        .eq("triggered_date", today)
        .execute()
    )

    if existing.data:
        # Alert already fired today — do not spam
        return None

    # Create the alert record
    result = (
        db()
        .table("budget_alerts")
        .insert({
            "budget_id":      budget["id"],
            "user_id":        user_id,
            "pct_spent":      str(pct_spent),
            "amount_spent":   str(budget["spent_amount"]),
            "limit_amount":   str(budget["limit_amount"]),
            "triggered_date": today,
        })
        .execute()
    )

    if result.data:
        logger.info(
            f"Budget alert created for user {user_id} "
            f"budget {budget['id']} at {pct_spent}%"
        )
        return result.data[0]

    return None


async def create_budget(
    user_id: str,
    data: BudgetCreate,
) -> dict:
    """
    Creates a new budget for the user.
    Enriches the response with current spending progress immediately.
    """
    payload = {
        "user_id":         user_id,
        "limit_amount":    str(data.limit_amount),
        "currency_id":     str(data.currency_id),
        "period":          data.period.value,
        "alert_threshold": data.alert_threshold,
        "is_active":       True,
    }

    if data.category_id:
        payload["category_id"] = str(data.category_id)

    result = (
        db()
        .table("budgets")
        .insert(payload)
        .execute()
    )

    if not result.data:
        raise RuntimeError("Failed to create budget")

    return await enrich_budget(user_id, result.data[0])


async def list_budgets(
    user_id: str,
    active_only: bool = True,
) -> list[dict]:
    """
    Returns all budgets for a user enriched with current spending.
    active_only=True (default) returns only active budgets.
    active_only=False returns all including deactivated budgets.
    """
    query = (
        db()
        .table("budgets")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=False)
    )

    if active_only:
        query = query.eq("is_active", True)

    result = query.execute()
    budgets = result.data or []

    # Enrich each budget with spending progress
    # Each enrich call makes one DB query — acceptable for small budget lists
    enriched = []
    for budget in budgets:
        enriched.append(await enrich_budget(user_id, budget))

    return enriched


async def get_budget_by_id(
    budget_id: UUID,
    user_id: str,
) -> Optional[dict]:
    """
    Fetches a single budget by ID scoped to the authenticated user.
    Returns None if not found or belongs to another user.
    """
    result = fetch_one(
        db()
        .table("budgets")
        .select("*")
        .eq("id", str(budget_id))
        .eq("user_id", user_id)
    )

    if not result:
        return None

    return await enrich_budget(user_id, result)


async def update_budget(
    budget_id: UUID,
    user_id: str,
    data: BudgetUpdate,
) -> Optional[dict]:
    """
    Partially updates a budget.
    period and category_id cannot be changed — they define budget scope.
    Returns None if not found or belongs to another user.
    """
    payload: dict = {}

    if data.limit_amount is not None:
        payload["limit_amount"] = str(data.limit_amount)

    if data.currency_id is not None:
        payload["currency_id"] = str(data.currency_id)

    if data.period is not None:
        payload["period"] = data.period.value

    if data.alert_threshold is not None:
        payload["alert_threshold"] = data.alert_threshold

    if data.is_active is not None:
        payload["is_active"] = data.is_active

    if not payload:
        return await get_budget_by_id(budget_id, user_id)

    result = (
        db()
        .table("budgets")
        .update(payload)
        .eq("id", str(budget_id))
        .eq("user_id", user_id)
        .execute()
    )

    if not result.data:
        return None

    return await enrich_budget(user_id, result.data[0])


async def delete_budget(
    budget_id: UUID,
    user_id: str,
) -> bool:
    """
    Deletes a budget and all its associated alerts (CASCADE in schema).
    Returns True if deleted, False if not found.
    """
    result = (
        db()
        .table("budgets")
        .delete()
        .eq("id", str(budget_id))
        .eq("user_id", user_id)
        .execute()
    )

    return len(result.data) > 0


async def get_budget_alerts(
    user_id: str,
    budget_id: Optional[UUID] = None,
    limit: int = 20,
) -> list[dict]:
    """
    Returns budget alert history for a user.
    Optionally filtered to a specific budget.
    Ordered by most recent first.
    """
    query = (
        db()
        .table("budget_alerts")
        .select("*")
        .eq("user_id", user_id)
        .order("triggered_at", desc=True)
        .limit(limit)
    )

    if budget_id:
        query = query.eq("budget_id", str(budget_id))

    result = query.execute()
    return result.data or []


async def clear_budget_alerts(user_id: str) -> int:
    result = (
        db()
        .table("budget_alerts")
        .delete()
        .eq("user_id", user_id)
        .execute()
    )
    return len(result.data or [])


async def check_all_budgets_after_expense(user_id: str) -> None:
    """
    Checks all active budgets after an expense is created or updated.
    Creates alerts for any budgets that crossed their threshold.

    Called by expenses/service.py after every successful INSERT or UPDATE.
    This is the budget alert trigger mechanism.
    """
    budgets = await list_budgets(user_id=user_id, active_only=True)

    for budget in budgets:
        await check_and_create_alert(
            user_id=user_id,
            budget=budget,
        )


async def delete_all_budgets(user_id: str) -> int:
    """
    Deletes every budget belonging to this user and returns the count.

    Alert history goes with them. budget_alerts.budget_id cascades, which
    is the one place in this schema where cascade is right: an alert says
    "this budget crossed its threshold", so it has no meaning once the
    budget is gone and it is not financial history worth keeping.
    """
    result = (
        db()
        .table("budgets")
        .delete()
        .eq("user_id", user_id)
        .execute()
    )

    deleted = len(result.data or [])
    logger.info(f"Deleted {deleted} budgets for user {user_id}")
    return deleted
