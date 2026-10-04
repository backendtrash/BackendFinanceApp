from app.database import supabase_admin
import logging

logger = logging.getLogger(__name__)

DEFAULT_PREFERENCES = {
    "week_start_day": 1,  # Monday by default (ISO standard)
}


async def get_preferences(user_id: str) -> dict:
    """
    Returns user preferences.
    If no preferences exist yet creates defaults automatically.
    This ensures every user always has a preferences record.
    """
    result = (
        supabase_admin
        .table("user_preferences")
        .select("*")
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    if result.data:
        return result.data

    # Auto-create default preferences for new users
    created = (
        supabase_admin
        .table("user_preferences")
        .insert({
            "user_id":        user_id,
            **DEFAULT_PREFERENCES,
        })
        .execute()
    )

    return created.data[0] if created.data else {
        "user_id":        user_id,
        "week_start_day": 1,
    }


async def update_preferences(user_id: str, data: object) -> dict:
    """
    Updates user preferences using upsert.
    Creates the record if it doesn't exist yet.
    """
    payload = {"user_id": user_id}

    if data.week_start_day is not None:
        payload["week_start_day"] = data.week_start_day

    result = (
        supabase_admin
        .table("user_preferences")
        .upsert(payload, on_conflict="user_id")
        .execute()
    )

    if not result.data:
        raise RuntimeError("Failed to update preferences")

    return result.data[0]