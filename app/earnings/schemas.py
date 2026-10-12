from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import date
from uuid import UUID
from decimal import Decimal


class EarningCreate(BaseModel):
    """
    DTO for POST /api/v1/earnings
    amount_mxn calculated automatically by service layer.
    """
    amount:       Decimal
    currency_id:  UUID
    category_id:  Optional[UUID] = None
    date:         date
    notes:        Optional[str]  = None
    is_recurring: bool           = False

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        if v > Decimal("999999999.99"):
            raise ValueError("Amount exceeds maximum allowed value")
        return round(v, 2)

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return None


class EarningUpdate(BaseModel):
    """
    DTO for PATCH /api/v1/earnings/{id}
    All fields optional — partial update semantics.
    """
    amount:       Optional[Decimal] = None
    currency_id:  Optional[UUID]    = None
    category_id:  Optional[UUID]    = None
    notes:        Optional[str]     = None
    is_recurring: Optional[bool]    = None
    date:         Optional[str]     = None

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                from datetime import date as date_type
                date_type.fromisoformat(v)
            except ValueError:
                raise ValueError("Date must be in YYYY-MM-DD format")
        return v
    
    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None:
            if v <= 0:
                raise ValueError("Amount must be greater than zero")
            if v > Decimal("999999999.99"):
                raise ValueError("Amount exceeds maximum allowed value")
            return round(v, 2)
        return v

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return None


class EarningResponse(BaseModel):
    """
    DTO for all earning responses.
    Identical structure to ExpenseResponse — both are financial transactions.
    """
    id:                UUID
    user_id:           UUID
    amount:            Decimal
    currency_id:       UUID
    amount_mxn:        Decimal
    category_id:       Optional[UUID]
    date:              date
    week_number:       int
    week_year:         int
    notes:             Optional[str]
    is_recurring:      bool
    recurring_rule_id: Optional[UUID]
    created_at:        str
    updated_at:        str

    class Config:
        from_attributes = True


class EarningFilters(BaseModel):
    """
    Query parameters for GET /api/v1/earnings
    """
    date_from:   Optional[date] = None
    date_to:     Optional[date] = None
    category_id: Optional[UUID] = None
    week_number: Optional[int]  = None
    week_year:   Optional[int]  = None
    currency_id: Optional[UUID] = None
    limit:       int            = 50
    offset:      int            = 0

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Limit must be at least 1")
        if v > 500:
            raise ValueError("Limit cannot exceed 500")
        return v

    @field_validator("offset")
    @classmethod
    def validate_offset(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Offset cannot be negative")
        return v


class EarningListResponse(BaseModel):
    """
    Paginated response wrapper for GET /api/v1/earnings
    """
    data:   list[EarningResponse]
    total:  int
    limit:  int
    offset: int