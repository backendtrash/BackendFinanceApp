from pydantic import BaseModel, field_validator
from typing import Optional
from uuid import UUID
from decimal import Decimal


class CurrencyResponse(BaseModel):
    """
    DTO for all currency responses.
    exchange_rate is relative to MXN (base currency).
    rate_updated_at is NULL if rate has never been fetched from API.
    """
    id:              UUID
    code:            str
    name:            str
    symbol:          str
    exchange_rate:   Decimal
    rate_updated_at: Optional[str]
    created_at:      str

    class Config:
        from_attributes = True


class CurrencyRateResponse(BaseModel):
    """
    Lightweight DTO for currency rate lookups.
    Used by frontend when converting amounts for display.
    """
    code:          str
    symbol:        str
    exchange_rate: Decimal


class ConvertAmountRequest(BaseModel):
    """
    DTO for POST /api/v1/currencies/convert
    Converts an amount between any two currencies via MXN as base.
    """
    amount:      Decimal
    from_currency_id: UUID
    to_currency_id:   UUID

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        return round(v, 2)


class ConvertAmountResponse(BaseModel):
    """
    DTO for currency conversion response.
    Returns both the converted amount and the rate used.
    Rate is included so frontend can display:
    "1 USD = 17.15 MXN"
    """
    original_amount:   Decimal
    converted_amount:  Decimal
    from_currency:     str
    to_currency:       str
    rate_used:         Decimal