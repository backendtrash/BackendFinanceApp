from pydantic import BaseModel, field_validator
from typing import Optional
from uuid import UUID
from decimal import Decimal
from enum import Enum


class GoalType(str, Enum):
    fixed_amount  = "fixed_amount"
    monthly_rate  = "monthly_rate"


class GoalCreate(BaseModel):
    """
    DTO for POST /api/v1/goals
    Fixed amount goals require: target_amount, currency_id, deadline
    Monthly rate goals require: target_rate_pct
    """
    name:            str
    type:            GoalType
    target_amount:   Optional[Decimal] = None
    currency_id:     Optional[UUID]    = None
    deadline:        Optional[str]     = None
    target_rate_pct: Optional[Decimal] = None
    notes:           Optional[str]     = None
    savings_category_id: Optional[UUID]    = None
    # Starting amount already saved before goal creation
    # Stored separately — never affects net balance
    start_amount:        Optional[Decimal] = None


    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Goal name cannot be empty")
        if len(v) > 100:
            raise ValueError("Goal name cannot exceed 100 characters")
        return v

    @field_validator("target_amount")
    @classmethod
    def validate_target_amount(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("Target amount must be greater than zero")
        return v

    @field_validator("target_rate_pct")
    @classmethod
    def validate_rate(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and not 1 <= v <= 100:
            raise ValueError("Target rate must be between 1 and 100")
        return v


class GoalUpdate(BaseModel):
    name:            Optional[str]     = None
    target_amount:   Optional[Decimal] = None
    currency_id:     Optional[UUID]    = None
    deadline:        Optional[str]     = None
    target_rate_pct: Optional[Decimal] = None
    notes:           Optional[str]     = None
    is_active:       Optional[bool]    = None


class GoalResponse(BaseModel):
    """
    DTO for goal responses.
    Includes computed progress fields calculated by service layer.
    """
    id:               UUID
    user_id:          UUID
    name:             str
    type:             GoalType
    target_amount:    Optional[Decimal]
    currency_id:      Optional[UUID]
    deadline:         Optional[str]
    target_rate_pct:  Optional[Decimal]
    notes:                Optional[str]    = None
    savings_category_id:  Optional[UUID]   = None
    initial_amount:       Optional[Decimal] = Decimal("0")
    is_active:            bool
    

    # Computed progress fields
    current_savings:        Optional[Decimal] = None
    pct_complete:           Optional[Decimal] = None
    months_remaining:       Optional[int]     = None
    projected_completion:   Optional[str]     = None
    current_rate_pct:       Optional[Decimal] = None
    on_track:               Optional[bool]    = None

    created_at: str
    updated_at: str

    class Config:
        from_attributes = True