from pydantic import BaseModel, field_validator, computed_field
from typing import Optional
from datetime import date
from uuid import UUID
from decimal import Decimal


class ExpenseCreate(BaseModel):
    """
    DTO for POST /api/v1/expenses
    Validates all fields before hitting the database.
    amount_mxn is NOT included here — the service layer
    calculates it automatically from amount + currency rate.
    """
    amount:            Decimal
    currency_id:       UUID
    category_id:       Optional[UUID] = None
    date:              date
    notes:             Optional[str] = None
    is_recurring:      bool = False
    projected_cost_id: Optional[UUID] = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        """
        Enforces positive amount with max 2 decimal places.
        Decimal is used instead of float to avoid precision loss
        during validation before storing as NUMERIC in PostgreSQL.
        """
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        if v > Decimal("999999999.99"):
            raise ValueError("Amount exceeds maximum allowed value")
        # Round to 2 decimal places — matches NUMERIC(12,2) in DB
        return round(v, 2)

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, v: Optional[str]) -> Optional[str]:
        """
        Strips whitespace and converts empty string to None.
        Avoids storing empty string notes in the DB.
        """
        if v is not None:
            v = v.strip()
            return v if v else None
        return None


class ExpenseUpdate(BaseModel):
    """
    DTO for PATCH /api/v1/expenses/{id}
    All fields are optional — only provided fields are updated.
    date is handled as a plain string to avoid Pydantic v2
    date coercion conflicts with Optional[date] = None.
    Service layer converts it to a date object before DB operations.
    """
    amount:       Optional[Decimal] = None
    currency_id:  Optional[UUID]    = None
    category_id:  Optional[UUID]    = None
    date:         Optional[str]     = None
    notes:        Optional[str]     = None
    is_recurring: Optional[bool]    = None

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        """
        Validates date string format YYYY-MM-DD.
        Keeps as string to avoid Pydantic v2 None coercion issue.
        """
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


class ExpenseResponse(BaseModel):
    """
    DTO for all expense responses.
    Returned by GET, POST, PATCH endpoints.
    Includes all fields the frontend needs including computed ones.
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
    projected_cost_id: Optional[UUID] = None
    created_at:        str
    updated_at:        str

    class Config:
        # Allows Pydantic to read data from ORM objects and dicts
        # Needed because Supabase returns dicts not ORM instances
        from_attributes = True


class ExpenseFilters(BaseModel):
    """
    Query parameters for GET /api/v1/expenses
    All filters are optional — no filter returns all user expenses.
    Used for filtering by date range, category, week etc.
    """
    # Date range filters
    date_from:   Optional[date] = None
    date_to:     Optional[date] = None

    # Filter by specific category
    category_id: Optional[UUID] = None

    # Filter by specific week
    week_number: Optional[int]  = None
    week_year:   Optional[int]  = None

    # Filter by currency
    currency_id: Optional[UUID] = None

    # Pagination
    limit:       int            = 50
    offset:      int            = 0

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int) -> int:
        """
        Caps page size at 100 to prevent accidental full table scans.
        Frontend should paginate rather than fetch everything at once.
        """
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


class ExpenseListResponse(BaseModel):
    """
    Paginated response wrapper for GET /api/v1/expenses
    Includes total count so frontend can calculate page numbers.
    """
    data:    list[ExpenseResponse]
    total:   int
    limit:   int
    offset:  int