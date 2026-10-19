from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID
import logging

from app.auth.dependencies import get_current_user, AuthenticatedUser
from app.currencies.schemas import (
    CurrencyResponse,
    ConvertAmountRequest,
    ConvertAmountResponse,
)
from app.currencies import service

# ── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ── Router ────────────────────────────────────────────────────────────────
router = APIRouter()


# ── List Currencies ───────────────────────────────────────────────────────
@router.get(
    "/",
    response_model=list[CurrencyResponse],
    status_code=status.HTTP_200_OK,
    summary="List all available currencies",
)
async def list_currencies(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns all currencies with current exchange rates.
    Rates are relative to MXN (base currency).
    """
    return await service.list_currencies()


# ── Convert Amount ─────────────────────────────────────────────────────────
# IMPORTANT: this must be registered BEFORE /{currency_id}
# FastAPI matches routes in registration order
# If /{currency_id} is registered first, 'convert' is treated as a UUID
@router.post(
    "/convert",
    response_model=ConvertAmountResponse,
    status_code=status.HTTP_200_OK,
    summary="Convert an amount between two currencies",
)
async def convert_amount(
    body: ConvertAmountRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Converts an amount from one currency to another using MXN as base.
    Returns the converted amount and the rate used.
    """
    try:
        return await service.convert_amount(
            amount=body.amount,
            from_currency_id=body.from_currency_id,
            to_currency_id=body.to_currency_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ── Update Exchange Rates ──────────────────────────────────────────────────
# IMPORTANT: also registered before /{currency_id} for same reason
@router.post(
    "/update-rates",
    status_code=status.HTTP_200_OK,
    summary="Manually trigger exchange rate update",
)
async def update_exchange_rates(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Manually triggers a fetch of latest exchange rates from ExchangeRate-API.
    Requires EXCHANGE_RATE_API_KEY to be configured in .env.
    """
    try:
        # Runs as the system: currencies is shared data the user's own
        # client is not allowed to write under RLS.
        from app.scheduler import refresh_exchange_rates
        return await refresh_exchange_rates()
    except RuntimeError as e:
        logger.error(f"Rate update failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )


# ── Get Single Currency ────────────────────────────────────────────────────
# IMPORTANT: parameterized route registered LAST
# Prevents 'convert' and 'update-rates' from being captured as UUIDs
@router.get(
    "/{currency_id}",
    response_model=CurrencyResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a single currency by ID",
)
async def get_currency(
    currency_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns a single currency by UUID.
    Returns 404 if not found.
    """
    currency = await service.get_currency_by_id(currency_id)

    if not currency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Currency {currency_id} not found",
        )

    return currency