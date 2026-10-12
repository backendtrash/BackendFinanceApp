from pydantic import BaseModel, field_validator
from typing import Optional
from uuid import UUID
from decimal import Decimal
from datetime import date
from enum import Enum


class FrequencyType(str, Enum):
    """
    Mirrors frequency_type ENUM in PostgreSQL.
    Only weekly and monthly per project requirements.
    """
    weekly  = "weekly"
    monthly = "monthly"


class TransactionType(str, Enum):
    """
    Mirrors transaction_type ENUM in PostgreSQL.
    """
    expense = "expense"
    income  = "income"


class RecurringRuleCreate(BaseModel):
    """
    DTO for POST /api/v1/recurring
    next_due_date defaults to start_date if not provided.
    The background job uses next_due_date to know when to fire.
    """
    type:          TransactionType
    amount:        Decimal
    currency_id:   UUID
    category_id:   Optional[UUID]    = None
    description:   Optional[str]     = None
    frequency:     FrequencyType
    start_date:    date              = None
    end_date:      Optional[date]    = None

    # Weekly rules: 0=Monday, 1=Tuesday ... 6=Sunday
    day_of_week:   Optional[int]     = None

    # Monthly rules: 1-31
    day_of_month:  Optional[int]     = None

    @field_validator("day_of_week")
    @classmethod
    def validate_day_of_week(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not 0 <= v <= 6:
            raise ValueError("day_of_week must be between 0 and 6")
        return v

    @field_validator("day_of_month")
    @classmethod
    def validate_day_of_month(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not 1 <= v <= 31:
            raise ValueError("day_of_month must be between 1 and 31")
        return v

    def model_post_init(self, __context) -> None:
        """
        Sets start_date to today if not provided.
        Called automatically by Pydantic after __init__.
        """
        if self.start_date is None:
            object.__setattr__(self, "start_date", date.today())

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        if v > Decimal("999999999.99"):
            raise ValueError("Amount exceeds maximum allowed value")
        return round(v, 2)

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return None

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, v: Optional[date]) -> Optional[date]:
        """
        end_date validation against start_date happens in the router
        after both values are available.
        """
        return v


class RecurringRuleUpdate(BaseModel):
    """
    DTO for PATCH /api/v1/recurring/{id}
    type and frequency cannot be changed — they define rule behavior.
    Changing them would make historical transactions inconsistent.
    """
    amount:          Optional[Decimal] = None
    currency_id:     Optional[UUID]    = None
    category_id:     Optional[UUID]    = None
    description:     Optional[str]     = None
    end_date:        Optional[date]    = None
    is_active:       Optional[bool]    = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None:
            if v <= 0:
                raise ValueError("Amount must be greater than zero")
            return round(v, 2)
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return None


class RecurringRuleResponse(BaseModel):
    """
    DTO for recurring rule responses.
    Includes next_due_date so frontend can show
    when the next transaction will be generated.
    """
    id:            UUID
    user_id:       UUID
    type:          TransactionType
    amount:        Decimal
    currency_id:   UUID
    category_id:   Optional[UUID]
    description:   Optional[str]
    frequency:     FrequencyType
    start_date:    str
    end_date:      Optional[str]
    next_due_date: str
    day_of_week:   Optional[int]
    day_of_month:  Optional[int]
    is_active:     bool
    created_at:    str
    updated_at:    str

    class Config:
        from_attributes = True


class ProcessRecurringResponse(BaseModel):
    """
    Response from POST /api/v1/recurring/process
    Shows how many rules were processed and transactions created.
    """
    processed:    int
    created:      int
    errors:       int
    transactions: list[dict]