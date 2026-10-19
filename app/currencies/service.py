from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID
import logging
import httpx

from app.database import db, fetch_one
from app.config import settings

# ── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)


async def list_currencies() -> list[dict]:
    """
    Returns all currencies ordered by code.
    No user scoping needed — currencies are global reference data.
    """
    result = (
        db()
        .table("currencies")
        .select("*")
        .order("code")
        .execute()
    )

    return result.data or []


async def get_currency_by_id(currency_id: UUID) -> Optional[dict]:
    """
    Fetches a single currency by UUID.
    Returns None if not found.
    """
    result = fetch_one(
        db()
        .table("currencies")
        .select("*")
        .eq("id", str(currency_id))
    )

    return result if result else None


async def get_currency_by_code(code: str) -> Optional[dict]:
    """
    Fetches a single currency by ISO code (e.g. 'USD', 'MXN').
    Used internally by the conversion and rate update functions.
    """
    result = fetch_one(
        db()
        .table("currencies")
        .select("*")
        .eq("code", code.upper())
    )

    return result if result else None


async def convert_amount(
    amount: Decimal,
    from_currency_id: UUID,
    to_currency_id: UUID,
) -> dict:
    """
    Converts an amount between any two currencies using MXN as base.

    Conversion formula:
      1. Convert from_currency → MXN:  amount * from_rate
      2. Convert MXN → to_currency:    mxn_amount / to_rate

    Example: 100 USD → EUR
      100 * 17.15 = 1715 MXN
      1715 / 18.50 = 92.70 EUR

    Both rates are fetched fresh from DB on each call.
    This ensures conversion uses current rates not cached values.
    """
    from_currency = await get_currency_by_id(from_currency_id)
    to_currency   = await get_currency_by_id(to_currency_id)

    if not from_currency:
        raise ValueError(f"Source currency {from_currency_id} not found")

    if not to_currency:
        raise ValueError(f"Target currency {to_currency_id} not found")

    from_rate = Decimal(str(from_currency["exchange_rate"]))
    to_rate   = Decimal(str(to_currency["exchange_rate"]))

    # Convert to MXN first then to target currency
    amount_mxn       = amount * from_rate
    converted_amount = round(amount_mxn / to_rate, 2)

    # Rate used represents: 1 unit of from_currency = X units of to_currency
    rate_used = round(from_rate / to_rate, 6)

    return {
        "original_amount":  amount,
        "converted_amount": converted_amount,
        "from_currency":    from_currency["code"],
        "to_currency":      to_currency["code"],
        "rate_used":        rate_used,
    }


async def update_exchange_rates() -> dict:
    """
    Fetches latest exchange rates from ExchangeRate-API and updates DB.

    Only runs if EXCHANGE_RATE_API_KEY is configured.
    MXN rate is never updated — always stays at 1.0 (base currency).

    Returns a summary of what was updated.
    Called by:
      - POST /api/v1/currencies/update-rates (manual trigger)
      - Background scheduler (Phase 7)

    ExchangeRate-API free tier:
      1500 requests/month → running daily uses only 30/month
    """
    if not settings.exchange_rate_api_key:
        return {
            "status":  "skipped",
            "message": "No exchange rate API key configured",
            "updated": [],
        }

    url = (
        f"https://v6.exchangerate-api.com/v6/"
        f"{settings.exchange_rate_api_key}/latest/MXN"
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

    except httpx.TimeoutException:
        raise RuntimeError("Exchange rate API request timed out")

    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"Exchange rate API error: {e.response.status_code}")

    if data.get("result") != "success":
        raise RuntimeError(f"Exchange rate API returned error: {data}")

    # API returns rates as: 1 MXN = X foreign currency
    # We need the inverse:  1 foreign currency = X MXN
    rates = data.get("conversion_rates", {})
    updated = []

    # Fetch all currencies from our DB to match against API response
    all_currencies = await list_currencies()

    for currency in all_currencies:
        code = currency["code"]

        # Never update MXN — it is always 1.0 (our base)
        if code == "MXN":
            continue

        # Skip currencies not returned by the API
        if code not in rates:
            logger.warning(f"Rate for {code} not found in API response")
            continue

        # API gives: 1 MXN = X USD → we need 1 USD = X MXN
        # Inverse: 1 / (1 MXN = X USD) = X MXN per USD
        api_rate    = Decimal(str(rates[code]))
        our_rate    = round(Decimal("1") / api_rate, 6)

        result = (
            db()
            .table("currencies")
            .update({
                "exchange_rate":    str(our_rate),
                # A real UTC timestamp. This used to be the string "now()",
                # which is SQL, not a value: Postgres rejects it as
                # timestamp input, so every refresh failed (defect 11).
                "rate_updated_at":  datetime.now(timezone.utc).isoformat(),
            })
            .eq("code", code)
            .execute()
        )

        if result.data:
            updated.append({"code": code, "rate": str(our_rate)})
            logger.info(f"Updated {code} rate to {our_rate} MXN")

    return {
        "status":  "success",
        "updated": updated,
        "count":   len(updated),
    }