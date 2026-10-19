from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional
from uuid import UUID
from datetime import date
from decimal import Decimal
import logging

from app.auth.dependencies import get_current_user, AuthenticatedUser
from app.expenses.schemas import (
    ExpenseCreate,
    ExpenseUpdate,
    ExpenseResponse,
    ExpenseListResponse,
    ExpenseFilters,
)
from app.expenses import service
from app.expenses.schemas import ExpenseCreate
from app.database import db

# ── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ── Router ────────────────────────────────────────────────────────────────
router = APIRouter()


# ── Create Expense ────────────────────────────────────────────────────────
@router.post(
    "/",
    response_model=ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new expense",
)
async def create_expense(
    body: ExpenseCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Creates a new expense for the authenticated user.
    amount_mxn is calculated automatically from amount + currency rate.
    week_number and week_year are generated automatically from date.
    """
    try:
        expense = await service.create_expense(
            user_id=current_user.user_id,
            data=body,
        )
        return expense

    except ValueError as e:
        # ValueError from service means bad input data
        # e.g. currency_id not found in DB
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except RuntimeError as e:
        # RuntimeError from service means DB operation failed
        logger.error(f"Failed to create expense for {current_user.user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create expense",
        )


# ── List Expenses ─────────────────────────────────────────────────────────
@router.get(
    "/",
    response_model=ExpenseListResponse,
    status_code=status.HTTP_200_OK,
    summary="List expenses with optional filters",
)
async def list_expenses(
    # Date range filters
    date_from:   Optional[date] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    date_to:     Optional[date] = Query(None, description="Filter to date (YYYY-MM-DD)"),

    # Category filter
    category_id: Optional[UUID] = Query(None, description="Filter by category UUID"),

    # Week filters
    week_number: Optional[int]  = Query(None, description="ISO week number (1-53)"),
    week_year:   Optional[int]  = Query(None, description="ISO week year"),

    # Currency filter
    currency_id: Optional[UUID] = Query(None, description="Filter by currency UUID"),

    # Pagination
    limit:       int            = Query(50,   description="Page size (max 100)"),
    offset:      int            = Query(0,    description="Pagination offset"),

    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns paginated list of expenses for the authenticated user.
    All filters are optional — no filters returns all expenses paginated.
    Results are ordered by date descending (most recent first).
    """
    # Build filters DTO from query params
    # Validation rules from ExpenseFilters are applied automatically
    filters = ExpenseFilters(
        date_from=date_from,
        date_to=date_to,
        category_id=category_id,
        week_number=week_number,
        week_year=week_year,
        currency_id=currency_id,
        limit=limit,
        offset=offset,
    )

    expenses, total = await service.list_expenses(
        user_id=current_user.user_id,
        filters=filters,
    )

    return ExpenseListResponse(
        data=expenses,
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )

# ── Monthly Summary ───────────────────────────────────────────────────────
@router.get(
    "/months",
    status_code=status.HTTP_200_OK,
    summary="Get list of months that have expenses",
)
async def get_expense_months(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns a list of distinct year/month combinations that have expenses.
    Used to populate the month picker in the frontend.
    Each entry includes total amount and transaction count.
    """
    result = (
        db()
        .table("expenses")
        .select("date, amount_mxn")
        .eq("user_id", current_user.user_id)
        .order("date", desc=True)
        .execute()
    )

    expenses = result.data or []

    # Aggregate by month in Python
    month_map: dict = {}
    for exp in expenses:
        d        = exp["date"][:7]  # YYYY-MM
        amount   = Decimal(str(exp["amount_mxn"]))
        if d not in month_map:
            month_map[d] = {"total": Decimal("0"), "count": 0}
        month_map[d]["total"] += amount
        month_map[d]["count"] += 1

    return [
        {
            "month_key":   k,
            "year":        int(k[:4]),
            "month":       int(k[5:7]),
            "total_mxn":   str(round(v["total"], 2)),
            "count":       v["count"],
        }
        for k, v in sorted(month_map.items(), reverse=True)
    ]

# ── Get Single Expense ────────────────────────────────────────────────────
@router.get(
    "/{expense_id}",
    response_model=ExpenseResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a single expense by ID",
)
async def get_expense(
    expense_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns a single expense by ID.
    Returns 404 if not found or belongs to a different user.
    """
    expense = await service.get_expense_by_id(
        expense_id=expense_id,
        user_id=current_user.user_id,
    )

    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Expense {expense_id} not found",
        )

    return expense


# ── Update Expense ────────────────────────────────────────────────────────
@router.patch(
    "/{expense_id}",
    response_model=ExpenseResponse,
    status_code=status.HTTP_200_OK,
    summary="Partially update an expense",
)
async def update_expense(
    expense_id: UUID,
    body: ExpenseUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Partially updates an expense (PATCH semantics).
    Only provided fields are updated — omitted fields stay unchanged.
    amount_mxn is recalculated automatically if amount or currency changes.
    Returns 404 if expense not found or belongs to a different user.
    """
    try:
        expense = await service.update_expense(
            expense_id=expense_id,
            user_id=current_user.user_id,
            data=body,
        )

        if not expense:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Expense {expense_id} not found",
            )

        return expense

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ── Delete Expense ────────────────────────────────────────────────────────
@router.delete(
    "/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an expense",
)
async def delete_expense(
    expense_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Deletes an expense by ID.
    Returns 204 No Content on success.
    Returns 404 if not found or belongs to a different user.
    """
    deleted = await service.delete_expense(
        expense_id=expense_id,
        user_id=current_user.user_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Expense {expense_id} not found",
        )


# ── Weekly Summary ────────────────────────────────────────────────────────
@router.get(
    "/weekly/{week_year}/{week_number}",
    status_code=status.HTTP_200_OK,
    summary="Get weekly expense summary by category",
)
async def get_weekly_summary(
    week_year:   int,
    week_number: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns total spending per category for a specific ISO week.
    Used by the weekly view and week relocation feature.
    week_year is required alongside week_number to handle
    cross-year week boundaries correctly.
    """
    if not 1 <= week_number <= 53:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="week_number must be between 1 and 53",
        )

    if week_year < 2000 or week_year > 2100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="week_year must be between 2000 and 2100",
        )

    return await service.get_weekly_summary(
        user_id=current_user.user_id,
        week_number=week_number,
        week_year=week_year,
    )
# ── Bulk Import ───────────────────────────────────────────────────────────
@router.post(
    "/import",
    status_code=status.HTTP_200_OK,
    summary="Bulk import expenses from JSON",
)
async def import_expenses(
    body: list[ExpenseCreate],
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Bulk imports a list of expenses for the authenticated user.
    Each item is validated by ExpenseCreate schema.
    Returns count of successfully created expenses.
    Frontend handles CSV/JSON parsing and sends validated rows here.
    """
    created = 0
    errors  = []

    for i, item in enumerate(body):
        try:
            await service.create_expense(
                user_id=current_user.user_id,
                data=item,
            )
            created += 1
        except Exception as e:
            errors.append({"row": i + 1, "error": str(e)})

    return {
        "created": created,
        "errors":  errors,
        "total":   len(body),
    }

# ── Bulk Delete ───────────────────────────────────────────────────────────
@router.delete(
    "/",
    status_code=status.HTTP_200_OK,
    summary="Delete all expenses for the current user",
)
async def delete_all_expenses(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Deletes ALL expense records belonging to the authenticated user.

    Irreversible.
    """
    deleted = await service.delete_all_expenses(user_id=current_user.user_id)
    return {"deleted": deleted, "message": f"Deleted {deleted} expenses"}

# ── Split Expense ─────────────────────────────────────────────────────────
from pydantic import BaseModel as PydanticBase

class SplitExpenseRequest(PydanticBase):
    """
    Request body for splitting an expense across two weeks.
    original_amount: what stays on the original date
    split_amount:    what moves to the new date
    split_date:      date for the new split row
    original_amount + split_amount must equal original total
    """
    original_amount: float
    original_date:   str
    split_amount:    float
    split_date:      str

@router.post(
    "/{expense_id}/split",
    status_code=status.HTTP_200_OK,
    summary="Split an expense across two dates/weeks",
)
async def split_expense(
    expense_id: UUID,
    body: SplitExpenseRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Splits an expense into two rows.
    Original row gets original_amount on original_date.
    New row gets split_amount on split_date.
    Used by the week view relocation feature.
    """
    result = db().rpc(
        "split_expense",
        {
            "expense_id":      str(expense_id),
            "user_id":         current_user.user_id,
            "original_amount": body.original_amount,
            "original_date":   body.original_date,
            "split_amount":    body.split_amount,
            "split_date":      body.split_date,
        }
    ).execute()
    return {"message": "Expense split successfully"}

