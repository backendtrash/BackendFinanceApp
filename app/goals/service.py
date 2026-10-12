from decimal import Decimal
from typing import Optional
from uuid import UUID
from datetime import date, timedelta
import calendar
import logging

from app.database import supabase_admin
from app.goals.schemas import GoalCreate, GoalUpdate,GoalType

logger = logging.getLogger(__name__)


async def calculate_total_savings(
    user_id:             str,
    since_date:          Optional[str] = None,
    savings_category_id: Optional[str] = None,
) -> Decimal:
    """
    Calculates total contributions to a goal.

    If savings_category_id is provided:
      Sums ALL expenses tagged with that category since goal creation.
      Goal contributions are now expenses — they reduce net balance
      and count toward goal progress simultaneously.

    If no category provided:
      Falls back to net savings (earnings - expenses).
    """
    if savings_category_id:
        # Goal contributions = expenses in the linked category
        query = (
            supabase_admin
            .table("expenses")
            .select("amount_mxn")
            .eq("user_id", user_id)
            .eq("category_id", savings_category_id)
        )
        if since_date:
            query = query.gte("date", since_date)

        result = query.execute()
        total  = Decimal("0") + sum(
            Decimal(str(e["amount_mxn"]))
            for e in (result.data or [])
        )
        return round(total, 2)

    # No category → net savings (earnings - expenses)
    expenses_query = (
        supabase_admin
        .table("expenses")
        .select("amount_mxn")
        .eq("user_id", user_id)
    )
    if since_date:
        expenses_query = expenses_query.gte("date", since_date)

    expenses_result = expenses_query.execute()

    earnings_result = (
        supabase_admin
        .table("earnings")
        .select("amount_mxn")
        .eq("user_id", user_id)
        .execute()
    )

    total_earnings = Decimal("0") + sum(
        Decimal(str(e["amount_mxn"]))
        for e in (earnings_result.data or [])
    )
    total_expenses = Decimal("0") + sum(
        Decimal(str(e["amount_mxn"]))
        for e in (expenses_result.data or [])
    )

    return round(total_earnings - total_expenses, 2)


async def calculate_current_savings_rate(user_id: str) -> Decimal:
    """
    Calculates average monthly savings rate over last 3 months.
    Formula: (income - expenses) / income * 100
    Returns 0 if no income recorded.
    """
    today      = date.today()
    start_date = date(today.year, today.month, 1)

    # Go back 3 months
    for _ in range(2):
        month = start_date.month - 1
        year  = start_date.year
        if month == 0:
            month = 12
            year -= 1
        start_date = date(year, month, 1)

    earnings_result = (
        supabase_admin
        .table("earnings")
        .select("amount_mxn")
        .eq("user_id", user_id)
        .gte("date", start_date.isoformat())
        .execute()
    )
    expenses_result = (
        supabase_admin
        .table("expenses")
        .select("amount_mxn")
        .eq("user_id", user_id)
        .gte("date", start_date.isoformat())
        .execute()
    )

    total_income   = sum(
        Decimal(str(e["amount_mxn"]))
        for e in (earnings_result.data or [])
    )
    total_expenses = sum(
        Decimal(str(e["amount_mxn"]))
        for e in (expenses_result.data or [])
    )

    if total_income <= 0:
        return Decimal("0")

    return round((total_income - total_expenses) / total_income * 100, 2)


async def enrich_goal(user_id: str, goal: dict) -> dict:
    """
    Adds computed progress fields to a goal.

    Fixed amount goals:
      current_savings:      total net savings in MXN
      pct_complete:         current / target * 100
      months_remaining:     months until deadline
      projected_completion: date when goal will be reached
                            based on average monthly savings rate

    Monthly rate goals:
      current_rate_pct:     actual savings rate last 3 months
      on_track:             current_rate >= target_rate
    """
    today = date.today()

    if goal["type"] == "fixed_amount":
        # Scope savings to goal creation date
        since_date           = goal.get("created_at", "")[:10]
        savings_category_id  = goal.get("savings_category_id")
        current              = await calculate_total_savings(
            user_id,
            since_date,
            savings_category_id,
        )

        # Add initial amount — never affects net balance
        initial = Decimal(str(goal.get("initial_amount") or 0))
        current = max(current or Decimal("0"), Decimal("0")) + initial

        # Convert target to MXN for consistent comparison
        # current_savings is always in MXN (from amount_mxn)
        # target_amount may be in any currency
        raw_target   = Decimal(str(goal["target_amount"] or 0))
        currency_id  = goal.get("currency_id")

        if currency_id:
            cur_result = (
                supabase_admin
                .table("currencies")
                .select("exchange_rate, code")
                .eq("id", currency_id)
                .single()
                .execute()
            )
            if cur_result.data:
                rate   = Decimal(str(cur_result.data["exchange_rate"]))
                target = round(raw_target * rate, 2)
            else:
                target = raw_target
        else:
            target = raw_target

        pct_complete = (
            round(current / target * 100, 2)
            if target > 0 else Decimal("0")
        )

        # Months remaining until deadline
        months_remaining = None
        if goal.get("deadline"):
            deadline = date.fromisoformat(goal["deadline"])
            months_remaining = max(
                0,
                (deadline.year - today.year) * 12
                + (deadline.month - today.month)
            )

        # Projected completion based on average monthly savings
        projected_completion = None
        if current < target:
            # Calculate average monthly savings over last 3 months
            start_3m = date(today.year, today.month, 1)
            for _ in range(2):
                m = start_3m.month - 1
                y = start_3m.year
                if m == 0:
                    m = 12
                    y -= 1
                start_3m = date(y, m, 1)

            # Use the later of: goal creation date or 3 months ago
            since_dt   = date.fromisoformat(since_date)
            cutoff     = max(since_dt, start_3m)

            earn_3m = (
                supabase_admin
                .table("earnings")
                .select("amount_mxn")
                .eq("user_id", user_id)
                .gte("date", cutoff.isoformat())
                .execute()
            )
            exp_3m = (
                supabase_admin
                .table("expenses")
                .select("amount_mxn")
                .eq("user_id", user_id)
                .gte("date", cutoff.isoformat())
                .execute()
            )

            monthly_income = sum(
                Decimal(str(e["amount_mxn"]))
                for e in (earn_3m.data or [])
            ) / Decimal("3")

            monthly_expense = sum(
                Decimal(str(e["amount_mxn"]))
                for e in (exp_3m.data or [])
            ) / Decimal("3")

            monthly_savings = monthly_income - monthly_expense

            if monthly_savings > 0:
                months_needed = int((target - current) / monthly_savings) + 1
                proj_date = today + timedelta(days=months_needed * 30)
                projected_completion = proj_date.isoformat()

        goal["current_savings"]      = current
        goal["pct_complete"]         = pct_complete
        goal["months_remaining"]     = months_remaining
        goal["projected_completion"] = projected_completion

    else:
        # Monthly rate goal
        current_rate = await calculate_current_savings_rate(user_id)
        target_rate  = Decimal(str(goal["target_rate_pct"] or 0))

        goal["current_rate_pct"] = current_rate
        goal["on_track"]         = current_rate >= target_rate

    return goal


async def create_goal(user_id: str, data: GoalCreate) -> dict:
    """
    Creates a new goal and automatically creates a linked income category.

    For fixed_amount goals:
      - Auto-creates an income category named after the goal
      - Links the goal to that category via savings_category_id
      - User can immediately tag earnings with that category
      - No manual category creation or linking needed

    For monthly_rate goals:
      - No category needed — tracks overall savings rate
    """
    # ── Auto-create income category for fixed amount goals ────────────────
    auto_category_id = None

    if data.type == GoalType.fixed_amount and not data.savings_category_id:
        # Cycle through palette so multiple goals have distinct colors
        goal_colors = [
            "#22C55E", "#6366F1", "#F59E0B", "#EC4899",
            "#14B8A6", "#F97316", "#8B5CF6", "#06B6D4",
        ]

        # Count existing goals to pick next color in palette
        existing = (
            supabase_admin
            .table("goals")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .execute()
        )
        color_index    = (existing.count or 0) % len(goal_colors)
        category_color = goal_colors[color_index]

        # Create expense category named after the goal
        cat_result = (
            supabase_admin
            .table("categories")
            .insert({
                "user_id": user_id,
                "name":    f"{data.name} Savings",
                "color":   category_color,
                "icon":    "trending-down",
                "type":    "expense",  # contributions are expenses now
            })
            .execute()
        )

        if cat_result.data:
            auto_category_id = cat_result.data[0]["id"]

    # ── Build goal payload ────────────────────────────────────────────────
    payload = {
        "user_id":   user_id,
        "name":      data.name,
        "type":      data.type.value,
        "notes":     data.notes,
        "is_active": True,
    }

    if data.target_amount is not None:
        payload["target_amount"] = str(data.target_amount)
    if data.currency_id is not None:
        payload["currency_id"] = str(data.currency_id)
    if data.deadline:
        payload["deadline"] = data.deadline
    if data.target_rate_pct is not None:
        payload["target_rate_pct"] = str(data.target_rate_pct)

    # Use auto-created category or manually provided one
    final_category_id = auto_category_id or (
        str(data.savings_category_id)
        if data.savings_category_id else None
    )
    if final_category_id:
        payload["savings_category_id"] = final_category_id

    # Store initial amount directly on goal — never creates an expense
    # so it never affects net balance calculations
    if data.start_amount and data.start_amount > 0:
        payload["initial_amount"] = str(data.start_amount)

    # ── Insert goal ───────────────────────────────────────────────────────
    result = (
        supabase_admin
        .table("goals")
        .insert(payload)
        .execute()
    )

    if not result.data:
        # Rollback: delete auto-created category if goal insert failed
        if auto_category_id:
            supabase_admin.table("categories").delete().eq(
                "id", auto_category_id
            ).execute()
        raise RuntimeError("Failed to create goal")

    goal = result.data[0]

    return await enrich_goal(user_id, goal)


async def list_goals(user_id: str) -> list[dict]:
    """
    Returns all goals enriched with current progress.

    Performance optimization:
    Instead of N separate DB queries (one per goal via enrich_goal),
    we fetch all earnings and expenses ONCE then calculate
    progress for each goal in Python.

    This reduces DB queries from O(N) to O(1) regardless of goal count.
    5 goals: was 15-20 queries → now 3 queries total.
    """
    # ── Fetch all goals ───────────────────────────────────────────────────
    result = (
        supabase_admin
        .table("goals")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=False)
        .execute()
    )

    goals = result.data or []
    if not goals:
        return []

    # ── Fetch all currencies once ─────────────────────────────────────────
    currencies_result = (
        supabase_admin
        .table("currencies")
        .select("id, exchange_rate")
        .execute()
    )
    currency_map = {
        c["id"]: Decimal(str(c["exchange_rate"]))
        for c in (currencies_result.data or [])
    }

    # ── Fetch ALL earnings once ───────────────────────────────────────────
    earnings_result = (
        supabase_admin
        .table("earnings")
        .select("amount_mxn, category_id, date")
        .eq("user_id", user_id)
        .execute()
    )
    all_earnings = earnings_result.data or []

    # ── Fetch ALL expenses once ───────────────────────────────────────────
    expenses_result = (
        supabase_admin
        .table("expenses")
        .select("amount_mxn, date, category_id")
        .eq("user_id", user_id)
        .execute()
    )
    all_expenses = expenses_result.data or []

    # ── Enrich each goal using pre-fetched data ───────────────────────────
    enriched = []
    today    = date.today()

    for goal in goals:
        since_date          = goal.get("created_at", "")[:10]
        savings_category_id = goal.get("savings_category_id")

        if goal["type"] == "fixed_amount":
            # Calculate current savings from pre-fetched data
            if savings_category_id:
                # Goal contributions = expenses in the linked category
                current = Decimal("0") + sum(
                    Decimal(str(e["amount_mxn"]))
                    for e in all_expenses
                    if e.get("category_id") == savings_category_id
                    and e["date"] >= since_date
                )
            else:
                # Net savings = earnings - expenses since goal creation
                current_earnings = Decimal("0") + sum(
                    Decimal(str(e["amount_mxn"]))
                    for e in all_earnings
                    if e["date"] >= since_date
                )
                current_expenses = Decimal("0") + sum(
                    Decimal(str(e["amount_mxn"]))
                    for e in all_expenses
                    if e["date"] >= since_date
                )
                current = current_earnings - current_expenses

            # Add initial amount — money already saved before goal creation
            # Stored on the goal itself, never affects net balance
            initial = Decimal(str(goal.get("initial_amount") or 0))
            current = max(current, Decimal("0")) + initial

            # Convert target to MXN
            raw_target  = Decimal(str(goal["target_amount"] or 0))
            currency_id = goal.get("currency_id")
            rate        = currency_map.get(currency_id, Decimal("1"))
            target      = round(raw_target * rate, 2)

            pct_complete = (
                round(current / target * 100, 2)
                if target > 0 else Decimal("0")
            )

            # Months remaining until deadline
            months_remaining = None
            if goal.get("deadline"):
                deadline = date.fromisoformat(goal["deadline"])
                months_remaining = max(
                    0,
                    (deadline.year - today.year) * 12
                    + (deadline.month - today.month)
                )

            # Projected completion from average monthly savings
            projected_completion = None
            if current < target:
                # Use last 3 months of relevant earnings for projection
                three_months_ago = date(
                    today.year - (1 if today.month <= 3 else 0),
                    (today.month - 3) % 12 or 12,
                    1,
                ).isoformat()

                if savings_category_id:
                    # Use expenses in goal category for projection
                    recent_contributions = sum(
                        Decimal(str(e["amount_mxn"]))
                        for e in all_expenses
                        if e.get("category_id") == savings_category_id
                        and e["date"] >= three_months_ago
                    )
                    monthly_savings = recent_contributions / Decimal("3")
                else:
                    recent_earn = sum(
                        Decimal(str(e["amount_mxn"]))
                        for e in all_earnings
                        if e["date"] >= three_months_ago
                    )
                    recent_exp = sum(
                        Decimal(str(e["amount_mxn"]))
                        for e in all_expenses
                        if e["date"] >= three_months_ago
                    )
                    monthly_savings = (recent_earn - recent_exp) / Decimal("3")

                if monthly_savings > 0:
                    months_needed    = int((target - current) / monthly_savings) + 1
                    proj_date        = today + timedelta(days=months_needed * 30)
                    projected_completion = proj_date.isoformat()

            goal["current_savings"]      = current
            goal["pct_complete"]         = pct_complete
            goal["months_remaining"]     = months_remaining
            goal["projected_completion"] = projected_completion

        else:
            # Monthly rate goal
            three_months_ago = date(
                today.year - (1 if today.month <= 3 else 0),
                (today.month - 3) % 12 or 12,
                1,
            ).isoformat()

            total_income = Decimal("0") + sum(
                Decimal(str(e["amount_mxn"]))
                for e in all_earnings
                if e["date"] >= three_months_ago
            )
            total_expenses = Decimal("0") + sum(
                Decimal(str(e["amount_mxn"]))
                for e in all_expenses
                if e["date"] >= three_months_ago
            )

            current_rate = (
                round((total_income - total_expenses) / total_income * 100, 2)
                if total_income > 0 else Decimal("0")
            )
            target_rate = Decimal(str(goal["target_rate_pct"] or 0))

            goal["current_rate_pct"] = current_rate
            goal["on_track"]         = current_rate >= target_rate

        enriched.append(goal)

    return enriched


async def get_goal_by_id(goal_id: UUID, user_id: str) -> Optional[dict]:
    """Fetches a single goal scoped to the authenticated user."""
    result = (
        supabase_admin
        .table("goals")
        .select("*")
        .eq("id", str(goal_id))
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    if not result.data:
        return None

    return await enrich_goal(user_id, result.data)


async def update_goal(
    goal_id: UUID,
    user_id: str,
    data: GoalUpdate,
) -> Optional[dict]:
    """Partially updates a goal."""
    payload: dict = {}

    if data.name is not None:
        payload["name"] = data.name
    if data.target_amount is not None:
        payload["target_amount"] = str(data.target_amount)
    if data.currency_id is not None:
        payload["currency_id"] = str(data.currency_id)
    if data.deadline is not None:
        payload["deadline"] = data.deadline
    if data.target_rate_pct is not None:
        payload["target_rate_pct"] = str(data.target_rate_pct)
    if data.notes is not None:
        payload["notes"] = data.notes
    if data.is_active is not None:
        payload["is_active"] = data.is_active

    if not payload:
        return await get_goal_by_id(goal_id, user_id)

    result = (
        supabase_admin
        .table("goals")
        .update(payload)
        .eq("id", str(goal_id))
        .eq("user_id", user_id)
        .execute()
    )

    if not result.data:
        return None

    return await enrich_goal(user_id, result.data[0])


async def delete_goal(goal_id: UUID, user_id: str) -> bool:
    """
    Deletes a goal and its auto-created savings category.

    The category is deleted so the user's category list stays clean.
    Past earnings tagged with that category keep their category_id
    set to NULL (ON DELETE SET NULL in schema) — history is preserved.
    The earnings themselves are never deleted.
    """
    # ── Fetch goal to get its linked category ─────────────────────────────
    goal_result = (
        supabase_admin
        .table("goals")
        .select("savings_category_id")
        .eq("id", str(goal_id))
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    if not goal_result.data:
        return False

    savings_category_id = goal_result.data.get("savings_category_id")

    # ── Delete the goal ───────────────────────────────────────────────────
    result = (
        supabase_admin
        .table("goals")
        .delete()
        .eq("id", str(goal_id))
        .eq("user_id", user_id)
        .execute()
    )

    if not result.data:
        return False

    # ── Delete the auto-created category ──────────────────────────────────
    # Only delete user-owned categories (not system categories)
    # Past earnings linked to this category will have category_id → NULL
    # via ON DELETE SET NULL — financial history is never lost
    if savings_category_id:
        supabase_admin.table("categories").delete().eq(
            "id", savings_category_id
        ).eq(
            "user_id", user_id  # safety check — only delete own categories
        ).execute()

    return True


async def delete_all_goals(user_id: str) -> int:
    """
    Deletes every goal belonging to this user and returns the count.

    The auto-created savings categories are deliberately left behind, along
    with the contributions filed under them. Those contributions are real
    expenses: money actually left the account, and deleting the goal does
    not undo that. Removing them here would silently change the user's
    spending history and net balance.
    """
    result = (
        supabase_admin
        .table("goals")
        .delete()
        .eq("user_id", user_id)
        .execute()
    )

    deleted = len(result.data or [])
    logger.info(f"Deleted {deleted} goals for user {user_id}")
    return deleted
