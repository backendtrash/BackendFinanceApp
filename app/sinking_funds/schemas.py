from pydantic import BaseModel, field_validator, model_validator
from typing   import Optional, Literal
from uuid     import UUID
from decimal  import Decimal
# Imported under an alias on purpose. ContributeRequest and ReleaseRequest
# each declare a field literally named `date` with a default, which binds
# `date` in the class namespace and shadows this import — Optional[date]
# then resolves to Optional[None], and Pydantic rejects every real date with
# "Input should be None". app/expenses/schemas.py hit the same trap and
# worked around it by weakening the field to Optional[str]; aliasing keeps
# proper date validation instead.
from datetime import date as date_type
from enum     import Enum


class SinkingFundMode(str, Enum):
    """
    target_by_date   — user gives target + due date, app derives the set-aside
    fixed_per_period — user gives an amount per period, app derives the end date
    """
    target_by_date   = "target_by_date"
    fixed_per_period = "fixed_per_period"


class Cadence(str, Enum):
    """
    Deliberately NOT reusing projected_costs.frequency, which also allows
    'one_time'. A one-time set-aside is just an expense, so allowing that
    value here would only invite a 500 from a shared form component.
    """
    weekly  = "weekly"
    monthly = "monthly"


class RepeatInterval(str, Enum):
    none       = "none"
    monthly    = "monthly"
    quarterly  = "quarterly"
    semiannual = "semiannual"
    annual     = "annual"


FundStatus = Literal[
    "on_track", "behind", "ahead", "funded", "overdue", "paid"
]


# ── Create ────────────────────────────────────────────────────────────────
class SinkingFundCreate(BaseModel):
    name:                str
    mode:                SinkingFundMode = SinkingFundMode.target_by_date
    target_amount:       Optional[Decimal] = None
    currency_id:         Optional[UUID]    = None
    contribution_amount: Optional[Decimal] = None

    cadence:                   Cadence       = Cadence.monthly
    contribution_day_of_week:  Optional[int] = None   # 0=Mon .. 6=Sun
    contribution_day_of_month: Optional[int] = None   # 1..31

    due_date:             Optional[date_type]  = None
    repeat_interval:      RepeatInterval  = RepeatInterval.none
    renewal_increase_pct: Decimal         = Decimal("0")
    auto_renew:           bool            = True

    # Money already saved before the fund existed.
    # Stored as opening_balance — never creates an expense, so it never
    # distorts net balance. Same carve-out as goals.initial_amount.
    start_amount:      Optional[Decimal] = None

    # Omit to auto-create a "<name> Fund" expense category.
    category_id:       Optional[UUID] = None
    projected_cost_id: Optional[UUID] = None
    notes:             Optional[str]  = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Fund name cannot be empty")
        if len(v) > 100:
            raise ValueError("Fund name cannot exceed 100 characters")
        return v

    @field_validator("target_amount", "contribution_amount", "start_amount")
    @classmethod
    def validate_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None:
            if v <= 0:
                raise ValueError("Amount must be greater than zero")
            if v > Decimal("999999999.99"):
                raise ValueError("Amount exceeds maximum allowed value")
            return round(v, 2)
        return v

    @field_validator("contribution_day_of_week")
    @classmethod
    def validate_dow(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not 0 <= v <= 6:
            raise ValueError("contribution_day_of_week must be between 0 and 6")
        return v

    @field_validator("contribution_day_of_month")
    @classmethod
    def validate_dom(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not 1 <= v <= 31:
            raise ValueError("contribution_day_of_month must be between 1 and 31")
        return v

    @model_validator(mode="after")
    def validate_mode_fields(self):
        """Mirrors the sinking_funds_mode_fields CHECK constraint so the user
        gets a 422 with a readable message instead of a database error."""
        if self.mode is SinkingFundMode.target_by_date:
            if self.target_amount is None or self.due_date is None:
                raise ValueError(
                    "target_by_date requires both target_amount and due_date"
                )
        elif self.contribution_amount is None:
            raise ValueError(
                "fixed_per_period requires contribution_amount"
            )

        if self.repeat_interval is not RepeatInterval.none and self.due_date is None:
            raise ValueError("A repeating fund requires a due_date to roll forward from")

        return self


# ── Update ────────────────────────────────────────────────────────────────
class SinkingFundUpdate(BaseModel):
    """
    All optional. mode is intentionally updatable — every derived number is
    recomputed on read, so there is no schedule to migrate.
    """
    name:                Optional[str]     = None
    mode:                Optional[SinkingFundMode] = None
    target_amount:       Optional[Decimal] = None
    currency_id:         Optional[UUID]    = None
    contribution_amount: Optional[Decimal] = None

    cadence:                   Optional[Cadence] = None
    contribution_day_of_week:  Optional[int]     = None
    contribution_day_of_month: Optional[int]     = None

    due_date:             Optional[date_type]      = None
    repeat_interval:      Optional[RepeatInterval] = None
    renewal_increase_pct: Optional[Decimal]        = None
    auto_renew:           Optional[bool]           = None

    projected_cost_id: Optional[UUID] = None
    # Repairs a fund whose auto-created category failed silently before this
    # fix landed — those funds have category_id = NULL with no way back
    # through the API. New funds normally never need this set explicitly.
    category_id:       Optional[UUID] = None
    notes:             Optional[str]  = None
    is_active:         Optional[bool] = None

    @field_validator("target_amount", "contribution_amount")
    @classmethod
    def validate_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None:
            if v <= 0:
                raise ValueError("Amount must be greater than zero")
            return round(v, 2)
        return v


# ── Actions ───────────────────────────────────────────────────────────────
class ContributeRequest(BaseModel):
    """Creates a REAL expense linked to the fund. Net balance drops."""
    amount:      Optional[Decimal] = None   # default: this period's set-aside
    currency_id: Optional[UUID]    = None   # default: MXN
    date:        Optional[date_type] = None   # default: today
    notes:       Optional[str]     = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("Amount must be greater than zero")
        return round(v, 2) if v is not None else v


class PayoutRequest(BaseModel):
    """
    Records the bill being paid out of the fund. Creates NO expense, so net
    balance does not move — the money already left as contributions.

    If the fund is short, a top-up contribution expense is created first for
    the shortfall, which is the only part that should hit net balance.
    """
    amount:       Optional[Decimal] = None   # default: target_amount
    currency_id:  Optional[UUID]    = None
    paid_on:      Optional[date_type] = None   # default: today
    notes:        Optional[str]     = None
    renew:        Optional[bool]    = None   # default: fund.auto_renew
    allow_top_up: bool              = True   # False -> 409 when short


class ReleaseRequest(BaseModel):
    """
    Returns fund money to the spendable pool. Creates an EARNING, because
    expenses.amount has a > 0 validator so a negative contribution is
    impossible and deleting past contributions would destroy history.

    Rare and explicit — the default for leftover money is to carry it into
    the next cycle, not to release it.
    """
    amount:      Optional[Decimal] = None    # default: full balance
    date:        Optional[date_type] = None
    notes:       Optional[str]     = None


# ── Responses ─────────────────────────────────────────────────────────────
class SinkingFundPayoutResponse(BaseModel):
    id:                 UUID
    user_id:            UUID
    sinking_fund_id:    UUID
    amount:             Decimal
    currency_id:        Optional[UUID] = None
    amount_mxn:         Decimal
    paid_on:            str
    kind:               str
    notes:              Optional[str] = None
    cycle_started_on:   str
    cycle_due_date:     Optional[str]  = None
    top_up_expense_id:  Optional[UUID] = None
    release_earning_id: Optional[UUID] = None
    projected_cost_id:  Optional[UUID] = None
    created_at:         str

    class Config:
        from_attributes = True


class SinkingFundResponse(BaseModel):
    # ── Stored ────────────────────────────────────────────────────────────
    id:                  UUID
    user_id:             UUID
    name:                str
    notes:               Optional[str]     = None
    target_amount:       Optional[Decimal] = None
    currency_id:         Optional[UUID]    = None
    opening_balance:     Decimal
    mode:                SinkingFundMode
    contribution_amount: Optional[Decimal] = None

    cadence:                   Cadence
    contribution_day_of_week:  Optional[int] = None
    contribution_day_of_month: Optional[int] = None

    due_date:             Optional[str] = None
    cycle_started_on:     str
    repeat_interval:      RepeatInterval
    renewal_increase_pct: Decimal
    auto_renew:           bool

    category_id:       Optional[UUID] = None
    projected_cost_id: Optional[UUID] = None
    is_active:         bool

    # ── Computed ──────────────────────────────────────────────────────────
    # target converted at TODAY's rate; contributions are frozen at their
    # own rate. For a genuinely foreign bill that gap is correct — you
    # really do need more pesos — so it is surfaced, never smoothed over.
    target_amount_mxn:     Optional[Decimal] = None
    contributed_mxn:       Decimal
    paid_out_mxn:          Decimal
    balance_mxn:           Decimal
    remaining_mxn:         Decimal
    pct_complete:          Decimal
    periods_remaining:     int
    # Catch-up aware — recomputed from today's balance every read.
    set_aside_this_period: Decimal
    # Steady state, ignoring catch-up. Used for FUTURE weeks in Week View.
    base_per_period:       Decimal
    monthly_equivalent:    Decimal
    expected_balance_mxn:  Optional[Decimal] = None
    schedule_variance_mxn: Optional[Decimal] = None
    status:                FundStatus
    is_overdue:            bool
    paid_this_cycle:       bool
    last_payout_on:        Optional[str] = None
    projected_completion:  Optional[str] = None
    # True when the computed balance went negative — a contribution was
    # edited or deleted after a payout. Displayed balance is clamped at 0.
    has_ledger_warning:    bool = False

    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class PayoutResult(BaseModel):
    fund:           SinkingFundResponse
    payout:         SinkingFundPayoutResponse
    top_up_expense: Optional[dict] = None
    renewed:        bool


class ContributeResult(BaseModel):
    fund:    SinkingFundResponse
    expense: dict


class FundActivityEntry(BaseModel):
    """A merged contribution + payout ledger row for the fund detail view."""
    id:         UUID
    kind:       str            # 'contribution' | 'payout' | 'release' | 'top_up'
    amount_mxn: Decimal
    date:       str
    notes:      Optional[str] = None
