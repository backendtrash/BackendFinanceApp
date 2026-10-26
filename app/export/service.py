"""
Settings -> "Export all data": every row the user owns, as one JSON file.

Read through the caller's own client, so row level security decides what
comes back as well as the user_id filter. Shared rows that are not the
user's — currencies, the system categories — are left out, except that
system categories the user's rows point to are listed, so a category_id in
the file can always be read.
"""
from datetime import datetime, timezone

from app.database import db

# Supabase caps every response at 1,000 rows (PostgREST max-rows). A plain
# select would cut a long history off there without saying so, so each
# table is read in pages until one comes back short.
PAGE = 1000

OWNED_TABLES = (
    "expenses",
    "earnings",
    "categories",
    "budgets",
    "budget_alerts",
    "recurring_rules",
    "goals",
    "projected_costs",
    "user_preferences",
)


def _all_rows(table: str, user_id: str) -> list[dict]:
    rows: list[dict] = []
    while True:
        page = (
            db()
            .table(table)
            .select("*")
            .eq("user_id", user_id)
            .order("id")
            .range(len(rows), len(rows) + PAGE - 1)
            .execute()
        ).data or []
        rows.extend(page)
        if len(page) < PAGE:
            return rows


def _system_categories(ids: set[str]) -> list[dict]:
    if not ids:
        return []
    return (
        db()
        .table("categories")
        .select("*")
        .is_("user_id", "null")
        .in_("id", sorted(ids))
        .execute()
    ).data or []


async def export_user_data(user_id: str, email: str | None) -> dict:
    tables = {name: _all_rows(name, user_id) for name in OWNED_TABLES}

    own = {c["id"] for c in tables["categories"]}
    used = {
        row["category_id"]
        for name in ("expenses", "earnings", "budgets", "recurring_rules", "projected_costs")
        for row in tables[name]
        if row.get("category_id") and row["category_id"] not in own
    }

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account":     {"id": user_id, "email": email},
        "counts":      {name: len(rows) for name, rows in tables.items()},
        "tables":      tables,
        "system_categories_referenced": _system_categories(used),
    }
