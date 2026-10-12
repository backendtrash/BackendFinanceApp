from pydantic   import BaseModel, field_validator
from typing     import Optional
from decimal    import Decimal
from uuid       import UUID


class ProjectedCostFrequency:
    MONTHLY  = "monthly"
    WEEKLY   = "weekly"
    ONE_TIME = "one_time"


class ProjectedCostCreate(BaseModel):
    name:         str
    amount:       Decimal
    currency_id:  Optional[UUID]    = None
    frequency:    str               = "monthly"
    month:        Optional[int]     = None
    year:         Optional[int]     = None
    category_id:  Optional[UUID]    = None
    is_active:    bool              = True
    notes:        Optional[str]     = None
    plan_group:   str               = "committed"
    # Day of week for weekly costs (0=Mon, 6=Sun)
    day_of_week:  Optional[int]     = None
    # Day of month for monthly costs (1-31)
    day_of_month: Optional[int]     = None

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: str) -> str:
        if v not in ("monthly", "weekly", "one_time"):
            raise ValueError("frequency must be monthly, weekly, or one_time")
        return v

    @field_validator("plan_group")
    @classmethod
    def validate_plan_group(cls, v: str) -> str:
        if v not in ("committed", "living", "lifestyle"):
            raise ValueError("plan_group must be committed, living, or lifestyle")
        return v

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        return v


class ProjectedCostUpdate(BaseModel):
    name:         Optional[str]     = None
    amount:       Optional[Decimal] = None
    currency_id:  Optional[UUID]    = None
    frequency:    Optional[str]     = None
    month:        Optional[int]     = None
    year:         Optional[int]     = None
    category_id:  Optional[UUID]    = None
    is_active:    Optional[bool]    = None
    notes:        Optional[str]     = None
    plan_group:   Optional[str]     = None
    day_of_week:  Optional[int]     = None
    day_of_month: Optional[int]     = None


class ProjectedCostResponse(BaseModel):
    id:           str
    user_id:      str
    name:         str
    amount:       Decimal
    amount_mxn:   Decimal
    currency_id:  Optional[str] = None
    frequency:    str
    month:        Optional[int] = None
    year:         Optional[int] = None
    category_id:  Optional[str] = None
    is_active:    bool
    notes:        Optional[str] = None
    plan_group:   str           = "committed"
    day_of_week:  Optional[int] = None
    day_of_month: Optional[int] = None
    created_at:   str
    updated_at:   str