from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional
from uuid import UUID
from datetime import date
import logging
from decimal import Decimal

from app.auth.dependencies import get_current_user, AuthenticatedUser
from app.earnings.schemas import (
    EarningCreate,
    EarningUpdate,
    EarningResponse,
    EarningListResponse,
    EarningFilters,
)
from app.earnings import service
from app.earnings.schemas import EarningCreate
from app.database import supabase_admin

# ── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ── Router ────────────────────────────────────────────────────────────────
router = APIRouter()


# ── Create Earning ────────────────────────────────────────────────────────
@router.post(
    "/",
    response_model=EarningResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new earning",
)
async def create_earning(
    body: EarningCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Creates a new earning for the authenticated user.
    amount_mxn calculated automatically from amount + currency rate.
    """
    try:
        earning = await service.create_earning(
            user_id=current_user.user_id,
            data=body,
        )
        return earning

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except RuntimeError as e:
        logger.error(f"Failed to create earning for {current_user.user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create earning",
        )


# ── List Earnings ─────────────────────────────────────────────────────────
@router.get(
    "/",
    response_model=EarningListResponse,
    status_code=status.HTTP_200_OK,
    summary="List earnings with optional filters",
)
async def list_earnings(
    date_from:   Optional[date] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    date_to:     Optional[date] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    category_id: Optional[UUID] = Query(None, description="Filter by category UUID"),
    week_number: Optional[int]  = Query(None, description="ISO week number (1-53)"),
    week_year:   Optional[int]  = Query(None, description="ISO week year"),
    currency_id: Optional[UUID] = Query(None, description="Filter by currency UUID"),
    limit:       int            = Query(50,   description="Page size (max 100)"),
    offset:      int            = Query(0,    description="Pagination offset"),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns paginated earnings for the authenticated user.
    Results ordered by date descending.
    """
    filters = EarningFilters(
        date_from=date_from,
        date_to=date_to,
        category_id=category_id,
        week_number=week_number,
        week_year=week_year,
        currency_id=currency_id,
        limit=limit,
        offset=offset,
    )

    earnings, total = await service.list_earnings(
        user_id=current_user.user_id,
        filters=filters,
    )

    return EarningListResponse(
        data=earnings,
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )

# ── Monthly Summary ───────────────────────────────────────────────────────
@router.get(
    "/months",
    status_code=status.HTTP_200_OK,
    summary="Get list of months that have earnings",
)
async def get_earning_months(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns distinct year/month combinations that have earnings.
    """
    result = (
        supabase_admin
        .table("earnings")
        .select("date, amount_mxn")
        .eq("user_id", current_user.user_id)
        .order("date", desc=True)
        .execute()
    )

    earnings = result.data or []

    month_map: dict = {}
    for e in earnings:
        d      = e["date"][:7]
        amount = Decimal(str(e["amount_mxn"]))
        if d not in month_map:
            month_map[d] = {"total": Decimal("0"), "count": 0}
        month_map[d]["total"] += amount
        month_map[d]["count"] += 1

    return [
        {
            "month_key": k,
            "year":      int(k[:4]),
            "month":     int(k[5:7]),
            "total_mxn": str(round(v["total"], 2)),
            "count":     v["count"],
        }
        for k, v in sorted(month_map.items(), reverse=True)
    ]


# ── Get Single Earning ────────────────────────────────────────────────────
@router.get(
    "/{earning_id}",
    response_model=EarningResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a single earning by ID",
)
async def get_earning(
    earning_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns a single earning by ID.
    Returns 404 if not found or belongs to a different user.
    """
    earning = await service.get_earning_by_id(
        earning_id=earning_id,
        user_id=current_user.user_id,
    )

    if not earning:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Earning {earning_id} not found",
        )

    return earning


# ── Update Earning ────────────────────────────────────────────────────────
@router.patch(
    "/{earning_id}",
    response_model=EarningResponse,
    status_code=status.HTTP_200_OK,
    summary="Partially update an earning",
)
async def update_earning(
    earning_id: UUID,
    body: EarningUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Partially updates an earning (PATCH semantics).
    amount_mxn recalculated automatically if amount or currency changes.
    """
    try:
        earning = await service.update_earning(
            earning_id=earning_id,
            user_id=current_user.user_id,
            data=body,
        )

        if not earning:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Earning {earning_id} not found",
            )

        return earning

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ── Delete Earning ────────────────────────────────────────────────────────
@router.delete(
    "/{earning_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an earning",
)
async def delete_earning(
    earning_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Deletes an earning by ID.
    Returns 204 No Content on success.
    Returns 404 if not found or belongs to a different user.
    """
    deleted = await service.delete_earning(
        earning_id=earning_id,
        user_id=current_user.user_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Earning {earning_id} not found",
        )


# ── Weekly Summary ────────────────────────────────────────────────────────
@router.get(
    "/weekly/{week_year}/{week_number}",
    status_code=status.HTTP_200_OK,
    summary="Get weekly earnings summary by category",
)
async def get_weekly_summary(
    week_year:   int,
    week_number: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns total income per category for a specific ISO week.
    Used alongside expenses weekly summary for cash flow view.
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
    summary="Bulk import earnings from JSON",
)
async def import_earnings(
    body: list[EarningCreate],
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Bulk imports a list of earnings for the authenticated user.
    """
    created = 0
    errors  = []

    for i, item in enumerate(body):
        try:
            await service.create_earning(
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
    summary="Delete all earnings for the current user",
)
async def delete_all_earnings(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Deletes ALL earning records belonging to the authenticated user.

    Irreversible.
    """
    deleted = await service.delete_all_earnings(user_id=current_user.user_id)
    return {"deleted": deleted, "message": f"Deleted {deleted} earnings"}

