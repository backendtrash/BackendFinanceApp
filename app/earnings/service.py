from decimal import Decimal
from typing import Optional
from uuid import UUID
import logging

from app.database import supabase_admin
from app.earnings.schemas import EarningCreate, EarningUpdate, EarningFilters
from app.currencies.service import (
    get_currency_by_id,
    convert_amount as currency_convert,
)

# ── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)


async def calculate_amount_mxn(
    amount: Decimal,
    currency_id: UUID,
) -> Decimal:
    """
    Converts amount to MXN using currency service.
    Delegates to currencies module — single source of truth for rates.
    """
    currency = await get_currency_by_id(currency_id)
    if not currency:
        raise ValueError(f"Currency {currency_id} not found")
    rate = Decimal(str(currency["exchange_rate"]))
    return round(amount * rate, 2)


async def create_earning(
    user_id: str,
    data: EarningCreate,
) -> dict:
    """
    Creates a new earning record in the database.
    Calculates and snapshots amount_mxn at creation time.
    """
    amount_mxn = await calculate_amount_mxn(data.amount, data.currency_id)

    payload = {
        "user_id":      user_id,
        "amount":       str(data.amount),
        "currency_id":  str(data.currency_id),
        "amount_mxn":   str(amount_mxn),
        "date":         data.date.isoformat(),
        "notes":        data.notes,
        "is_recurring": data.is_recurring,
    }

    if data.category_id:
        payload["category_id"] = str(data.category_id)

    result = (
        supabase_admin
        .table("earnings")
        .insert(payload)
        .execute()
    )

    if not result.data:
        raise RuntimeError("Failed to create earning")

    return result.data[0]


async def get_earning_by_id(
    earning_id: UUID,
    user_id: str,
) -> Optional[dict]:
    """
    Fetches a single earning by ID scoped to the authenticated user.
    Returns None if not found or belongs to a different user.
    """
    result = (
        supabase_admin
        .table("earnings")
        .select("*")
        .eq("id", str(earning_id))
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    return result.data if result.data else None


async def list_earnings(
    user_id: str,
    filters: EarningFilters,
) -> tuple[list[dict], int]:
    """
    Returns paginated earnings for a user with optional filters.
    Returns tuple of (earnings_list, total_count).
    """
    count_query = (
        supabase_admin
        .table("earnings")
        .select("id", count="exact")
        .eq("user_id", user_id)
    )

    data_query = (
        supabase_admin
        .table("earnings")
        .select("*")
        .eq("user_id", user_id)
        .order("date", desc=True)
        .limit(filters.limit)
        .offset(filters.offset)
    )

    if filters.date_from:
        count_query = count_query.gte("date", filters.date_from.isoformat())
        data_query  = data_query.gte("date",  filters.date_from.isoformat())

    if filters.date_to:
        count_query = count_query.lte("date", filters.date_to.isoformat())
        data_query  = data_query.lte("date",  filters.date_to.isoformat())

    if filters.category_id:
        count_query = count_query.eq("category_id", str(filters.category_id))
        data_query  = data_query.eq("category_id",  str(filters.category_id))

    if filters.week_number and filters.week_year:
        count_query = count_query.eq("week_number", filters.week_number)
        count_query = count_query.eq("week_year",   filters.week_year)
        data_query  = data_query.eq("week_number",  filters.week_number)
        data_query  = data_query.eq("week_year",    filters.week_year)

    if filters.currency_id:
        count_query = count_query.eq("currency_id", str(filters.currency_id))
        data_query  = data_query.eq("currency_id",  str(filters.currency_id))

    count_result = count_query.execute()
    data_result  = data_query.execute()

    total = count_result.count if count_result.count is not None else 0

    return data_result.data or [], total


async def update_earning(
    earning_id: UUID,
    user_id: str,
    data: EarningUpdate,
) -> Optional[dict]:
    """
    Partially updates an earning.
    Handles date updates via RPC for same reason as expenses —
    generated columns week_number/week_year cannot be updated via REST.
    """
    existing = await get_earning_by_id(earning_id, user_id)
    if not existing:
        return None

    payload: dict = {}

    if data.amount is not None:
        payload["amount"] = str(data.amount)

    if data.currency_id is not None:
        payload["currency_id"] = str(data.currency_id)

    if data.category_id is not None:
        payload["category_id"] = str(data.category_id)

    if data.notes is not None:
        payload["notes"] = data.notes

    if data.is_recurring is not None:
        payload["is_recurring"] = data.is_recurring

    if "amount" in payload or "currency_id" in payload:
        new_amount      = data.amount      or Decimal(str(existing["amount"]))
        new_currency_id = data.currency_id or UUID(existing["currency_id"])
        payload["amount_mxn"] = str(
            await calculate_amount_mxn(new_amount, new_currency_id)
        )

    # Update non-date fields
    if payload:
        result = (
            supabase_admin
            .table("earnings")
            .update(payload)
            .eq("id", str(earning_id))
            .eq("user_id", user_id)
            .execute()
        )
        if not result.data:
            return None

    # Update date via RPC
    if data.date is not None:
        supabase_admin.rpc(
            "update_earning_date",
            {
                "earning_id": str(earning_id),
                "user_id":    user_id,
                "new_date":   data.date,
            }
        ).execute()

    return await get_earning_by_id(earning_id, user_id)


async def delete_earning(
    earning_id: UUID,
    user_id: str,
) -> bool:
    """
    Deletes an earning scoped to the authenticated user.
    Returns True if deleted, False if not found.
    """
    result = (
        supabase_admin
        .table("earnings")
        .delete()
        .eq("id", str(earning_id))
        .eq("user_id", user_id)
        .execute()
    )

    return len(result.data) > 0


async def get_weekly_summary(
    user_id: str,
    week_number: int,
    week_year: int,
) -> dict:
    """
    Returns total income per category for a specific week.
    Mirrors expenses weekly summary for cash flow comparisons.
    """
    result = (
        supabase_admin
        .table("earnings")
        .select("category_id, amount_mxn")
        .eq("user_id", user_id)
        .eq("week_number", week_number)
        .eq("week_year", week_year)
        .execute()
    )

    earnings = result.data or []

    category_totals: dict = {}
    total_mxn = Decimal("0")

    for earning in earnings:
        amount = Decimal(str(earning["amount_mxn"]))
        cat_id = earning.get("category_id") or "uncategorized"
        total_mxn += amount

        if cat_id not in category_totals:
            category_totals[cat_id] = {"total_mxn": Decimal("0"), "count": 0}

        category_totals[cat_id]["total_mxn"] += amount
        category_totals[cat_id]["count"]     += 1

    return {
        "week_number": week_number,
        "week_year":   week_year,
        "total_mxn":   str(round(total_mxn, 2)),
        "by_category": [
            {
                "category_id": cat_id,
                "total_mxn":   str(round(v["total_mxn"], 2)),
                "count":       v["count"],
            }
            for cat_id, v in category_totals.items()
        ],
    }