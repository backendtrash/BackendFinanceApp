from decimal import Decimal
from typing import Optional
from uuid import UUID
import logging

from app.database import db, fetch_one
from app.expenses.schemas import (
    ExpenseCreate,
    ExpenseUpdate,
    ExpenseFilters,
)
from app.budgets.service import check_all_budgets_after_expense
from app.currencies.service import (
    get_currency_by_id,
    convert_amount as currency_convert,
)

# ── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)


# ── Currency Helpers ──────────────────────────────────────────────────────
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

# ── Expense CRUD ──────────────────────────────────────────────────────────
async def create_expense(
    user_id: str,
    data: ExpenseCreate,
) -> dict:
    """
    Creates a new expense record in the database.

    Flow:
      1. Calculate amount_mxn from amount + currency rate
      2. Build the insert payload
      3. Insert into expenses table
      4. Return the created row

    amount_mxn is calculated here not in the router because:
      - Service layer owns business logic
      - Router only handles HTTP concerns
      - Makes service testable without HTTP context
    """
    # Calculate MXN equivalent at current exchange rate
    # This snapshots the rate at creation time
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

    # Only include category_id if provided — avoids sending null FK
    if data.category_id:
        payload["category_id"] = str(data.category_id)

    # Link to the planned cost this expense was created from (Pay action)
    if data.projected_cost_id:
        payload["projected_cost_id"] = str(data.projected_cost_id)

    result = (
        db()
        .table("expenses")
        .insert(payload)
        .execute()
    )

    if not result.data:
        raise RuntimeError("Failed to create expense")

    # Check all budgets after new expense — triggers alerts if needed
    await check_all_budgets_after_expense(user_id)

    return result.data[0]


async def get_expense_by_id(
    expense_id: UUID,
    user_id: str,
) -> Optional[dict]:
    """
    Fetches a single expense by ID scoped to the authenticated user.
    Returns None if not found or belongs to a different user.
    Never raises 404 here — router handles HTTP error responses.
    """
    result = fetch_one(
        db()
        .table("expenses")
        .select("*")
        .eq("id", str(expense_id))
        .eq("user_id", user_id)
    )

    return result if result else None


async def list_expenses(
    user_id: str,
    filters: ExpenseFilters,
) -> tuple[list[dict], int]:
    """
    Returns a paginated list of expenses for a user with optional filters.
    Returns a tuple of (expenses_list, total_count).

    Total count uses a separate query with count="exact" so the
    frontend knows the full dataset size for pagination.

    Filters applied in order:
      1. user_id scope (always applied — security critical)
      2. date range
      3. category
      4. week
      5. currency
      6. pagination (limit + offset)
    """
    # ── Count query ───────────────────────────────────────────────────────
    # Separate count query needed because Supabase does not return
    # total count in the same response as paginated data
    count_query = (
        db()
        .table("expenses")
        .select("id", count="exact")
        .eq("user_id", user_id)
    )

    # ── Data query ────────────────────────────────────────────────────────
    data_query = (
        db()
        .table("expenses")
        .select("*")
        .eq("user_id", user_id)
        .order("date", desc=True)
        .limit(filters.limit)
        .offset(filters.offset)
    )

    # ── Apply filters to both queries ─────────────────────────────────────
    if filters.date_from:
        count_query = count_query.gte("date", filters.date_from.isoformat())
        data_query  = data_query.gte("date", filters.date_from.isoformat())

    if filters.date_to:
        count_query = count_query.lte("date", filters.date_to.isoformat())
        data_query  = data_query.lte("date", filters.date_to.isoformat())

    if filters.category_id:
        count_query = count_query.eq("category_id", str(filters.category_id))
        data_query  = data_query.eq("category_id", str(filters.category_id))

    if filters.week_number and filters.week_year:
        count_query = count_query.eq("week_number", filters.week_number)
        count_query = count_query.eq("week_year",   filters.week_year)
        data_query  = data_query.eq("week_number",  filters.week_number)
        data_query  = data_query.eq("week_year",    filters.week_year)

    if filters.currency_id:
        count_query = count_query.eq("currency_id", str(filters.currency_id))
        data_query  = data_query.eq("currency_id",  str(filters.currency_id))

    # ── Execute both queries ──────────────────────────────────────────────
    count_result = count_query.execute()
    data_result  = data_query.execute()

    total = count_result.count if count_result.count is not None else 0

    return data_result.data or [], total


async def update_expense(
    expense_id: UUID,
    user_id: str,
    data: ExpenseUpdate,
) -> Optional[dict]:
    """
    Partially updates an expense (PATCH semantics).
    Handles date updates separately via RPC because week_number
    and week_year are GENERATED ALWAYS columns that Supabase REST
    cannot update directly — they are recomputed automatically
    when date changes via raw SQL.
    """
    existing = await get_expense_by_id(expense_id, user_id)
    if not existing:
        return None

    # ── Build payload without date ────────────────────────────────────────
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

    # Recalculate amount_mxn if amount or currency changed
    if "amount" in payload or "currency_id" in payload:
        new_amount      = data.amount      or Decimal(str(existing["amount"]))
        new_currency_id = data.currency_id or UUID(existing["currency_id"])
        payload["amount_mxn"] = str(
            await calculate_amount_mxn(new_amount, new_currency_id)
        )

    # ── Update non-date fields ────────────────────────────────────────────
    if payload:
        result = (
            db()
            .table("expenses")
            .update(payload)
            .eq("id", str(expense_id))
            .eq("user_id", user_id)
            .execute()
        )
        if not result.data:
            return None

    # ── Update date separately via RPC ────────────────────────────────────
    if data.date is not None:
        db().rpc(
            "update_expense_date",
            {
                "expense_id": str(expense_id),
                "user_id":    user_id,
                "new_date":   data.date,
            }
        ).execute()

    # ── Check budget alerts after update ──────────────────────────────────
    await check_all_budgets_after_expense(user_id)

    # Return fresh data
    return await get_expense_by_id(expense_id, user_id)


async def delete_expense(
    expense_id: UUID,
    user_id: str,
) -> bool:
    """
    Deletes an expense by ID scoped to the authenticated user.
    Returns True if deleted, False if not found.
    Double-scoping by both id and user_id prevents a user from
    deleting another user's expense even if they guess the UUID.
    """
    result = (
        db()
        .table("expenses")
        .delete()
        .eq("id", str(expense_id))
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
    Returns total spending per category for a specific week.
    Used by the weekly view and the week relocation feature.

    Returns a dict with:
      total_mxn:  total spent in MXN for the week
      by_category: list of {category_id, total_mxn, count}
    """
    result = (
        db()
        .table("expenses")
        .select("category_id, amount_mxn")
        .eq("user_id", user_id)
        .eq("week_number", week_number)
        .eq("week_year", week_year)
        .execute()
    )

    expenses = result.data or []

    # Aggregate by category in Python — avoids complex SQL via PostgREST
    category_totals: dict = {}
    total_mxn = Decimal("0")

    for expense in expenses:
        amount  = Decimal(str(expense["amount_mxn"]))
        cat_id  = expense.get("category_id") or "uncategorized"
        total_mxn += amount

        if cat_id not in category_totals:
            category_totals[cat_id] = {"total_mxn": Decimal("0"), "count": 0}

        category_totals[cat_id]["total_mxn"] += amount
        category_totals[cat_id]["count"]     += 1

    return {
        "week_number":   week_number,
        "week_year":     week_year,
        "total_mxn":     str(round(total_mxn, 2)),
        "by_category": [
            {
                "category_id": cat_id,
                "total_mxn":   str(round(v["total_mxn"], 2)),
                "count":       v["count"],
            }
            for cat_id, v in category_totals.items()
        ],
    }


async def delete_all_expenses(user_id: str) -> int:
    """
    Deletes every expense belonging to this user and returns the count.

    Part of the full data reset on the Settings screen.
    """
    result = (
        db()
        .table("expenses")
        .delete()
        .eq("user_id", user_id)
        .execute()
    )

    deleted = len(result.data or [])
    logger.info(f"Deleted {deleted} expenses for user {user_id}")
    return deleted
