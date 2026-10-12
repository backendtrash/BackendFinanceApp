from typing import Optional
from uuid import UUID
import logging

from app.database import supabase_admin
from app.categories.schemas import CategoryCreate, CategoryUpdate

# ── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)


async def list_categories(
    user_id: str,
    type_filter: Optional[str] = None,
) -> list[dict]:
    """
    Returns all categories visible to a user:
      - System categories (user_id IS NULL)
      - User's own custom categories

    Adds is_system flag to each row:
      True  → user_id is NULL (system default, not editable)
      False → user_id matches current user (custom, editable)

    Optional type_filter limits to 'expense' or 'income' categories.
    """
    query = (
        supabase_admin
        .table("categories")
        .select("*")
        .or_(f"user_id.is.null,user_id.eq.{user_id}")
        .order("name")
    )

    if type_filter:
        query = query.eq("type", type_filter)

    result = query.execute()
    categories = result.data or []

    # Inject is_system flag based on whether user_id is NULL
    # Frontend uses this to show/hide edit and delete buttons
    for category in categories:
        category["is_system"] = category.get("user_id") is None

    return categories


async def get_category_by_id(
    category_id: UUID,
    user_id: str,
) -> Optional[dict]:
    """
    Fetches a single category visible to the user.
    Returns system categories OR user-owned categories.
    Returns None if not found or belongs to another user.
    """
    result = (
        supabase_admin
        .table("categories")
        .select("*")
        .eq("id", str(category_id))
        .or_(f"user_id.is.null,user_id.eq.{user_id}")
        .single()
        .execute()
    )

    if not result.data:
        return None

    result.data["is_system"] = result.data.get("user_id") is None
    return result.data


async def create_category(
    user_id: str,
    data: CategoryCreate,
) -> dict:
    """
    Creates a new custom category owned by the user.
    user_id is always injected from JWT — never from request body.
    This prevents users from creating system categories (user_id=NULL).
    """
    payload = {
        "user_id": user_id,
        "name":    data.name,
        "color":   data.color,
        "icon":    data.icon,
        "type":    data.type.value,
    }

    result = (
        supabase_admin
        .table("categories")
        .insert(payload)
        .execute()
    )

    if not result.data:
        raise RuntimeError("Failed to create category")

    created = result.data[0]
    created["is_system"] = False
    return created


async def update_category(
    category_id: UUID,
    user_id: str,
    data: CategoryUpdate,
) -> Optional[dict]:
    """
    Updates a user-owned category.
    System categories (user_id=NULL) cannot be updated via this function.
    The .eq("user_id", user_id) filter ensures system categories
    are never matched — returns None instead of updating them.
    """
    payload: dict = {}

    if data.name is not None:
        payload["name"] = data.name

    if data.color is not None:
        payload["color"] = data.color

    if data.icon is not None:
        payload["icon"] = data.icon

    if not payload:
        return await get_category_by_id(category_id, user_id)

    result = (
        supabase_admin
        .table("categories")
        .update(payload)
        .eq("id", str(category_id))
        # Critical: only update user-owned categories
        # System categories have user_id=NULL → never matched here
        .eq("user_id", user_id)
        .execute()
    )

    if not result.data:
        return None

    result.data[0]["is_system"] = False
    return result.data[0]


async def delete_category(
    category_id: UUID,
    user_id: str,
) -> bool:
    """
    Deletes a user-owned category.
    System categories cannot be deleted — .eq("user_id") prevents it.
    Linked expenses/earnings keep their category_id as NULL
    after deletion (ON DELETE SET NULL in schema).
    """
    result = (
        supabase_admin
        .table("categories")
        .delete()
        .eq("id", str(category_id))
        # Prevents deletion of system categories (user_id=NULL)
        .eq("user_id", user_id)
        .execute()
    )

    return len(result.data) > 0