from typing import Optional
from uuid import UUID
import logging

from app.database import db, fetch_one
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
        db()
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
    result = fetch_one(
        db()
        .table("categories")
        .select("*")
        .eq("id", str(category_id))
        .or_(f"user_id.is.null,user_id.eq.{user_id}")
    )

    if not result:
        return None

    result["is_system"] = result.get("user_id") is None
    return result


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
        db()
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
        db()
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


class CategoryInUse(Exception):
    """
    Raised instead of deleting a category that still has movements.

    Carries the per-table counts so the API can tell the user what is in
    the way rather than just refusing.
    """

    def __init__(self, counts: dict[str, int]) -> None:
        self.counts = counts
        total = sum(counts.values())
        super().__init__(f"category still referenced by {total} records")


# Every table that points at a category, and the column it points with.
# goals uses savings_category_id rather than category_id, which is easy to
# miss — a goal whose savings category vanished silently stops tracking
# progress, because contributions are found through that category.
CATEGORY_REFERENCES = [
    ("expenses",        "category_id"),
    ("earnings",        "category_id"),
    ("budgets",         "category_id"),
    ("recurring_rules", "category_id"),
    ("projected_costs", "category_id"),
    ("goals",           "savings_category_id"),
]


async def count_category_references(category_id: UUID, user_id: str) -> dict[str, int]:
    """
    Counts the rows that would be orphaned by deleting this category.

    Scoped to the owner as well as the category. Without the user_id filter
    one user's rows could block another user's delete, which is both a leak
    of the fact those rows exist and a denial of service.
    """
    counts: dict[str, int] = {}

    for table, column in CATEGORY_REFERENCES:
        result = (
            db()
            .table(table)
            .select("id")
            .eq(column, str(category_id))
            .eq("user_id", user_id)
            .execute()
        )
        found = len(result.data or [])
        if found:
            counts[table] = found

    return counts


async def delete_category(
    category_id: UUID,
    user_id: str,
) -> bool:
    """
    Deletes a user-owned category, but only if nothing still uses it.

    Raises CategoryInUse when movements reference it.

    The schema says ON DELETE SET NULL, so the database would happily
    accept this delete and quietly rewrite history around it:

      - every past expense and earning in that category becomes
        "Uncategorized", so previous months silently re-report
      - a budget scoped to that category becomes a budget over ALL
        categories, which changes what it measures without changing
        anything the user can see
      - a recurring rule keeps firing, now uncategorised, forever
      - a goal loses the category its contributions are counted through,
        so its progress resets to zero while the money stays spent

    None of that is recoverable from the API, because the old category_id
    is gone. Refusing the delete is the only honest option; the user can
    reassign or remove the movements first.

    System categories remain unreachable here: .eq("user_id") can never
    match a row whose user_id is null.
    """
    counts = await count_category_references(category_id, user_id)
    if counts:
        raise CategoryInUse(counts)

    result = (
        db()
        .table("categories")
        .delete()
        .eq("id", str(category_id))
        # Prevents deletion of system categories (user_id=NULL)
        .eq("user_id", user_id)
        .execute()
    )

    return len(result.data) > 0


async def delete_all_categories(user_id: str) -> dict:
    """
    Deletes the user's own categories, skipping any still in use.

    Two things make this different from the other bulk deletes.

    System categories are never touched: .eq("user_id") cannot match a row
    whose user_id is null, so the shared defaults survive by construction.

    And each category is checked for references first, for the same reason
    the single delete refuses — ON DELETE SET NULL would quietly rewrite
    history rather than fail. Categories still in use are reported back
    instead of being removed, so the Settings screen can say what is left
    and why.

    The full reset therefore wipes movements first and categories last, at
    which point nothing references them and everything goes.
    """
    owned = (
        db()
        .table("categories")
        .select("id, name")
        .eq("user_id", user_id)
        .execute()
    ).data or []

    deleted = 0
    skipped: dict[str, int] = {}

    for category in owned:
        counts = await count_category_references(category["id"], user_id)
        if counts:
            skipped[category["name"]] = sum(counts.values())
            continue

        db().table("categories").delete().eq(
            "id", category["id"]
        ).eq("user_id", user_id).execute()
        deleted += 1

    logger.info(
        f"Deleted {deleted} categories for user {user_id}, "
        f"skipped {len(skipped)} still in use"
    )
    return {"deleted": deleted, "skipped": skipped}
