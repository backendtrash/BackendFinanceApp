from decimal import Decimal
from typing import Optional
from uuid import UUID
from datetime import date, timedelta
import calendar
import logging

from app.database import supabase_admin
from app.recurring.schemas import (
    RecurringRuleCreate,
    RecurringRuleUpdate,
    FrequencyType,
)

# ── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)


def calculate_next_due_date(
    current_due: date,
    frequency: str,
    day_of_week:  Optional[int] = None,
    day_of_month: Optional[int] = None,
) -> date:
    """
    Advances next_due_date by one frequency interval.
    Respects day_of_week and day_of_month targeting.

    weekly  + day_of_week:  always lands on correct weekday
    monthly + day_of_month: always lands on correct day of month
    """
    if frequency == FrequencyType.weekly.value:
        next_date = current_due + timedelta(weeks=1)

        # Correct to target weekday if specified
        if day_of_week is not None:
            days_ahead = day_of_week - next_date.weekday()
            if days_ahead != 0:
                next_date = next_date + timedelta(days=days_ahead)

        return next_date

    else:
        # Monthly advance
        month = current_due.month + 1
        year  = current_due.year
        if month > 12:
            month = 1
            year += 1

        # Use day_of_month target or original day
        target_day = day_of_month if day_of_month is not None else current_due.day
        max_day    = calendar.monthrange(year, month)[1]
        day        = min(target_day, max_day)

        return date(year, month, day)


async def create_recurring_rule(
    user_id: str,
    data: RecurringRuleCreate,
) -> dict:
    """
    Creates a new recurring rule.
    Calculates first next_due_date based on frequency and day targeting:
      Weekly:  finds the next occurrence of the specified weekday
               from start_date forward
      Monthly: sets next_due_date to day_of_month of current or next month
    """
    # ── Calculate first next_due_date ─────────────────────────────────────
    start = data.start_date or date.today()

    if data.frequency == FrequencyType.weekly and data.day_of_week is not None:
        # Find next occurrence of target weekday from start date
        # day_of_week: 0=Monday ... 6=Sunday
        # Python weekday(): 0=Monday ... 6=Sunday — same convention
        days_ahead = data.day_of_week - start.weekday()
        if days_ahead < 0:
            # Target day already passed this week → go to next week
            days_ahead += 7
        elif days_ahead == 0:
            # Today is the target day → start today
            days_ahead = 0
        next_due = start + timedelta(days=days_ahead)

    elif data.frequency == FrequencyType.monthly and data.day_of_month is not None:
        # Set to day_of_month in current month
        # If that day has passed → use next month
        today = date.today()
        try:
            candidate = date(today.year, today.month, data.day_of_month)
        except ValueError:
            # day_of_month > days in current month (e.g. 31 in February)
            # Use last day of month instead
            last_day = calendar.monthrange(today.year, today.month)[1]
            candidate = date(today.year, today.month, last_day)

        if candidate < today:
            # Already passed this month → next month
            next_month = today.month + 1
            next_year  = today.year
            if next_month > 12:
                next_month = 1
                next_year += 1
            try:
                candidate = date(next_year, next_month, data.day_of_month)
            except ValueError:
                last_day  = calendar.monthrange(next_year, next_month)[1]
                candidate = date(next_year, next_month, last_day)

        next_due = candidate
    else:
        # No day targeting → start from start_date
        next_due = start

    payload = {
        "user_id":       user_id,
        "type":          data.type.value,
        "amount":        str(data.amount),
        "currency_id":   str(data.currency_id),
        "description":   data.description,
        "frequency":     data.frequency.value,
        "start_date":    start.isoformat(),
        "next_due_date": next_due.isoformat(),
        "is_active":     True,
    }

    if data.category_id:
        payload["category_id"]  = str(data.category_id)
    if data.end_date:
        payload["end_date"]     = data.end_date.isoformat()
    if data.day_of_week is not None:
        payload["day_of_week"]  = data.day_of_week
    if data.day_of_month is not None:
        payload["day_of_month"] = data.day_of_month

    result = (
        supabase_admin
        .table("recurring_rules")
        .insert(payload)
        .execute()
    )

    if not result.data:
        raise RuntimeError("Failed to create recurring rule")

    return result.data[0]


async def list_recurring_rules(
    user_id: str,
    active_only: bool = False,
) -> list[dict]:
    """
    Returns all recurring rules for a user.
    active_only=True returns only rules that are currently active.
    """
    query = (
        supabase_admin
        .table("recurring_rules")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=False)
    )

    if active_only:
        query = query.eq("is_active", True)

    result = query.execute()
    return result.data or []


async def get_recurring_rule_by_id(
    rule_id: UUID,
    user_id: str,
) -> Optional[dict]:
    """
    Fetches a single recurring rule scoped to the authenticated user.
    Returns None if not found or belongs to another user.
    """
    result = (
        supabase_admin
        .table("recurring_rules")
        .select("*")
        .eq("id", str(rule_id))
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    return result.data if result.data else None


async def update_recurring_rule(
    rule_id: UUID,
    user_id: str,
    data: RecurringRuleUpdate,
) -> Optional[dict]:
    """
    Partially updates a recurring rule.
    type and frequency cannot be changed — they define rule behavior.
    Deactivating (is_active=False) stops future transaction generation
    without deleting the rule or its history.
    """
    payload: dict = {}

    if data.amount is not None:
        payload["amount"] = str(data.amount)

    if data.currency_id is not None:
        payload["currency_id"] = str(data.currency_id)

    if data.category_id is not None:
        payload["category_id"] = str(data.category_id)

    if data.description is not None:
        payload["description"] = data.description

    if data.end_date is not None:
        payload["end_date"] = data.end_date.isoformat()

    if data.is_active is not None:
        payload["is_active"] = data.is_active

    if not payload:
        return await get_recurring_rule_by_id(rule_id, user_id)

    result = (
        supabase_admin
        .table("recurring_rules")
        .update(payload)
        .eq("id", str(rule_id))
        .eq("user_id", user_id)
        .execute()
    )

    return result.data[0] if result.data else None


async def delete_recurring_rule(
    rule_id: UUID,
    user_id: str,
) -> bool:
    """
    Deletes a recurring rule.
    Previously generated transactions are NOT deleted —
    recurring_rule_id on those rows becomes NULL (ON DELETE SET NULL).
    is_recurring=True is preserved on those rows so history shows
    they were auto-generated.
    """
    result = (
        supabase_admin
        .table("recurring_rules")
        .delete()
        .eq("id", str(rule_id))
        .eq("user_id", user_id)
        .execute()
    )

    return len(result.data) > 0


async def process_due_rules() -> dict:
    """
    Core recurring engine — processes all rules due today or overdue.

    Flow per rule:
      1. Fetch all active rules WHERE next_due_date <= TODAY
      2. For each rule:
         a. Check if end_date has passed → deactivate if so
         b. Calculate amount_mxn from current exchange rate
         c. Insert expense or earning row
         d. Advance next_due_date by frequency interval
         e. Update rule in DB
      3. Return processing summary

    This function is called by:
      - POST /api/v1/recurring/process (manual trigger for testing)
      - Background scheduler daily at midnight (Phase 7)

    Uses supabase_admin because there is no user session context —
    this runs as a background job across all users.
    """
    today = date.today()

    # Fetch all rules due today or overdue across ALL users
    result = (
        supabase_admin
        .table("recurring_rules")
        .select("*")
        .eq("is_active", True)
        .lte("next_due_date", today.isoformat())
        .execute()
    )

    rules = result.data or []

    processed    = 0
    created      = 0
    errors       = 0
    transactions = []

    for rule in rules:
        try:
            rule_id       = rule["id"]
            user_id       = rule["user_id"]
            next_due      = date.fromisoformat(rule["next_due_date"])
            frequency     = rule["frequency"]
            end_date_str  = rule.get("end_date")

            # ── Check if rule has expired ─────────────────────────────────
            if end_date_str:
                end_date = date.fromisoformat(end_date_str)
                if today > end_date:
                    # Deactivate expired rule — no more transactions
                    supabase_admin.table("recurring_rules").update(
                        {"is_active": False}
                    ).eq("id", rule_id).execute()
                    logger.info(f"Deactivated expired rule {rule_id}")
                    processed += 1
                    continue

            # ── Calculate amount in MXN ───────────────────────────────────
            currency_result = (
                supabase_admin
                .table("currencies")
                .select("exchange_rate")
                .eq("id", rule["currency_id"])
                .single()
                .execute()
            )

            rate       = Decimal(str(currency_result.data["exchange_rate"]))
            amount     = Decimal(str(rule["amount"]))
            amount_mxn = round(amount * rate, 2)

            # ── Build transaction payload ─────────────────────────────────
            tx_payload = {
                "user_id":           user_id,
                "amount":            str(amount),
                "currency_id":       rule["currency_id"],
                "amount_mxn":        str(amount_mxn),
                "date":              next_due.isoformat(),
                "notes":             rule.get("description"),
                "is_recurring":      True,
                "recurring_rule_id": rule_id,
            }

            if rule.get("category_id"):
                tx_payload["category_id"] = rule["category_id"]

            # ── Insert into correct table based on rule type ──────────────
            table = "expenses" if rule["type"] == "expense" else "earnings"

            tx_result = (
                supabase_admin
                .table(table)
                .insert(tx_payload)
                .execute()
            )

            if tx_result.data:
                transactions.append({
                    "rule_id": rule_id,
                    "type":    rule["type"],
                    "table":   table,
                    "amount":  str(amount),
                    "date":    next_due.isoformat(),
                })
                created += 1

            # ── Advance next_due_date ─────────────────────────────────────
            new_next_due = calculate_next_due_date(
                next_due,
                frequency,
                day_of_week  = rule.get("day_of_week"),
                day_of_month = rule.get("day_of_month"),
            )

            supabase_admin.table("recurring_rules").update(
                {"next_due_date": new_next_due.isoformat()}
            ).eq("id", rule_id).execute()

            logger.info(
                f"Processed rule {rule_id} for user {user_id} "
                f"→ created {table} → next due {new_next_due}"
            )
            processed += 1

        except Exception as e:
            # Log error but continue processing other rules
            # One failed rule should not block all others
            logger.error(f"Failed to process rule {rule.get('id')}: {e}")
            errors += 1

    return {
        "processed":    processed,
        "created":      created,
        "errors":       errors,
        "transactions": transactions,
    }