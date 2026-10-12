from fastapi import APIRouter, Depends, status

from app.auth.dependencies  import get_current_user, AuthenticatedUser
from app.preferences        import service
from app.preferences.schemas import PreferencesUpdate, PreferencesResponse

router = APIRouter(tags=["Preferences"])


@router.get(
    "/",
    status_code=status.HTTP_200_OK,
    summary="Get user preferences",
)
async def get_preferences(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return await service.get_preferences(user_id=current_user.user_id)


@router.patch(
    "/",
    status_code=status.HTTP_200_OK,
    summary="Update user preferences",
)
async def update_preferences(
    body:         PreferencesUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return await service.update_preferences(
        user_id=current_user.user_id,
        data=body,
    )


# ── Reset Preferences ─────────────────────────────────────────────────────
@router.delete(
    "/",
    response_model=PreferencesResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset preferences to defaults",
)
async def reset_preferences(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns the authenticated user's preferences to their defaults.

    A reset rather than a delete: every read path assumes the row exists,
    so writing the defaults back is the same result with one fewer moving
    part.
    """
    return await service.reset_preferences(user_id=current_user.user_id)
