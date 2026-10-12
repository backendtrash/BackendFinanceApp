from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional
from uuid import UUID
from datetime import date
import logging

from app.auth.dependencies import get_current_user, AuthenticatedUser
from app.recurring.schemas import (
    RecurringRuleCreate,
    RecurringRuleUpdate,
    RecurringRuleResponse,
    ProcessRecurringResponse,
)
from app.recurring import service
from app.database import supabase_admin

# ── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ── Router ────────────────────────────────────────────────────────────────
router = APIRouter()


# ── Process Due Rules ─────────────────────────────────────────────────────
# Registered first — static path before /{rule_id}
@router.post(
    "/process",
    response_model=ProcessRecurringResponse,
    status_code=status.HTTP_200_OK,
    summary="Process all due recurring rules",
)
async def process_due_rules(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Manually triggers processing of all due recurring rules.
    In production this runs automatically at midnight daily.
    Useful for testing and catching up after downtime.
    Any authenticated user can trigger this safely —
    each rule is scoped to its owner via user_id.
    """
    try:
        return await service.process_due_rules()
    except Exception as e:
        logger.error(f"Failed to process recurring rules: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process recurring rules",
        )


# ── List Recurring Rules ──────────────────────────────────────────────────
@router.get(
    "/",
    response_model=list[RecurringRuleResponse],
    status_code=status.HTTP_200_OK,
    summary="List all recurring rules",
)
async def list_recurring_rules(
    active_only: bool = Query(
        False,
        description="Return only active rules"
    ),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns all recurring rules for the authenticated user.
    Includes both active and inactive rules by default.
    """
    return await service.list_recurring_rules(
        user_id=current_user.user_id,
        active_only=active_only,
    )


# ── Create Recurring Rule ─────────────────────────────────────────────────
@router.post(
    "/",
    response_model=RecurringRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new recurring rule",
)
async def create_recurring_rule(
    body: RecurringRuleCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Creates a new recurring rule that generates transactions automatically.
    First transaction is generated on start_date.
    Subsequent transactions are generated on each next_due_date.
    """
    # Validate end_date > start_date here because both values
    # need to be available simultaneously for comparison
    if body.end_date and body.end_date <= body.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be after start_date",
        )

    try:
        rule = await service.create_recurring_rule(
            user_id=current_user.user_id,
            data=body,
        )
        return rule

    except RuntimeError as e:
        logger.error(f"Failed to create recurring rule: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create recurring rule",
        )


# ── Get Single Rule ───────────────────────────────────────────────────────
@router.get(
    "/{rule_id}",
    response_model=RecurringRuleResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a single recurring rule by ID",
)
async def get_recurring_rule(
    rule_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns a single recurring rule by ID.
    Returns 404 if not found or belongs to a different user.
    """
    rule = await service.get_recurring_rule_by_id(
        rule_id=rule_id,
        user_id=current_user.user_id,
    )

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recurring rule {rule_id} not found",
        )

    return rule


# ── Update Recurring Rule ─────────────────────────────────────────────────
@router.patch(
    "/{rule_id}",
    response_model=RecurringRuleResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a recurring rule",
)
async def update_recurring_rule(
    rule_id: UUID,
    body: RecurringRuleUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Partially updates a recurring rule.
    type and frequency cannot be changed after creation.
    Set is_active=false to stop future transaction generation.
    """
    rule = await service.update_recurring_rule(
        rule_id=rule_id,
        user_id=current_user.user_id,
        data=body,
    )

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recurring rule {rule_id} not found",
        )

    return rule


# ── Delete Recurring Rule ─────────────────────────────────────────────────
@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a recurring rule",
)
async def delete_recurring_rule(
    rule_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Deletes a recurring rule.
    Previously generated transactions are preserved with is_recurring=True.
    Returns 404 if not found or belongs to a different user.
    """
    deleted = await service.delete_recurring_rule(
        rule_id=rule_id,
        user_id=current_user.user_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recurring rule {rule_id} not found",
        )
# ── Bulk Delete ───────────────────────────────────────────────────────────
@router.delete(
    "/",
    status_code=status.HTTP_200_OK,
    summary="Delete all recurring rules for the current user",
)
async def delete_all_rules(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Deletes ALL recurring rules belonging to the authenticated user.
    Previously generated transactions are preserved (recurring_rule_id → NULL).
    """
    result = (
        supabase_admin
        .table("recurring_rules")
        .delete()
        .eq("user_id", current_user.user_id)
        .execute()
    )
    count = len(result.data) if result.data else 0
    return {"deleted": count, "message": f"Deleted {count} rules"}