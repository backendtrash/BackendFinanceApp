from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional
from uuid import UUID
import logging

from app.auth.dependencies import get_current_user, AuthenticatedUser
from app.budgets.schemas import (
    BudgetCreate,
    BudgetUpdate,
    BudgetResponse,
    BudgetAlertResponse,
)
from app.budgets import service

# ── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ── Router ────────────────────────────────────────────────────────────────
router = APIRouter()


# ── List Budgets ──────────────────────────────────────────────────────────
@router.get(
    "/",
    response_model=list[BudgetResponse],
    status_code=status.HTTP_200_OK,
    summary="List all budgets with current spending progress",
)
async def list_budgets(
    active_only: bool = Query(True, description="Return only active budgets"),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns all budgets enriched with current period spending.
    Each budget includes spent_amount, pct_spent, and remaining.
    Frontend can use these to render progress bars directly.
    """
    return await service.list_budgets(
        user_id=current_user.user_id,
        active_only=active_only,
    )


# ── Get Budget Alerts ─────────────────────────────────────────────────────
# Registered before /{budget_id} to prevent route conflict
@router.get(
    "/alerts",
    response_model=list[BudgetAlertResponse],
    status_code=status.HTTP_200_OK,
    summary="Get budget alert history",
)
async def get_budget_alerts(
    limit: int = Query(20, description="Number of alerts to return"),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns recent budget alerts for the authenticated user.
    Ordered by most recent first.
    """
    return await service.get_budget_alerts(
        user_id=current_user.user_id,
        limit=limit,
    )



# ── Clear Budget Alerts ──────────────────────────────────────────────────
@router.delete(
    "/alerts",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear all budget alerts for the current user",
)
async def clear_budget_alerts(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Deletes all budget alert records for the authenticated user.
    Useful for dismissing all over-budget warnings at once.
    """
    await service.clear_budget_alerts(user_id=current_user.user_id)

# ── Create Budget ─────────────────────────────────────────────────────────
@router.post(
    "/",
    response_model=BudgetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new budget",
)
async def create_budget(
    body: BudgetCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Creates a new budget for the authenticated user.
    Returns 409 if a budget for the same category+period already exists.
    """
    try:
        budget = await service.create_budget(
            user_id=current_user.user_id,
            data=body,
        )
        return budget

    except RuntimeError as e:
        if "23505" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A budget for this category and period already exists",
            )
        logger.error(f"Failed to create budget: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create budget",
        )


# ── Get Single Budget ─────────────────────────────────────────────────────
@router.get(
    "/{budget_id}",
    response_model=BudgetResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a single budget by ID",
)
async def get_budget(
    budget_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns a single budget with current spending progress.
    Returns 404 if not found or belongs to a different user.
    """
    budget = await service.get_budget_by_id(
        budget_id=budget_id,
        user_id=current_user.user_id,
    )

    if not budget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Budget {budget_id} not found",
        )

    return budget


# ── Get Alerts for Specific Budget ────────────────────────────────────────
@router.get(
    "/{budget_id}/alerts",
    response_model=list[BudgetAlertResponse],
    status_code=status.HTTP_200_OK,
    summary="Get alert history for a specific budget",
)
async def get_alerts_for_budget(
    budget_id: UUID,
    limit: int = Query(20, description="Number of alerts to return"),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns alert history for a specific budget.
    Useful for budget detail screen showing alert timeline.
    """
    return await service.get_budget_alerts(
        user_id=current_user.user_id,
        budget_id=budget_id,
        limit=limit,
    )


# ── Update Budget ─────────────────────────────────────────────────────────
@router.patch(
    "/{budget_id}",
    response_model=BudgetResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a budget",
)
async def update_budget(
    budget_id: UUID,
    body: BudgetUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Partially updates a budget.
    limit_amount, currency_id, alert_threshold, is_active are updatable.
    period and category_id cannot be changed after creation.
    """
    budget = await service.update_budget(
        budget_id=budget_id,
        user_id=current_user.user_id,
        data=body,
    )

    if not budget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Budget {budget_id} not found",
        )

    return budget


# ── Delete Budget ─────────────────────────────────────────────────────────
@router.delete(
    "/{budget_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a budget",
)
async def delete_budget(
    budget_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Deletes a budget and all its associated alerts.
    Returns 404 if not found or belongs to a different user.
    """
    deleted = await service.delete_budget(
        budget_id=budget_id,
        user_id=current_user.user_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Budget {budget_id} not found",
        )


# ── Delete All Budgets ────────────────────────────────────────────────────
@router.delete(
    "/",
    status_code=status.HTTP_200_OK,
    summary="Delete all budgets for the current user",
)
async def delete_all_budgets(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Deletes ALL budgets belonging to the authenticated user.

    Alert history goes with them, by cascade. Irreversible.
    """
    deleted = await service.delete_all_budgets(user_id=current_user.user_id)
    return {"deleted": deleted, "message": f"Deleted {deleted} budgets"}
