from decimal import Decimal
from typing import Optional
from uuid import UUID
from datetime import date, timedelta
import calendar
import logging

from app.database import db, fetch_one
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
        db()
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
        db()
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
    result = fetch_one(
        db()
        .table("recurring_rules")
        .select("*")
        .eq("id", str(rule_id))
        .eq("user_id", user_id)
    )

    return result if result else None


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
        db()
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
        db()
        .table("recurring_rules")
        .delete()
        .eq("id", str(rule_id))
        .eq("user_id", user_id)
        .execute()
    )

    return len(result.data) > 0



# Upper bound on how many occurrences one rule may generate in a single
# invocation. A weekly rule untouched for two years is ~104; anything past
# this is a sign the cursor is not advancing, and looping forever on a
# background job is worse than stopping and logging.
MAX_CATCHUP_PER_RULE = 500


async def process_due_rules(user_id: Optional[str] = None) -> dict:
    """
    Core recurring engine — writes the transactions that are due.

    Pass user_id to process a single user's rules. Omitted, it runs across
    every user, which is what the nightly scheduler wants.

    Per rule, per occurrence:
      1. Claim the occurrence by advancing next_due_date, conditional on it
         still holding the value this run read.
      2. Only if that claim succeeded, write the transaction.
      3. Repeat until next_due_date is in the future.

    Why claim before writing
    ------------------------
    The order used to be the other way round: insert the transaction, then
    advance the cursor. Anything failing between the two — a dropped
    connection, a restart, a Supabase 5xx — left the transaction committed
    and the cursor unmoved, so the next run wrote it again. The broad
    except below made that silent.

    Claiming first inverts the failure: a crash after the claim loses one
    occurrence instead of duplicating one. For money that is the right way
    round. A missing transaction is visible to the user and can be added
    by hand; a duplicate quietly overstates spending and corrupts every
    total derived from it. The unique index from migration 012 is the
    backstop underneath both.

    The conditional update is also what makes concurrency safe. Two runners
    — the scheduler and a manual POST /process — both read next_due_date as
    the same value, but only one update can match it. The loser gets zero
    rows back and stops, rather than writing a second copy.

    Why the inner loop
    ------------------
    calculate_next_due_date advances exactly one interval. A rule five
    weeks overdue used to emit one transaction per invocation and leave
    next_due_date still in the past, so calling the endpoint five times in
    one day produced five transactions on five different dates. Draining
    the backlog here means a second call the same day finds nothing to do.
    """
    today = date.today()

    query = (
        db()
        .table("recurring_rules")
        .select("*")
        .eq("is_active", True)
        .lte("next_due_date", today.isoformat())
    )

    # Scope to one user when asked. The scheduler passes nothing.
    if user_id is not None:
        query = query.eq("user_id", user_id)

    rules = (query.execute().data) or []

    processed    = 0
    created      = 0
    errors       = 0
    transactions = []

    for rule in rules:
        try:
            rule_id      = rule["id"]
            owner_id     = rule["user_id"]
            frequency    = rule["frequency"]
            next_due     = date.fromisoformat(rule["next_due_date"])
            end_date_str = rule.get("end_date")
            end_date     = date.fromisoformat(end_date_str) if end_date_str else None

            # ── Rule has run its course ───────────────────────────────────
            if end_date and today > end_date:
                db().table("recurring_rules").update(
                    {"is_active": False}
                ).eq("id", rule_id).execute()
                logger.info(f"Deactivated expired rule {rule_id}")
                processed += 1
                continue

            # ── Exchange rate, read once per rule not once per occurrence ─
            currency_result = (
                db()
                .table("currencies")
                .select("exchange_rate")
                .eq("id", rule["currency_id"])
                .single()
                .execute()
            )

            rate       = Decimal(str(currency_result.data["exchange_rate"]))
            amount     = Decimal(str(rule["amount"]))
            amount_mxn = round(amount * rate, 2)
            table      = "expenses" if rule["type"] == "expense" else "earnings"

            # ── Drain this rule's backlog ─────────────────────────────────
            occurrences = 0

            while next_due <= today:
                if end_date and next_due > end_date:
                    db().table("recurring_rules").update(
                        {"is_active": False}
                    ).eq("id", rule_id).execute()
                    logger.info(f"Deactivated rule {rule_id} past its end date")
                    break

                occurrences += 1
                if occurrences > MAX_CATCHUP_PER_RULE:
                    logger.error(
                        f"Rule {rule_id} exceeded {MAX_CATCHUP_PER_RULE} "
                        f"catch-up occurrences; stopping to avoid a runaway loop"
                    )
                    errors += 1
                    break

                new_next_due = calculate_next_due_date(
                    next_due,
                    frequency,
                    day_of_week  = rule.get("day_of_week"),
                    day_of_month = rule.get("day_of_month"),
                )

                # Claim. The second .eq is the whole guard: it only matches
                # while next_due_date still holds the value we read.
                claim = (
                    db()
                    .table("recurring_rules")
                    .update({"next_due_date": new_next_due.isoformat()})
                    .eq("id", rule_id)
                    .eq("next_due_date", next_due.isoformat())
                    .execute()
                )

                if not claim.data:
                    # Another runner took this occurrence. Not an error.
                    logger.info(
                        f"Rule {rule_id} occurrence {next_due} already claimed "
                        f"by another run; skipping"
                    )
                    break

                tx_payload = {
                    "user_id":           owner_id,
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

                tx_result = (
                    db()
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

                logger.info(
                    f"Processed rule {rule_id} for user {owner_id} "
                    f"→ created {table} dated {next_due} → next due {new_next_due}"
                )

                next_due = new_next_due

            processed += 1

        except Exception as e:
            # One bad rule must not stop the rest. The cursor for this rule
            # has already moved for any occurrence that was claimed, so a
            # retry resumes rather than repeats.
            logger.error(f"Failed to process rule {rule.get('id')}: {e}")
            errors += 1

    return {
        "processed":    processed,
        "created":      created,
        "errors":       errors,
        "transactions": transactions,
    }


async def delete_all_rules(user_id: str) -> int:
    """
    Deletes every recurring rule belonging to this user and returns the count.

    Part of the full data reset on the Settings screen.

    Transactions already generated are kept. recurring_rule_id on those
    rows is set null by the foreign key, so spending history survives the
    rule that produced it.
    """
    result = (
        db()
        .table("recurring_rules")
        .delete()
        .eq("user_id", user_id)
        .execute()
    )

    deleted = len(result.data or [])
    logger.info(f"Deleted {deleted} rules for user {user_id}")
    return deleted
