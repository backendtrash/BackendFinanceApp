from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID
import logging

from app.auth.dependencies import get_current_user, AuthenticatedUser
from app.goals.schemas import GoalCreate, GoalUpdate, GoalResponse
from app.goals import service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/",
    response_model=list[GoalResponse],
    status_code=status.HTTP_200_OK,
    summary="List all goals with progress",
)
async def list_goals(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return await service.list_goals(user_id=current_user.user_id)


@router.post(
    "/",
    response_model=GoalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new goal",
)
async def create_goal(
    body: GoalCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        return await service.create_goal(
            user_id=current_user.user_id,
            data=body,
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get(
    "/{goal_id}",
    response_model=GoalResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a single goal",
)
async def get_goal(
    goal_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    goal = await service.get_goal_by_id(
        goal_id=goal_id,
        user_id=current_user.user_id,
    )
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal {goal_id} not found",
        )
    return goal


@router.patch(
    "/{goal_id}",
    response_model=GoalResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a goal",
)
async def update_goal(
    goal_id: UUID,
    body: GoalUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    goal = await service.update_goal(
        goal_id=goal_id,
        user_id=current_user.user_id,
        data=body,
    )
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal {goal_id} not found",
        )
    return goal


@router.delete(
    "/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a goal",
)
async def delete_goal(
    goal_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    deleted = await service.delete_goal(
        goal_id=goal_id,
        user_id=current_user.user_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal {goal_id} not found",
        )