from app.database import db, fetch_one
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
    result = fetch_one(
        db()
        .table("user_preferences")
        .select("*")
        .eq("user_id", user_id)
    )

    if result:
        return result

    # Auto-create default preferences for new users
    created = (
        db()
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
        db()
        .table("user_preferences")
        .upsert(payload, on_conflict="user_id")
        .execute()
    )

    if not result.data:
        raise RuntimeError("Failed to update preferences")

    return result.data[0]


async def reset_preferences(user_id: str) -> dict:
    """
    Returns this user's preferences to their defaults.

    A reset rather than a delete, on purpose. Every read path assumes a row
    exists and creates one if it does not, and the write path upserts on
    user_id. Deleting the row would work but leaves the next read to
    recreate it, so writing the defaults straight back is the same outcome
    with one fewer moving part — and it keeps the row id stable.
    """
    payload = {"user_id": user_id, **DEFAULT_PREFERENCES}

    result = (
        db()
        .table("user_preferences")
        .upsert(payload, on_conflict="user_id")
        .execute()
    )

    if not result.data:
        raise RuntimeError("Failed to reset preferences")

    logger.info(f"Reset preferences to defaults for user {user_id}")
    return result.data[0]
