from decimal  import Decimal
from typing   import Optional
from uuid     import UUID
import logging

from app.database import supabase_admin

logger = logging.getLogger(__name__)

WEEKLY_PER_MONTH = Decimal("4.333333")


async def _get_exchange_rate(currency_id: Optional[str]) -> Decimal:
    """Fetches exchange rate for a currency. Returns 1 for MXN."""
    if not currency_id:
        return Decimal("1")

    result = (
        supabase_admin
        .table("currencies")
        .select("exchange_rate")
        .eq("id", currency_id)
        .single()
        .execute()
    )
    if result.data:
        return Decimal(str(result.data["exchange_rate"]))
    return Decimal("1")


async def list_projected_costs(user_id: str) -> list[dict]:
    """Returns all projected costs enriched with amount_mxn."""
    result = (
        supabase_admin
        .table("projected_costs")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=False)
        .execute()
    )

    costs = result.data or []

    # Fetch all currencies once for enrichment
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

    for cost in costs:
        rate              = currency_map.get(cost.get("currency_id"), Decimal("1"))
        cost["amount_mxn"] = str(round(Decimal(str(cost["amount"])) * rate, 2))

    return costs


async def create_projected_cost(
    user_id: str,
    data:    object,
) -> dict:
    """Creates a new projected cost."""
    rate       = await _get_exchange_rate(
        str(data.currency_id) if data.currency_id else None
    )
    amount_mxn = round(data.amount * rate, 2)

    payload = {
        "user_id":   user_id,
        "name":      data.name,
        "amount":    str(data.amount),
        "frequency": data.frequency,
        "is_active": data.is_active,
    }

    if data.currency_id:
        payload["currency_id"] = str(data.currency_id)
    if data.category_id:
        payload["category_id"] = str(data.category_id)
    if data.notes:
        payload["notes"] = data.notes
    if data.month:
        payload["month"] = data.month
    if data.year:
        payload["year"] = data.year
    if data.day_of_week is not None:
        payload["day_of_week"] = data.day_of_week
    if data.day_of_month is not None:
        payload["day_of_month"] = data.day_of_month
    payload["plan_group"] = data.plan_group

    result = (
        supabase_admin
        .table("projected_costs")
        .insert(payload)
        .execute()
    )

    if not result.data:
        raise RuntimeError("Failed to create projected cost")

    cost             = result.data[0]
    cost["amount_mxn"] = str(amount_mxn)
    return cost


async def update_projected_cost(
    cost_id: UUID,
    user_id: str,
    data:    object,
) -> Optional[dict]:
    """Partially updates a projected cost."""
    payload: dict = {}

    if data.name         is not None: payload["name"]         = data.name
    if data.amount       is not None: payload["amount"]        = str(data.amount)
    if data.currency_id  is not None: payload["currency_id"]   = str(data.currency_id)
    if data.frequency    is not None: payload["frequency"]     = data.frequency
    if data.month        is not None: payload["month"]         = data.month
    if data.year         is not None: payload["year"]          = data.year
    if data.category_id  is not None: payload["category_id"]   = str(data.category_id)
    if data.is_active    is not None: payload["is_active"]     = data.is_active
    if data.notes        is not None: payload["notes"]         = data.notes
    if data.plan_group   is not None: payload["plan_group"]    = data.plan_group
    if data.day_of_week  is not None: payload["day_of_week"]   = data.day_of_week
    if data.day_of_month is not None: payload["day_of_month"]  = data.day_of_month

    if not payload:
        return None

    result = (
        supabase_admin
        .table("projected_costs")
        .update(payload)
        .eq("id", str(cost_id))
        .eq("user_id", user_id)
        .execute()
    )

    if not result.data:
        return None

    cost             = result.data[0]
    rate             = await _get_exchange_rate(cost.get("currency_id"))
    cost["amount_mxn"] = str(round(Decimal(str(cost["amount"])) * rate, 2))
    return cost


async def delete_projected_cost(cost_id: UUID, user_id: str) -> bool:
    """Deletes a projected cost."""
    result = (
        supabase_admin
        .table("projected_costs")
        .delete()
        .eq("id", str(cost_id))
        .eq("user_id", user_id)
        .execute()
    )
    return bool(result.data)


async def get_monthly_projection(
    user_id: str,
    year:    int,
    month:   int,
) -> dict:
    """
    Calculates total projected spending for a given month.

    Includes:
      - All active monthly projected costs
      - All active weekly projected costs (× 4.333)
      - One-time costs scheduled for this specific month/year

    Returns breakdown by category for analytics.
    """
    result = (
        supabase_admin
        .table("projected_costs")
        .select("*, currencies(exchange_rate)")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .execute()
    )

    costs = result.data or []

    total            = Decimal("0")
    category_totals: dict = {}

    for cost in costs:
        amount = Decimal(str(cost["amount"]))

        # Get exchange rate from joined currency data
        currency_data = cost.get("currencies")
        rate = (
            Decimal(str(currency_data["exchange_rate"]))
            if currency_data else Decimal("1")
        )
        amount_mxn = amount * rate

        freq = cost["frequency"]

        if freq == "monthly":
            contribution = amount_mxn
        elif freq == "weekly":
            contribution = amount_mxn * WEEKLY_PER_MONTH
        elif freq == "one_time":
            # Only include if this cost is for this specific month/year
            cost_month = cost.get("month")
            cost_year  = cost.get("year")
            if cost_month == month and cost_year == year:
                contribution = amount_mxn
            else:
                continue
        else:
            continue

        total += contribution

        # Group by category for breakdown
        cat_id = cost.get("category_id") or "uncategorized"
        if cat_id not in category_totals:
            category_totals[cat_id] = Decimal("0")
        category_totals[cat_id] += contribution

    return {
        "total_projected_mxn": str(round(total, 2)),
        "category_breakdown":  {
            k: str(round(v, 2))
            for k, v in category_totals.items()
        },
        "year":  year,
        "month": month,
    }


async def delete_all_projected_costs(user_id: str) -> int:
    """
    Deletes every projected cost belonging to this user.

    Safe in isolation: projections are forecast only and never produced a
    transaction. Expenses that were paid against one keep their row; the
    foreign key sets projected_cost_id to null.
    """
    result = (
        supabase_admin
        .table("projected_costs")
        .delete()
        .eq("user_id", user_id)
        .execute()
    )

    deleted = len(result.data or [])
    logger.info(f"Deleted {deleted} projected costs for user {user_id}")
    return deleted
