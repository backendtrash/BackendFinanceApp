from decimal  import Decimal, ROUND_CEILING
from typing   import Optional
from uuid     import UUID
from datetime import date, timedelta
import calendar
import logging

from app.database import supabase_admin
from app.sinking_funds.schemas import (
    SinkingFundCreate,
    SinkingFundUpdate,
    ContributeRequest,
    PayoutRequest,
    ReleaseRequest,
)

logger = logging.getLogger(__name__)

ZERO = Decimal("0")

# 52 / 12. Display only — used for the "≈ $X/mo" equivalent.
# Fund scheduling counts ACTUAL calendar periods instead, because converting
# a monthly target to a weekly set-aside through this constant accumulates
# drift and lands the user short on the due date.
WEEKS_PER_MONTH = Decimal("4.333333")

# Same palette the goals module cycles, so a fund's auto-created category
# looks at home beside a goal's.
FUND_COLORS = [
    "#22C55E", "#6366F1", "#F59E0B", "#EC4899",
    "#14B8A6", "#F97316", "#8B5CF6", "#06B6D4",
]

_MONTHS_PER_INTERVAL = {
    "monthly":    1,
    "quarterly":  3,
    "semiannual": 6,
    "annual":     12,
}


# ── Small helpers ─────────────────────────────────────────────────────────
def ceil_cents(v: Decimal) -> Decimal:
    """Round UP so rounding never leaves the user short.
    The final period absorbs whatever slack accumulates."""
    return v.quantize(Decimal("0.01"), rounding=ROUND_CEILING)


def _d(v) -> Decimal:
    """Supabase returns numerics as strings; None means zero."""
    return Decimal(str(v)) if v is not None else ZERO


def _parse_date(v) -> Optional[date]:
    if not v:
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def start_of_week(d: date, week_start_day: int) -> date:
    """
    week_start_day uses the preferences convention: 0=Sunday, 1=Monday.
    Note this is the OPPOSITE convention to contribution_day_of_week
    (0=Monday), which matches projected_costs.day_of_week. The two adjacent
    0-6 fields genuinely mean different things — see the app-wide note in
    weekBoundaries.ts.

    Mirrors the frontend's (d.getDay() - weekStartDay + 7) % 7.
    """
    js_dow = (d.weekday() + 1) % 7          # py Mon=0..Sun=6 -> JS Sun=0..Sat=6
    return d - timedelta(days=(js_dow - week_start_day) % 7)


def add_months(d: date, n: int) -> date:
    """Adds n months, clamping the day to the target month's length.
    Feb 29 + 12 months -> Feb 28."""
    total = d.month - 1 + n
    year  = d.year + total // 12
    month = total % 12 + 1
    day   = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def end_of_month(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def periods_between(frm: date, to: date, cadence: str, wsd: int) -> int:
    """
    Inclusive count of contribution slots from the period containing `frm`
    through the period containing `to`. Can return <= 0 when `to` is in the
    past — callers clamp with max(..., 1).
    """
    if cadence == "weekly":
        delta = start_of_week(to, wsd) - start_of_week(frm, wsd)
        return (delta.days // 7) + 1
    return (to.year - frm.year) * 12 + (to.month - frm.month) + 1


def add_periods(frm: date, n: int, cadence: str, wsd: int) -> date:
    """The last day of the period n slots after the one containing `frm`."""
    if cadence == "weekly":
        return start_of_week(frm, wsd) + timedelta(days=7 * n + 6)
    return end_of_month(add_months(frm, n))


def add_interval(d: date, interval: str) -> date:
    return add_months(d, _MONTHS_PER_INTERVAL.get(interval, 0))


async def _get_exchange_rate(currency_id: Optional[str]) -> Decimal:
    """Fetches the exchange rate for a currency. Returns 1 for MXN/None."""
    if not currency_id:
        return Decimal("1")
    result = (
        supabase_admin
        .table("currencies")
        .select("exchange_rate")
        .eq("id", str(currency_id))
        .single()
        .execute()
    )
    if result.data:
        return Decimal(str(result.data["exchange_rate"]))
    return Decimal("1")


async def _get_week_start_day(user_id: str) -> int:
    """Reads the user's week start preference, defaulting to Monday."""
    try:
        result = (
            supabase_admin
            .table("user_preferences")
            .select("week_start_day")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if result.data and result.data.get("week_start_day") is not None:
            return int(result.data["week_start_day"])
    except Exception:
        # A missing preferences row is normal for a brand new user.
        pass
    return 1


async def _get_mxn_currency_id() -> Optional[str]:
    result = (
        supabase_admin
        .table("currencies")
        .select("id")
        .eq("code", "MXN")
        .limit(1)
        .execute()
    )
    return result.data[0]["id"] if result.data else None


# ── Enrichment — all derived numbers live here ────────────────────────────
def enrich_fund(
    fund:          dict,
    contributions: list[dict],
    payouts:       list[dict],
    rate_map:      dict,
    week_start_day: int,
    today:         Optional[date] = None,
) -> dict:
    """
    Computes every derived field from (balance, target, due_date, today).

    Nothing is materialised: there is no schedule table, so editing the
    target, the due date or the cadence mid-flight needs no migration —
    the numbers simply recompute on the next read.
    """
    today   = today or date.today()
    cadence = fund.get("cadence") or "monthly"
    mode    = fund.get("mode") or "target_by_date"
    cycle_start = _parse_date(fund.get("cycle_started_on")) or today
    due_date    = _parse_date(fund.get("due_date"))

    # ── Ledger sums, scoped to the current cycle ──────────────────────────
    # Scoping by cycle_started_on is what makes renewal free: no rows move,
    # none are deleted, and last year's contributions stop counting.
    contributed = sum(
        (_d(e.get("amount_mxn")) for e in contributions
         if (_parse_date(e.get("date")) or today) >= cycle_start),
        ZERO,
    )
    paid_out = sum(
        (_d(p.get("amount_mxn")) for p in payouts
         if (_parse_date(p.get("paid_on")) or today) >= cycle_start),
        ZERO,
    )

    opening   = _d(fund.get("opening_balance"))
    raw_balance = opening + contributed - paid_out

    # A contribution edited or deleted after a payout can drive this
    # negative. Clamp for display and flag it, but never block the edit —
    # users have to be able to fix mistakes.
    has_ledger_warning = raw_balance < ZERO
    balance = max(raw_balance, ZERO)

    # ── Target in MXN, at TODAY's rate ────────────────────────────────────
    # Contributions are frozen at their own rate. For a genuinely foreign
    # bill the gap is correct — if MXN weakens you really do need more
    # pesos — so it surfaces as schedule variance rather than being hidden.
    raw_target = fund.get("target_amount")
    target_mxn = None
    if raw_target is not None:
        rate = rate_map.get(fund.get("currency_id"), Decimal("1"))
        target_mxn = round(_d(raw_target) * rate, 2)

    remaining = max(target_mxn - balance, ZERO) if target_mxn is not None else ZERO

    pct_complete = (
        round(balance / target_mxn * 100, 2)
        if target_mxn and target_mxn > 0 else ZERO
    )

    # ── Has this cycle already been paid out? ─────────────────────────────
    cycle_payouts = [
        p for p in payouts
        if (_parse_date(p.get("paid_on")) or today) >= cycle_start
        and p.get("kind") == "payout"
    ]
    paid_this_cycle = len(cycle_payouts) > 0
    all_payout_dates = [_parse_date(p.get("paid_on")) for p in payouts]
    all_payout_dates = [d for d in all_payout_dates if d]
    last_payout_on   = max(all_payout_dates) if all_payout_dates else None

    # ── Periods remaining ─────────────────────────────────────────────────
    periods_remaining = 0
    if due_date:
        # max(..., 1) also guards against a negative count from a past due
        # date producing an absurd or negative per-period amount.
        periods_remaining = max(periods_between(today, due_date, cadence, week_start_day), 0)

    # ── The per-period set-aside ──────────────────────────────────────────
    contribution_amount = fund.get("contribution_amount")
    projected_completion = None

    if mode == "target_by_date":
        if remaining <= ZERO or target_mxn is None:
            set_aside = ZERO
        else:
            n = max(periods_between(today, due_date, cadence, week_start_day), 1) \
                if due_date else 1
            set_aside = min(ceil_cents(remaining / n), remaining)
        projected_completion = due_date

        # Steady-state number, ignoring catch-up. Week View uses this for
        # FUTURE weeks, where a figure computed against today's balance
        # would be meaningless.
        if due_date and target_mxn is not None:
            total_periods = max(
                periods_between(cycle_start, due_date, cadence, week_start_day), 1
            )
            base_per_period = ceil_cents(max(target_mxn - opening, ZERO) / total_periods)
        else:
            base_per_period = set_aside

    else:  # fixed_per_period
        base = _d(contribution_amount)
        if target_mxn is None:
            # Open-ended fund — save indefinitely, no completion date.
            set_aside = base
        else:
            set_aside = min(base, remaining)
            if remaining > ZERO and base > ZERO:
                needed = int(-(-remaining // base))   # ceil division
                projected_completion = add_periods(
                    today, needed - 1, cadence, week_start_day
                )
        base_per_period = base

    monthly_equivalent = (
        round(set_aside * WEEKS_PER_MONTH, 2) if cadence == "weekly" else set_aside
    )

    # ── Ahead / behind the funding line ───────────────────────────────────
    expected_balance = None
    variance         = None
    if due_date and target_mxn is not None:
        total   = max(periods_between(cycle_start, due_date, cadence, week_start_day), 1)
        left    = max(periods_between(today, due_date, cadence, week_start_day), 0)
        elapsed = total - left
        frac    = min(Decimal("1"), max(ZERO, Decimal(elapsed) / Decimal(total)))
        expected_balance = round(opening + (target_mxn - opening) * frac, 2)
        variance         = round(balance - expected_balance, 2)

    is_overdue = bool(due_date and due_date < today and not paid_this_cycle
                      and remaining > ZERO)

    if paid_this_cycle:
        status = "paid"
    elif target_mxn is not None and remaining <= ZERO:
        status = "funded"
    elif is_overdue:
        status = "overdue"
    elif variance is not None and variance < ZERO:
        status = "behind"
    elif variance is not None and variance > ZERO:
        status = "ahead"
    else:
        status = "on_track"

    fund["target_amount_mxn"]     = target_mxn
    fund["contributed_mxn"]       = round(contributed, 2)
    fund["paid_out_mxn"]          = round(paid_out, 2)
    fund["balance_mxn"]           = round(balance, 2)
    fund["remaining_mxn"]         = round(remaining, 2)
    fund["pct_complete"]          = pct_complete
    fund["periods_remaining"]     = periods_remaining
    fund["set_aside_this_period"] = round(set_aside, 2)
    fund["base_per_period"]       = round(base_per_period, 2)
    fund["monthly_equivalent"]    = monthly_equivalent
    fund["expected_balance_mxn"]  = expected_balance
    fund["schedule_variance_mxn"] = variance
    fund["status"]                = status
    fund["is_overdue"]            = is_overdue
    fund["paid_this_cycle"]       = paid_this_cycle
    fund["last_payout_on"]        = last_payout_on.isoformat() if last_payout_on else None
    fund["projected_completion"]  = (
        projected_completion.isoformat() if projected_completion else None
    )
    fund["has_ledger_warning"]    = has_ledger_warning
    return fund


# ── Reads ─────────────────────────────────────────────────────────────────
async def list_sinking_funds(
    user_id:          str,
    include_inactive: bool = False,
) -> list[dict]:
    """
    Four queries total regardless of fund count — funds, currencies,
    linked expenses, payouts — then enrichment happens in Python.
    Follows the same O(1) pattern as list_goals rather than calling a
    per-fund enrich in a loop.
    """
    query = (
        supabase_admin
        .table("sinking_funds")
        .select("*")
        .eq("user_id", user_id)
    )
    if not include_inactive:
        query = query.eq("is_active", True)

    result = query.order("created_at", desc=False).execute()
    funds  = result.data or []
    if not funds:
        return []

    fund_ids = [f["id"] for f in funds]

    currencies_result = (
        supabase_admin
        .table("currencies")
        .select("id, exchange_rate")
        .execute()
    )
    rate_map = {
        c["id"]: Decimal(str(c["exchange_rate"]))
        for c in (currencies_result.data or [])
    }

    expenses_result = (
        supabase_admin
        .table("expenses")
        .select("id, sinking_fund_id, amount_mxn, date, notes")
        .eq("user_id", user_id)
        .in_("sinking_fund_id", fund_ids)
        .execute()
    )
    payouts_result = (
        supabase_admin
        .table("sinking_fund_payouts")
        .select("*")
        .eq("user_id", user_id)
        .in_("sinking_fund_id", fund_ids)
        .execute()
    )

    by_fund_expenses: dict = {}
    for e in (expenses_result.data or []):
        by_fund_expenses.setdefault(e["sinking_fund_id"], []).append(e)

    by_fund_payouts: dict = {}
    for p in (payouts_result.data or []):
        by_fund_payouts.setdefault(p["sinking_fund_id"], []).append(p)

    week_start_day = await _get_week_start_day(user_id)
    today          = date.today()

    return [
        enrich_fund(
            f,
            by_fund_expenses.get(f["id"], []),
            by_fund_payouts.get(f["id"], []),
            rate_map,
            week_start_day,
            today,
        )
        for f in funds
    ]


async def get_fund_by_id(fund_id: UUID, user_id: str) -> Optional[dict]:
    """Fetches a single fund, enriched, scoped to the authenticated user."""
    result = (
        supabase_admin
        .table("sinking_funds")
        .select("*")
        .eq("id", str(fund_id))
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        return None

    fund = result.data[0]

    expenses_result = (
        supabase_admin
        .table("expenses")
        .select("id, sinking_fund_id, amount_mxn, date, notes")
        .eq("user_id", user_id)
        .eq("sinking_fund_id", str(fund_id))
        .execute()
    )
    payouts_result = (
        supabase_admin
        .table("sinking_fund_payouts")
        .select("*")
        .eq("user_id", user_id)
        .eq("sinking_fund_id", str(fund_id))
        .execute()
    )

    rate_map = {}
    if fund.get("currency_id"):
        rate_map[fund["currency_id"]] = await _get_exchange_rate(fund["currency_id"])

    week_start_day = await _get_week_start_day(user_id)

    return enrich_fund(
        fund,
        expenses_result.data or [],
        payouts_result.data or [],
        rate_map,
        week_start_day,
    )


async def get_activity(
    fund_id: UUID,
    user_id: str,
    limit:   int = 50,
    offset:  int = 0,
) -> list[dict]:
    """Merged contribution + payout ledger, newest first."""
    expenses_result = (
        supabase_admin
        .table("expenses")
        .select("id, amount_mxn, date, notes")
        .eq("user_id", user_id)
        .eq("sinking_fund_id", str(fund_id))
        .execute()
    )
    payouts_result = (
        supabase_admin
        .table("sinking_fund_payouts")
        .select("id, amount_mxn, paid_on, kind, notes, top_up_expense_id")
        .eq("user_id", user_id)
        .eq("sinking_fund_id", str(fund_id))
        .execute()
    )

    top_up_ids = {
        p["top_up_expense_id"]
        for p in (payouts_result.data or [])
        if p.get("top_up_expense_id")
    }

    entries = [
        {
            "id":         e["id"],
            "kind":       "top_up" if e["id"] in top_up_ids else "contribution",
            "amount_mxn": _d(e.get("amount_mxn")),
            "date":       str(e.get("date"))[:10],
            "notes":      e.get("notes"),
        }
        for e in (expenses_result.data or [])
    ] + [
        {
            "id":         p["id"],
            "kind":       p.get("kind") or "payout",
            "amount_mxn": _d(p.get("amount_mxn")),
            "date":       str(p.get("paid_on"))[:10],
            "notes":      p.get("notes"),
        }
        for p in (payouts_result.data or [])
    ]

    entries.sort(key=lambda x: x["date"], reverse=True)
    return entries[offset:offset + limit]


# ── Writes ────────────────────────────────────────────────────────────────
async def _create_fund_category(user_id: str, fund_name: str) -> str:
    """
    Creates the "<name> Fund" expense category and returns its id.

    Raises RuntimeError on failure instead of swallowing it. This used to be
    inline in create_sinking_fund with a silent `if cat_result.data:` and no
    else — a fund could end up with category_id = NULL, every set-aside for
    it landed uncategorized, and nothing ever reported why. Icon uses
    "trending-down", the value already proven to work on the equivalent
    goals path (app/goals/service.py) — "piggy-bank" was never confirmed
    against whatever the categories table actually accepts, and is the
    prime suspect for the original silent failure.
    """
    existing = (
        supabase_admin
        .table("sinking_funds")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    color = FUND_COLORS[(existing.count or 0) % len(FUND_COLORS)]

    cat_result = (
        supabase_admin
        .table("categories")
        .insert({
            "user_id": user_id,
            "name":    f"{fund_name} Fund",
            "color":   color,
            "icon":    "trending-down",
            "type":    "expense",   # set-asides are expenses
        })
        .execute()
    )
    if not cat_result.data:
        raise RuntimeError(
            f"Failed to create the '{fund_name} Fund' category — "
            "the fund was not created. Check server logs for the "
            "underlying Supabase error."
        )
    return cat_result.data[0]["id"]


async def _ensure_fund_category(user_id: str, fund: dict) -> Optional[str]:
    """
    Returns the fund's category id, creating and persisting one if it is
    missing. This is what makes an already-broken fund (created before this
    fix, or from a still-failing insert) self-heal on its next set-aside
    instead of silently writing another uncategorized expense.
    """
    category_id = fund.get("category_id")
    if category_id:
        return category_id

    category_id = await _create_fund_category(user_id, fund["name"])

    supabase_admin.table("sinking_funds").update(
        {"category_id": category_id}
    ).eq("id", fund["id"]).eq("user_id", user_id).execute()

    fund["category_id"] = category_id
    return category_id


async def create_sinking_fund(user_id: str, data: SinkingFundCreate) -> dict:
    """
    Creates a fund and, unless one is supplied, an expense category named
    "<name> Fund" for it.

    The category exists for analytics grouping and the Week View colour dot.
    It is NOT the source of truth for the balance — expenses.sinking_fund_id
    is. Goals compute progress by summing a category, which is safe there
    because goals have no payouts and no cycles; for funds it would count a
    manually-filed bill as a contribution.
    """
    auto_category_id = None

    if not data.category_id:
        auto_category_id = await _create_fund_category(user_id, data.name)

    payload = {
        "user_id":              user_id,
        "name":                 data.name,
        "mode":                 data.mode.value,
        "cadence":              data.cadence.value,
        "repeat_interval":      data.repeat_interval.value,
        "renewal_increase_pct": str(data.renewal_increase_pct),
        "auto_renew":           data.auto_renew,
        "is_active":            True,
        "cycle_started_on":     date.today().isoformat(),
    }

    if data.target_amount is not None:
        payload["target_amount"] = str(data.target_amount)
    if data.contribution_amount is not None:
        payload["contribution_amount"] = str(data.contribution_amount)
    if data.currency_id:
        payload["currency_id"] = str(data.currency_id)
    if data.due_date:
        payload["due_date"] = data.due_date.isoformat()
    if data.contribution_day_of_week is not None:
        payload["contribution_day_of_week"] = data.contribution_day_of_week
    if data.contribution_day_of_month is not None:
        payload["contribution_day_of_month"] = data.contribution_day_of_month
    if data.notes:
        payload["notes"] = data.notes
    if data.projected_cost_id:
        payload["projected_cost_id"] = str(data.projected_cost_id)

    # Money already saved. Stored directly, never as an expense, so it does
    # not distort net balance — the same carve-out goals makes for
    # initial_amount. Named opening_balance because after the first renewal
    # it holds carried-over surplus and "initial" would be a lie.
    if data.start_amount and data.start_amount > 0:
        payload["opening_balance"] = str(data.start_amount)

    final_category_id = auto_category_id or (
        str(data.category_id) if data.category_id else None
    )
    if final_category_id:
        payload["category_id"] = final_category_id

    result = (
        supabase_admin
        .table("sinking_funds")
        .insert(payload)
        .execute()
    )

    if not result.data:
        # Roll back the auto-created category so a failed insert does not
        # leave an orphan behind.
        if auto_category_id:
            supabase_admin.table("categories").delete().eq(
                "id", auto_category_id
            ).execute()
        raise RuntimeError("Failed to create sinking fund")

    return await get_fund_by_id(UUID(result.data[0]["id"]), user_id)


async def update_sinking_fund(
    fund_id: UUID,
    user_id: str,
    data:    SinkingFundUpdate,
) -> Optional[dict]:
    """
    Partial update. Every derived number is recomputed on read, so there is
    no schedule to migrate when the target, date or cadence changes.
    """
    payload: dict = {}

    if data.name                is not None: payload["name"]                = data.name.strip()
    if data.mode                is not None: payload["mode"]                = data.mode.value
    if data.cadence             is not None: payload["cadence"]             = data.cadence.value
    if data.repeat_interval     is not None: payload["repeat_interval"]     = data.repeat_interval.value
    if data.target_amount       is not None: payload["target_amount"]       = str(data.target_amount)
    if data.contribution_amount is not None: payload["contribution_amount"] = str(data.contribution_amount)
    if data.currency_id         is not None: payload["currency_id"]         = str(data.currency_id)
    if data.due_date            is not None: payload["due_date"]            = data.due_date.isoformat()
    if data.renewal_increase_pct is not None: payload["renewal_increase_pct"] = str(data.renewal_increase_pct)
    if data.auto_renew          is not None: payload["auto_renew"]          = data.auto_renew
    if data.notes               is not None: payload["notes"]               = data.notes
    if data.is_active           is not None: payload["is_active"]           = data.is_active
    if data.projected_cost_id   is not None: payload["projected_cost_id"]   = str(data.projected_cost_id)
    if data.category_id         is not None: payload["category_id"]        = str(data.category_id)
    if data.contribution_day_of_week  is not None:
        payload["contribution_day_of_week"]  = data.contribution_day_of_week
    if data.contribution_day_of_month is not None:
        payload["contribution_day_of_month"] = data.contribution_day_of_month

    if not payload:
        return await get_fund_by_id(fund_id, user_id)

    result = (
        supabase_admin
        .table("sinking_funds")
        .update(payload)
        .eq("id", str(fund_id))
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        return None

    return await get_fund_by_id(fund_id, user_id)


async def contribute(
    fund_id: UUID,
    user_id: str,
    data:    ContributeRequest,
) -> Optional[dict]:
    """
    Sets money aside: creates a REAL expense carrying sinking_fund_id.
    Net balance drops now, which is the whole point of the model — by the
    time the bill arrives the money has already left.
    """
    fund = await get_fund_by_id(fund_id, user_id)
    if not fund:
        return None

    amount = data.amount
    if amount is None:
        amount = Decimal(str(fund.get("set_aside_this_period") or 0))
    if amount <= ZERO:
        raise ValueError("Nothing left to set aside for this fund")

    when = data.date or date.today()

    # A contribution dated before the cycle start is excluded from the
    # balance sum, so it would silently do nothing. Refuse it explicitly.
    cycle_start = _parse_date(fund.get("cycle_started_on"))
    if cycle_start and when < cycle_start:
        raise ValueError(
            f"Date is before this fund's current cycle started "
            f"({cycle_start.isoformat()})"
        )

    currency_id = str(data.currency_id) if data.currency_id else await _get_mxn_currency_id()
    if not currency_id:
        raise RuntimeError("No currency available")

    rate       = await _get_exchange_rate(currency_id)
    amount_mxn = round(amount * rate, 2)

    # Self-heals a fund whose category is missing (a stale fund from before
    # this fix, or a still-failing insert) instead of silently writing
    # another uncategorized expense.
    category_id = await _ensure_fund_category(user_id, fund)

    payload = {
        "user_id":         user_id,
        "amount":          str(amount),
        "currency_id":     currency_id,
        "amount_mxn":      str(amount_mxn),
        "date":            when.isoformat(),
        "notes":           data.notes or f"Set aside · {fund['name']}",
        "is_recurring":    False,
        "sinking_fund_id": str(fund_id),
        "category_id":     category_id,
    }

    result = supabase_admin.table("expenses").insert(payload).execute()
    if not result.data:
        raise RuntimeError("Failed to create contribution")

    return {
        "fund":    await get_fund_by_id(fund_id, user_id),
        "expense": result.data[0],
    }


async def payout(
    fund_id: UUID,
    user_id: str,
    data:    PayoutRequest,
) -> Optional[dict]:
    """
    Records the bill being paid out of the fund.

    Creates NO expense, so net balance does not move — correct, because the
    money already left as contributions. If the fund is short, a top-up
    CONTRIBUTION expense covers the shortfall first, so exactly the amount
    that really came out of pocket hits net balance, with no special case
    anywhere else.
    """
    fund = await get_fund_by_id(fund_id, user_id)
    if not fund:
        return None

    amount = data.amount
    if amount is None:
        amount = Decimal(str(fund.get("target_amount_mxn") or fund.get("balance_mxn") or 0))
    if amount <= ZERO:
        raise ValueError("Payout amount must be greater than zero")

    when        = data.paid_on or date.today()
    currency_id = str(data.currency_id) if data.currency_id else await _get_mxn_currency_id()
    rate        = await _get_exchange_rate(currency_id)
    amount_mxn  = round(amount * rate, 2)

    # Re-read the balance HERE rather than trusting the client, so a
    # double-clicked payout cannot drive the fund negative.
    balance   = Decimal(str(fund.get("balance_mxn") or 0))
    shortfall = amount_mxn - balance

    top_up_expense = None
    if shortfall > ZERO:
        if not data.allow_top_up:
            raise ValueError(
                f"Fund is short by {shortfall}. Enable top-up or lower the amount."
            )
        mxn_id  = await _get_mxn_currency_id()
        top_res = supabase_admin.table("expenses").insert({
            "user_id":         user_id,
            "amount":          str(shortfall),
            "currency_id":     mxn_id,
            "amount_mxn":      str(shortfall),
            "date":            when.isoformat(),
            "notes":           f"Top-up · {fund['name']}",
            "is_recurring":    False,
            "sinking_fund_id": str(fund_id),
            **({"category_id": fund["category_id"]} if fund.get("category_id") else {}),
        }).execute()
        if not top_res.data:
            raise RuntimeError("Failed to create top-up expense")
        top_up_expense = top_res.data[0]

    payout_payload = {
        "user_id":          user_id,
        "sinking_fund_id":  str(fund_id),
        "amount":           str(amount),
        "amount_mxn":       str(amount_mxn),
        "paid_on":          when.isoformat(),
        "kind":             "payout",
        "notes":            data.notes or f"Paid · {fund['name']}",
        "cycle_started_on": fund["cycle_started_on"],
    }
    if currency_id:
        payout_payload["currency_id"] = currency_id
    if fund.get("due_date"):
        payout_payload["cycle_due_date"] = fund["due_date"]
    if top_up_expense:
        payout_payload["top_up_expense_id"] = top_up_expense["id"]
    if fund.get("projected_cost_id"):
        payout_payload["projected_cost_id"] = fund["projected_cost_id"]

    payout_result = (
        supabase_admin
        .table("sinking_fund_payouts")
        .insert(payout_payload)
        .execute()
    )
    if not payout_result.data:
        raise RuntimeError("Failed to record payout")

    # ── Renewal ───────────────────────────────────────────────────────────
    # Done in the same call so the fund is never observed in a
    # paid-but-not-rolled state.
    should_renew = data.renew if data.renew is not None else bool(fund.get("auto_renew"))
    renewed      = False
    if should_renew and (fund.get("repeat_interval") or "none") != "none":
        await _renew(fund_id, user_id, when)
        renewed = True

    return {
        "fund":           await get_fund_by_id(fund_id, user_id),
        "payout":         payout_result.data[0],
        "top_up_expense": top_up_expense,
        "renewed":        renewed,
    }


async def _renew(fund_id: UUID, user_id: str, from_date: date) -> Optional[dict]:
    """
    Rolls the fund into its next cycle.

    Nothing resets and nothing is deleted — because the balance is a ledger
    sum scoped by cycle_started_on, renewal is four field writes. Any
    surplus carries into opening_balance, so next cycle starts ahead and the
    derived per-period amount is automatically lower.
    """
    fund = await get_fund_by_id(fund_id, user_id)
    if not fund:
        return None

    leftover = Decimal(str(fund.get("balance_mxn") or 0))
    due      = _parse_date(fund.get("due_date"))
    interval = fund.get("repeat_interval") or "none"

    payload = {
        "opening_balance":  str(max(leftover, ZERO)),
        "cycle_started_on": (from_date + timedelta(days=1)).isoformat(),
    }
    if due and interval != "none":
        payload["due_date"] = add_interval(due, interval).isoformat()

    pct = Decimal(str(fund.get("renewal_increase_pct") or 0))
    if fund.get("target_amount") is not None and pct != ZERO:
        new_target = round(_d(fund["target_amount"]) * (1 + pct / 100), 2)
        payload["target_amount"] = str(new_target)

    supabase_admin.table("sinking_funds").update(payload).eq(
        "id", str(fund_id)
    ).eq("user_id", user_id).execute()

    return await get_fund_by_id(fund_id, user_id)


async def renew_fund(
    fund_id:  UUID,
    user_id:  str,
    due_date: Optional[date] = None,
) -> Optional[dict]:
    """Manual roll, for when the user wants the next cycle without a payout."""
    result = await _renew(fund_id, user_id, date.today())
    if result and due_date:
        return await update_sinking_fund(
            fund_id, user_id,
            SinkingFundUpdate(due_date=due_date),
        )
    return result


async def release(
    fund_id: UUID,
    user_id: str,
    data:    ReleaseRequest,
) -> Optional[dict]:
    """
    Returns fund money to the spendable pool.

    The money was booked as an expense, so undoing it needs a positive
    entry. expenses.amount has a > 0 validator and deleting past
    contributions would destroy history, so this creates an EARNING.

    That is the offsetting-earning mechanism rejected for payouts — used
    here deliberately, because money genuinely IS re-entering the spendable
    pool, so the income row is honest rather than fictitious. It is rare,
    explicit, and never the default; leftover normally carries over.
    """
    fund = await get_fund_by_id(fund_id, user_id)
    if not fund:
        return None

    balance = Decimal(str(fund.get("balance_mxn") or 0))
    amount  = data.amount if data.amount is not None else balance
    if amount <= ZERO:
        raise ValueError("Nothing to release")
    if amount > balance:
        raise ValueError("Cannot release more than the fund holds")

    when   = data.date or date.today()
    mxn_id = await _get_mxn_currency_id()

    category_id = await _get_or_create_release_category(user_id)

    earning_result = supabase_admin.table("earnings").insert({
        "user_id":      user_id,
        "amount":       str(amount),
        "currency_id":  mxn_id,
        "amount_mxn":   str(amount),
        "date":         when.isoformat(),
        "notes":        data.notes or f"Released · {fund['name']}",
        "is_recurring": False,
        **({"category_id": category_id} if category_id else {}),
    }).execute()
    if not earning_result.data:
        raise RuntimeError("Failed to create release earning")

    supabase_admin.table("sinking_fund_payouts").insert({
        "user_id":            user_id,
        "sinking_fund_id":    str(fund_id),
        "amount":             str(amount),
        "amount_mxn":         str(amount),
        "paid_on":            when.isoformat(),
        "kind":               "release",
        "notes":              data.notes or f"Released · {fund['name']}",
        "cycle_started_on":   fund["cycle_started_on"],
        "release_earning_id": earning_result.data[0]["id"],
    }).execute()

    return await get_fund_by_id(fund_id, user_id)


async def _get_or_create_release_category(user_id: str) -> Optional[str]:
    """One shared income category for all fund releases."""
    existing = (
        supabase_admin
        .table("categories")
        .select("id")
        .eq("user_id", user_id)
        .eq("name", "Fund Release")
        .eq("type", "income")
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    created = (
        supabase_admin
        .table("categories")
        .insert({
            "user_id": user_id,
            "name":    "Fund Release",
            "color":   "#14B8A6",
            "icon":    "piggy-bank",
            "type":    "income",
        })
        .execute()
    )
    return created.data[0]["id"] if created.data else None


async def delete_sinking_fund(
    fund_id:    UUID,
    user_id:    str,
    on_balance: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """
    Hard-deletes a fund. Returns (deleted, error_reason).

    Refuses while the fund still holds money unless the caller says what to
    do with it, because a fund's balance represents real money notionally
    sitting in savings. Archiving (is_active=false) is the softer default
    the UI offers first.

    Contribution expenses are NEVER deleted — expenses.sinking_fund_id is
    ON DELETE SET NULL, so financial history survives, matching how goals
    treats its own category.
    """
    fund = await get_fund_by_id(fund_id, user_id)
    if not fund:
        return False, "not_found"

    balance = Decimal(str(fund.get("balance_mxn") or 0))
    if balance > ZERO and on_balance not in ("keep", "release"):
        return False, "has_balance"

    if balance > ZERO and on_balance == "release":
        await release(fund_id, user_id, ReleaseRequest())

    had_payouts = bool(
        supabase_admin
        .table("sinking_fund_payouts")
        .select("id")
        .eq("sinking_fund_id", str(fund_id))
        .limit(1)
        .execute()
        .data
    )

    result = (
        supabase_admin
        .table("sinking_funds")
        .delete()
        .eq("id", str(fund_id))
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        return False, "not_found"

    # Only reclaim the auto-created category when it has no history behind
    # it. Deleting it otherwise would strand a year of contributions in
    # "uncategorized", since categories are ON DELETE SET NULL too.
    category_id = fund.get("category_id")
    if category_id and not had_payouts:
        linked = (
            supabase_admin
            .table("expenses")
            .select("id")
            .eq("category_id", category_id)
            .limit(1)
            .execute()
        )
        if not linked.data:
            supabase_admin.table("categories").delete().eq(
                "id", category_id
            ).eq("user_id", user_id).execute()

    return True, None
