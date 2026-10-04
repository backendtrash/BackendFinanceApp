from pydantic import BaseModel, field_validator
from typing import Optional
from uuid import UUID
from decimal import Decimal
from enum import Enum


class BudgetPeriod(str, Enum):
    """
    Mirrors budget_period ENUM in PostgreSQL.
    Enforces valid period values at API level.
    """
    weekly  = "weekly"
    monthly = "monthly"


class BudgetCreate(BaseModel):
    """
    DTO for POST /api/v1/budgets
    category_id is optional — NULL means global budget
    covering all categories combined.
    """
    category_id:     Optional[UUID]    = None
    limit_amount:    Decimal
    currency_id:     UUID
    period:          BudgetPeriod      = BudgetPeriod.monthly
    alert_threshold: int               = 80

    @field_validator("limit_amount")
    @classmethod
    def validate_limit_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Limit amount must be greater than zero")
        if v > Decimal("999999999.99"):
            raise ValueError("Limit amount exceeds maximum allowed value")
        return round(v, 2)

    @field_validator("alert_threshold")
    @classmethod
    def validate_alert_threshold(cls, v: int) -> int:
        if not 1 <= v <= 100:
            raise ValueError("Alert threshold must be between 1 and 100")
        return v


class BudgetUpdate(BaseModel):
    """
    DTO for PATCH /api/v1/budgets/{id}
    category_id cannot be changed after creation — it defines what the
    budget tracks. period IS updatable (switch weekly/monthly reset),
    along with limit and alert settings.
    """
    limit_amount:    Optional[Decimal]      = None
    currency_id:     Optional[UUID]         = None
    period:          Optional[BudgetPeriod] = None
    alert_threshold: Optional[int]          = None
    is_active:       Optional[bool]         = None

    @field_validator("limit_amount")
    @classmethod
    def validate_limit_amount(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None:
            if v <= 0:
                raise ValueError("Limit amount must be greater than zero")
            if v > Decimal("999999999.99"):
                raise ValueError("Limit amount exceeds maximum allowed value")
            return round(v, 2)
        return v

    @field_validator("alert_threshold")
    @classmethod
    def validate_alert_threshold(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not 1 <= v <= 100:
            raise ValueError("Alert threshold must be between 1 and 100")
        return v


class BudgetResponse(BaseModel):
    """
    DTO for budget responses.
    Includes spent_amount and pct_spent computed by service layer
    so frontend can render progress bars without extra API calls.
    """
    id:              UUID
    user_id:         UUID
    category_id:     Optional[UUID]
    limit_amount:    Decimal
    currency_id:     UUID
    period:          BudgetPeriod
    alert_threshold: int
    is_active:       bool

    # Computed fields — not stored in DB
    # Calculated fresh on every fetch
    spent_amount:    Decimal
    pct_spent:       Decimal
    remaining:       Decimal

    created_at:      str
    updated_at:      str

    class Config:
        from_attributes = True


class BudgetAlertResponse(BaseModel):
    """
    DTO for budget alert history.
    """
    id:             UUID
    budget_id:      UUID
    pct_spent:      Decimal
    amount_spent:   Decimal
    limit_amount:   Decimal
    triggered_date: str
    triggered_at:   str

    class Config:
        from_attributes = True