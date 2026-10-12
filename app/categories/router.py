from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional
from uuid import UUID
import logging

from app.auth.dependencies import get_current_user, AuthenticatedUser
from app.categories.schemas import (
    CategoryCreate,
    CategoryUpdate,
    CategoryResponse,
    TransactionType,
)
from app.categories import service

# ── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ── Router ────────────────────────────────────────────────────────────────
router = APIRouter()


# ── List Categories ───────────────────────────────────────────────────────
@router.get(
    "/",
    response_model=list[CategoryResponse],
    status_code=status.HTTP_200_OK,
    summary="List all categories visible to the user",
)
async def list_categories(
    type: Optional[TransactionType] = Query(
        None,
        description="Filter by type: 'expense' or 'income'"
    ),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns system categories + user's own custom categories.
    Optionally filtered by transaction type.
    is_system=True means category is read-only (cannot edit/delete).
    """
    return await service.list_categories(
        user_id=current_user.user_id,
        type_filter=type.value if type else None,
    )


# ── Get Single Category ───────────────────────────────────────────────────
@router.get(
    "/{category_id}",
    response_model=CategoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a single category by ID",
)
async def get_category(
    category_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns a single category by ID.
    Returns both system and user-owned categories.
    Returns 404 if not found or belongs to another user.
    """
    category = await service.get_category_by_id(
        category_id=category_id,
        user_id=current_user.user_id,
    )

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category {category_id} not found",
        )

    return category


# ── Create Category ───────────────────────────────────────────────────────
@router.post(
    "/",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a custom category",
)
async def create_category(
    body: CategoryCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Creates a new custom category owned by the authenticated user.
    Cannot create system categories (user_id=NULL) via this endpoint.
    Returns 409 if a category with the same name+type already exists.
    """
    try:
        category = await service.create_category(
            user_id=current_user.user_id,
            data=body,
        )
        return category

    except RuntimeError as e:
        # Check if it is a unique constraint violation
        # Supabase returns error code 23505 for unique violations
        if "23505" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Category '{body.name}' of type '{body.type}' already exists",
            )
        logger.error(f"Failed to create category: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create category",
        )


# ── Update Category ───────────────────────────────────────────────────────
@router.patch(
    "/{category_id}",
    response_model=CategoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a custom category",
)
async def update_category(
    category_id: UUID,
    body: CategoryUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Updates a user-owned category.
    Returns 404 if not found or if trying to update a system category.
    type cannot be changed after creation.
    """
    category = await service.update_category(
        category_id=category_id,
        user_id=current_user.user_id,
        data=body,
    )

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category {category_id} not found or is a system category",
        )

    return category


# ── Delete Category ───────────────────────────────────────────────────────
@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a custom category",
)
async def delete_category(
    category_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Deletes a user-owned category.

    404 if it does not exist, or is a system category.
    409 if movements still reference it, with the counts per table so the
    client can tell the user what is in the way.
    """
    try:
        deleted = await service.delete_category(
            category_id=category_id,
            user_id=current_user.user_id,
        )
    except service.CategoryInUse as in_use:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    "This category still has movements. Reassign or delete "
                    "them before removing the category."
                ),
                "references": in_use.counts,
            },
        )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category {category_id} not found or is a system category",
        )


# ── Delete All Custom Categories ──────────────────────────────────────────
@router.delete(
    "/",
    status_code=status.HTTP_200_OK,
    summary="Delete all custom categories for the current user",
)
async def delete_all_categories(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Deletes the authenticated user's own categories.

    System categories are never removed. Categories still referenced by
    movements are skipped rather than deleted, for the same reason the
    single delete returns 409 — removing one would silently rewrite the
    history filed under it. The response lists what was skipped and how
    many records are holding each one.

    In a full reset, call this last: once movements are gone nothing
    references the categories and they all go.
    """
    return await service.delete_all_categories(user_id=current_user.user_id)
