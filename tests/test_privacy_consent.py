"""
RF01: an account can only be created by accepting the privacy notice.

Found missing on 19/10 (defect 24): neither the registration screen nor the
API asked for consent, though the notice requires express consent to
process financial data. The API now refuses to register without it and
stores the consent, server-timestamped, in the account's metadata.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.auth import router as auth_router
from app.auth.schemas import PRIVACY_NOTICE_VERSION
from app.main import limiter

VALID = {"email": "new@example.com", "password": "Secret123!"}


@pytest.fixture
def sign_ups(monkeypatch):
    """Captures what would be sent to Supabase; never reaches it."""
    calls = []

    def sign_up(credentials):
        calls.append(credentials)
        # Email confirmation pending: the route answers 202.
        return SimpleNamespace(session=None, user=SimpleNamespace(id="u-1", email=credentials["email"]))

    monkeypatch.setattr(auth_router, "supabase", SimpleNamespace(auth=SimpleNamespace(sign_up=sign_up)))
    # Registration is rate limited to 3/minute; these tests are not about that.
    monkeypatch.setattr(limiter, "enabled", False)
    return calls


def test_registering_without_the_field_is_refused(client, sign_ups):
    response = client.post("/api/v1/auth/register", json=VALID)
    assert response.status_code == 422
    assert sign_ups == [], "an account was created without consent"


def test_registering_while_declining_is_refused(client, sign_ups):
    response = client.post("/api/v1/auth/register", json={**VALID, "accepted_privacy": False})
    assert response.status_code == 422
    assert "Aviso de Privacidad" in response.text
    assert sign_ups == []


def test_accepting_creates_the_account_and_records_the_consent(client, sign_ups):
    before = datetime.now(timezone.utc)
    response = client.post("/api/v1/auth/register", json={**VALID, "accepted_privacy": True})

    assert response.status_code == 202
    assert len(sign_ups) == 1

    data = sign_ups[0]["options"]["data"]
    assert data["privacy_notice_version"] == PRIVACY_NOTICE_VERSION
    stamped = datetime.fromisoformat(data["privacy_accepted_at"])
    assert before - timedelta(seconds=5) <= stamped <= datetime.now(timezone.utc), \
        "consent must be timestamped by the server, now"
    assert data["optional_purposes_accepted"] is False, "voluntary purposes are opt-in"


def test_voluntary_purposes_are_recorded_only_when_chosen(client, sign_ups):
    client.post("/api/v1/auth/register",
                json={**VALID, "accepted_privacy": True, "accepted_optional_purposes": True})
    assert sign_ups[0]["options"]["data"]["optional_purposes_accepted"] is True


def test_a_client_cannot_backdate_its_consent(client, sign_ups):
    """Anything the client sends about when it consented is ignored."""
    client.post("/api/v1/auth/register",
                json={**VALID, "accepted_privacy": True, "privacy_accepted_at": "2000-01-01T00:00:00+00:00"})
    assert not sign_ups[0]["options"]["data"]["privacy_accepted_at"].startswith("2000")
