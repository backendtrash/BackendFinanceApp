"""
Defect 16: any signed-in user could trigger an exchange rate refresh.

POST /currencies/update-rates writes the shared currencies table as the
system — every user's conversions — and spends the rate API's monthly
quota. It is now limited to ADMIN_EMAILS, and a daily job does the refresh
so nobody else needs to.
"""
import pytest

from app import scheduler as scheduler_module
from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.config import settings
from app.main import app


@pytest.fixture
def signed_in_as(client, monkeypatch):
    calls = []

    async def fake_refresh():
        calls.append(True)
        return {"status": "success", "updated": [], "count": 0}

    monkeypatch.setattr(scheduler_module, "refresh_exchange_rates", fake_refresh)
    monkeypatch.setattr(settings, "admin_emails", "admin@example.com, Ops@Example.com")

    def as_email(email):
        async def fake_user():
            return AuthenticatedUser(user_id="u-1", email=email)
        app.dependency_overrides[get_current_user] = fake_user
        return client

    yield as_email, calls
    app.dependency_overrides.clear()


def test_an_ordinary_user_is_refused(signed_in_as):
    as_email, calls = signed_in_as
    response = as_email("someone@example.com").post("/api/v1/currencies/update-rates")

    assert response.status_code == 403
    assert calls == [], "the refresh ran for a non-administrator"


def test_an_administrator_can_refresh(signed_in_as):
    as_email, calls = signed_in_as
    response = as_email("admin@example.com").post("/api/v1/currencies/update-rates")

    assert response.status_code == 200
    assert calls == [True]


def test_admin_emails_match_case_insensitively(signed_in_as):
    as_email, calls = signed_in_as
    response = as_email("OPS@example.COM").post("/api/v1/currencies/update-rates")
    assert response.status_code == 200


def test_with_no_admins_configured_nobody_can(signed_in_as, monkeypatch):
    as_email, calls = signed_in_as
    monkeypatch.setattr(settings, "admin_emails", "")
    response = as_email("admin@example.com").post("/api/v1/currencies/update-rates")
    assert response.status_code == 403


def test_rates_refresh_daily_on_their_own():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    fresh = AsyncIOScheduler()
    original = scheduler_module.scheduler
    scheduler_module.scheduler = fresh
    try:
        scheduler_module.setup_scheduler()
        jobs = {job.id: job for job in fresh.get_jobs()}
    finally:
        scheduler_module.scheduler = original

    assert "refresh_exchange_rates" in jobs
    assert str(jobs["refresh_exchange_rates"].trigger) == "cron[hour='6', minute='0']"
