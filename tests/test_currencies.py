"""
RF05 — refreshing exchange rates records when it happened.

Defect 11: update_exchange_rates wrote the literal string "now()" into
rate_updated_at. That is SQL, not a value. PostgREST passes it to Postgres
as a string, and 'now()' is not valid timestamp input — Postgres accepts the
special value 'now', without parentheses. So the update fails on the first
currency it touches, and the rate refresh as a whole never completes.

These tests stub the exchange rate API and the database, and check what the
function actually writes.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.currencies import service
from app.database import bind_db
from fakes import FakeSupabase

STALE = "2026-01-01T00:00:00+00:00"


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient; answers like ExchangeRate-API."""

    payload = {"result": "success", "conversion_rates": {"USD": 0.05}}

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def get(self, url: str) -> _FakeResponse:
        return _FakeResponse(self.payload)


@pytest.fixture
def rates_api(monkeypatch):
    monkeypatch.setattr(service.settings, "exchange_rate_api_key", "test-key")
    monkeypatch.setattr(service.httpx, "AsyncClient", _FakeAsyncClient)


def _currencies() -> FakeSupabase:
    return FakeSupabase(currencies=[
        {"id": "c-mxn", "code": "MXN", "name": "Mexican Peso", "symbol": "$",
         "exchange_rate": "1", "rate_updated_at": None},
        {"id": "c-usd", "code": "USD", "name": "US Dollar", "symbol": "$",
         "exchange_rate": "17", "rate_updated_at": STALE},
    ])


def _row(fake: FakeSupabase, code: str) -> dict:
    return next(r for r in fake.rows("currencies") if r["code"] == code)


async def test_rate_updated_at_is_a_real_timestamp_not_sql(rates_api):
    fake = _currencies()
    bind_db(fake)

    await service.update_exchange_rates()

    written = _row(fake, "USD")["rate_updated_at"]
    assert written != "now()", "wrote the SQL function name as a string"

    stamp = datetime.fromisoformat(written)
    assert stamp.tzinfo is not None, "timestamp must carry its timezone"
    assert stamp.utcoffset() == timedelta(0), "timestamp must be UTC"


async def test_rate_updated_at_changes_when_the_rate_is_updated(rates_api):
    """The check the cut-off document asks for, stated directly."""
    fake = _currencies()
    bind_db(fake)

    before = datetime.fromisoformat(_row(fake, "USD")["rate_updated_at"])
    await service.update_exchange_rates()
    after = datetime.fromisoformat(_row(fake, "USD")["rate_updated_at"])

    assert after > before
    assert datetime.now(timezone.utc) - after < timedelta(minutes=1)


async def test_the_rate_itself_is_inverted_against_mxn(rates_api):
    """The API gives 1 MXN = 0.05 USD; the table stores 1 USD = 20 MXN."""
    fake = _currencies()
    bind_db(fake)

    await service.update_exchange_rates()

    assert Decimal(_row(fake, "USD")["exchange_rate"]) == Decimal("20")


async def test_mxn_is_never_touched(rates_api):
    fake = _currencies()
    bind_db(fake)

    await service.update_exchange_rates()

    mxn = _row(fake, "MXN")
    assert mxn["exchange_rate"] == "1"
    assert mxn["rate_updated_at"] is None
