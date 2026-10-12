from fastapi  import APIRouter, Depends, HTTPException, status
from uuid     import UUID
import logging

from app.auth.dependencies  import get_current_user, AuthenticatedUser
from app.projected          import service
from app.projected.schemas  import (
    ProjectedCostCreate,
    ProjectedCostUpdate,
    ProjectedCostResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Projected Costs"])


@router.get(
    "/",
    status_code=status.HTTP_200_OK,
    summary="List all projected costs",
)
async def list_projected_costs(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return await service.list_projected_costs(user_id=current_user.user_id)


@router.get(
    "/monthly",
    status_code=status.HTTP_200_OK,
    summary="Get total projected spending for a month",
)
async def get_monthly_projection(
    year:         int,
    month:        int,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return await service.get_monthly_projection(
        user_id=current_user.user_id,
        year=year,
        month=month,
    )


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Create a projected cost",
)
async def create_projected_cost(
    body:         ProjectedCostCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return await service.create_projected_cost(
        user_id=current_user.user_id,
        data=body,
    )


@router.patch(
    "/{cost_id}",
    status_code=status.HTTP_200_OK,
    summary="Update a projected cost",
)
async def update_projected_cost(
    cost_id:      UUID,
    body:         ProjectedCostUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    result = await service.update_projected_cost(
        cost_id=cost_id,
        user_id=current_user.user_id,
        data=body,
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Projected cost not found",
        )
    return result


@router.delete(
    "/{cost_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a projected cost",
)
async def delete_projected_cost(
    cost_id:      UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    deleted = await service.delete_projected_cost(
        cost_id=cost_id,
        user_id=current_user.user_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Projected cost not found",
        )


# ── Delete All Projected Costs ────────────────────────────────────────────
@router.delete(
    "/",
    status_code=status.HTTP_200_OK,
    summary="Delete all projected costs for the current user",
)
async def delete_all_projected_costs(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Deletes ALL projected costs belonging to the authenticated user.

    Forecast data only — no real transaction is affected. Irreversible.
    """
    deleted = await service.delete_all_projected_costs(
        user_id=current_user.user_id
    )
    return {"deleted": deleted, "message": f"Deleted {deleted} projected costs"}
