"""
How the API responds to tokens of each shape.

test_auth_required.py asks whether a route is reachable with no token at
all. This file asks what happens when a token is present but wrong, which
is the case the frontend actually depends on: it watches for 401 to know
when to refresh a session.

One endpoint is enough here. Every protected route resolves the same
get_current_user dependency, so token handling is a property of that
dependency rather than of any route.
"""
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.config import settings

ENDPOINT = "/api/v1/goals/"


def _hs256(claims: dict, secret: str | None = None) -> str:
    return jwt.encode(
        claims, secret or settings.supabase_jwt_secret, algorithm="HS256"
    )


def _valid_claims(**overrides) -> dict:
    claims = {
        "sub": "00000000-0000-0000-0000-000000000001",
        "email": "user@example.com",
        "role": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    claims.update(overrides)
    return claims


def test_no_authorization_header_is_401(client):
    response = client.get(ENDPOINT)
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_empty_bearer_value_is_401(client):
    response = client.get(ENDPOINT, headers={"Authorization": "Bearer "})
    assert response.status_code == 401


def test_expired_token_is_401(client):
    """
    The detail string matters as much as the code: the frontend matches on
    it to tell an expired session apart from a rejected one.
    """
    token = _hs256(_valid_claims(exp=datetime.now(timezone.utc) - timedelta(hours=1)))
    response = client.get(ENDPOINT, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["detail"] in {
        "Token has expired",
        "Invalid authentication token",
    }


def test_token_signed_with_the_wrong_secret_is_401(client):
    token = _hs256(_valid_claims(), secret="a-different-secret-entirely")
    response = client.get(ENDPOINT, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_token_without_sub_claim_is_401(client):
    claims = _valid_claims()
    del claims["sub"]
    token = _hs256(claims)
    response = client.get(ENDPOINT, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


# ── Known defect ──────────────────────────────────────────────────────────
# A malformed bearer token produces 500, not 401, on every protected
# endpoint — 69 of them.
#
# app/auth/dependencies.py:88 calls jwt.get_unverified_header(token) to read
# the algorithm, and that call sits one line ABOVE the try block that begins
# at line 91. A token that is not three base64 segments raises JWTError
# there, outside the handler, so it escapes as an unhandled exception.
#
# Consequences:
#   - an unauthenticated caller can trigger a 500 on the whole protected API
#   - the frontend never sees the 401 its refresh logic waits for
#   - the failure is logged as a server fault rather than a rejected request
#
# strict=True so these turn into failures the moment the bug is fixed and
# this file has to be updated. The fix belongs with the other changes to
# decode_jwt, which land in the configuration PR (3.5).
@pytest.mark.xfail(
    strict=True,
    reason="dependencies.py:88 reads the JWT header outside the try block, "
           "so a malformed token escapes as 500 instead of 401",
)
@pytest.mark.parametrize(
    "token",
    ["not-a-real-token", "a.b.c", "....", "Bearer-inside-the-value"],
    ids=["no-dots", "non-base64-segments", "empty-segments", "nested-bearer"],
)
def test_malformed_token_should_be_401(raw_client, token):
    response = raw_client.get(ENDPOINT, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401, (
        f"malformed token returned {response.status_code}"
    )


def test_malformed_token_currently_returns_500(raw_client):
    """
    Pins the defect above as it stands today, so the suite documents real
    behaviour rather than only the intent. Delete this together with the
    xfail when decode_jwt is fixed.
    """
    response = raw_client.get(
        ENDPOINT, headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 500
