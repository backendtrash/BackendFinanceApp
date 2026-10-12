"""
How the API responds to tokens of each shape.

test_auth_required.py asks whether a route is reachable with no token at
all. This file asks what happens when a token is present but wrong, which
is the case the frontend depends on: it watches for 401 to know when to
refresh a session.

Tokens here are real ES256, signed with a keypair generated for the test
and verified through the same JWKS path production uses — the cache is
pre-filled so nothing reaches the network. That matters: these used to be
HS256 tokens riding the fallback branch, and once that branch was removed
they would have been testing rejection-by-wrong-algorithm while appearing
to test expiry and claims.

One endpoint is enough. Every protected route resolves the same
get_current_user dependency, so this is a property of the dependency.
"""
import base64
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jose import jwt

from app.auth import dependencies

ENDPOINT = "/api/v1/goals/"
KID = "test-signing-key"


def _b64url_uint(value: int, length: int = 32) -> str:
    raw = value.to_bytes(length, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.fixture(scope="session")
def signing_key() -> tuple[str, dict]:
    """A P-256 keypair: the PEM to sign with, and the JWK to publish."""
    key = ec.generate_private_key(ec.SECP256R1())

    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    numbers = key.public_key().public_numbers()
    public_jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64url_uint(numbers.x),
        "y": _b64url_uint(numbers.y),
        "kid": KID,
        "alg": "ES256",
        "use": "sig",
    }
    return pem, public_jwk


@pytest.fixture(autouse=True)
def published_keys(signing_key, monkeypatch):
    """
    Pre-fill the JWKS cache so verification uses our key and never calls
    out. get_jwks() returns the cache whenever it is non-empty.
    """
    _, public_jwk = signing_key
    monkeypatch.setattr(dependencies, "_jwks_cache", {"keys": [public_jwk]})


def _token(signing_key, *, kid: str = KID, **overrides) -> str:
    pem, _ = signing_key
    claims = {
        "sub": "00000000-0000-0000-0000-000000000001",
        "email": "user@example.com",
        "role": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    claims.update(overrides)
    return jwt.encode(claims, pem, algorithm="ES256", headers={"kid": kid})


def _get(client, token: str):
    return client.get(ENDPOINT, headers={"Authorization": f"Bearer {token}"})


# ── The happy path, so the rejections below mean something ────────────────

async def test_a_valid_es256_token_is_accepted(signing_key):
    """
    Not a rejection. Without this the whole file could pass with
    authentication broken in a way that refuses everything.

    Checked against decode_jwt rather than over HTTP: a token that is
    accepted means the handler runs, and every protected handler then
    queries Supabase. Going through the endpoint would be testing the
    network, not the token.
    """
    payload = await dependencies.decode_jwt(_token(signing_key))

    assert payload["sub"] == "00000000-0000-0000-0000-000000000001"
    assert payload["email"] == "user@example.com"


# ── Missing or empty ──────────────────────────────────────────────────────

def test_no_authorization_header_is_401(client):
    response = client.get(ENDPOINT)
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_empty_bearer_value_is_401(client):
    response = client.get(ENDPOINT, headers={"Authorization": "Bearer "})
    assert response.status_code == 401


# ── Present but invalid ───────────────────────────────────────────────────

def test_expired_token_is_401_with_the_detail_the_frontend_matches(client, signing_key):
    token = _token(
        signing_key, exp=datetime.now(timezone.utc) - timedelta(hours=1)
    )
    response = _get(client, token)

    assert response.status_code == 401
    assert response.json()["detail"] == "Token has expired", (
        "the frontend keys its refresh logic off this exact string"
    )


def test_a_token_signed_by_an_unknown_key_is_401(client):
    """Correctly formed ES256, signed by a keypair that is not published."""
    other = ec.generate_private_key(ec.SECP256R1())
    pem = other.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    token = jwt.encode(
        {"sub": "attacker", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        pem,
        algorithm="ES256",
        headers={"kid": KID},      # claims to be the published key
    )

    assert _get(client, token).status_code == 401


def test_an_unknown_kid_is_401(client, signing_key):
    token = _token(signing_key, kid="some-other-key")
    response = _get(client, token)

    assert response.status_code == 401
    assert response.json()["detail"] == "Unable to find matching public key"


def test_a_token_without_sub_is_401(client, signing_key):
    pem, _ = signing_key
    token = jwt.encode(
        {"email": "user@example.com",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        pem,
        algorithm="ES256",
        headers={"kid": KID},
    )

    response = _get(client, token)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token claims"


# ── Malformed: was a 500 on every protected endpoint ──────────────────────

@pytest.mark.parametrize(
    "token",
    ["not-a-real-token", "a.b.c", "....", "Bearer-inside-the-value", ""],
    ids=["no-dots", "non-base64", "empty-segments", "nested-bearer", "empty"],
)
def test_a_malformed_token_is_401_not_500(raw_client, token):
    """
    Regression test. Reading the JWT header to pick an algorithm used to
    happen one line above the try block, so a token that is not three
    base64 segments raised out of the handler and became a 500 — on all 69
    protected endpoints, reachable by anyone, and never showing the
    frontend the 401 it waits for.

    The header read is inside the try now, and there is no algorithm to
    pick.
    """
    response = raw_client.get(
        ENDPOINT, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401, (
        f"malformed token returned {response.status_code}"
    )


# ── The HS256 fallback is gone ────────────────────────────────────────────

def test_an_hs256_token_is_rejected(raw_client):
    """
    The fallback chose its verification algorithm by reading "alg" out of
    the unverified header, which let the caller decide how their own token
    would be checked. With it removed, an HS256 token is simply not a
    token this API accepts.
    """
    token = jwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000001",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "any-secret-at-all",
        algorithm="HS256",
    )

    assert _get(raw_client, token).status_code == 401


def test_the_jwt_secret_is_no_longer_a_setting():
    """
    3.5 asked whether SUPABASE_JWT_SECRET was still used. It was — by the
    fallback above. With that gone it is genuinely unused, so it came out
    of Settings entirely rather than staying as a required variable that
    nothing reads.
    """
    from app.config import Settings

    assert "supabase_jwt_secret" not in Settings.model_fields
