from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, ExpiredSignatureError
from jose import jwk
from typing import Optional
import logging
import httpx

from app.config import settings

# ── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ── Bearer Token Extractor ────────────────────────────────────────────────
# Extracts the JWT from the Authorization: Bearer <token> header
# auto_error=False means we handle the missing token error ourselves
# instead of getting a generic 403 from FastAPI
bearer_scheme = HTTPBearer(auto_error=False)

# ── JWKS Configuration ────────────────────────────────────────────────────
# Supabase exposes public keys at this endpoint for ES256 verification
# These public keys verify token signatures without exposing private keys
JWKS_URL = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"

# Module-level JWKS cache — fetched once on first request
# Avoids repeated HTTP calls to Supabase on every token verification
_jwks_cache: dict = {}


class AuthenticatedUser:
    """
    Represents a verified authenticated user extracted from JWT.
    Passed as a dependency to every protected endpoint.
    Contains only what endpoints actually need — no sensitive data.
    """

    def __init__(
        self,
        user_id: str,
        email: str,
        role: str = "authenticated",
    ):
        self.user_id = user_id
        self.email = email
        self.role = role

    def __repr__(self) -> str:
        return f"AuthenticatedUser(user_id={self.user_id}, email={self.email})"


async def get_jwks() -> dict:
    """
    Fetches Supabase's public JSON Web Key Set (JWKS).

    Cached in memory after first fetch — no repeated HTTP calls.
    JWKS contains the public keys used to verify ES256 JWT signatures.
    Supabase rotates these keys rarely — in-memory cache is safe.
    """
    global _jwks_cache

    # Return cached keys if already fetched
    if _jwks_cache:
        return _jwks_cache

    async with httpx.AsyncClient() as client:
        response = await client.get(JWKS_URL)
        response.raise_for_status()
        _jwks_cache = response.json()
        return _jwks_cache


async def decode_jwt(token: str) -> dict:
    """
    Decodes and validates a Supabase JWT token.

    Supports both ES256 (newer Supabase projects) and HS256 (older).
    ES256: verifies using public key from Supabase JWKS endpoint.
    HS256: verifies using JWT secret from project settings.

    Flow:
      1. Peek at token header to detect algorithm (no verification yet)
      2. For ES256 → fetch JWKS → find matching key by kid → verify
      3. For HS256 → verify using supabase_jwt_secret
      4. Return decoded payload on success
      5. Raise 401 on any validation failure
    """
    # Read token header without verifying to detect algorithm
    unverified_header = jwt.get_unverified_header(token)
    algorithm = unverified_header.get("alg", "HS256")

    try:
        if algorithm == "ES256":
            # ── ES256 verification ────────────────────────────────────────
            # Fetch public keys from Supabase JWKS endpoint
            jwks = await get_jwks()

            # Match the key by 'kid' (key ID) claim in token header
            # Supabase may have multiple keys during rotation periods
            kid = unverified_header.get("kid")
            public_key = None

            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    # Construct a verifiable public key object from JWK dict
                    public_key = jwk.construct(key)
                    break

            if not public_key:
                # kid in token does not match any known public key
                # Could mean token is forged or keys were rotated
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Unable to find matching public key",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            payload = jwt.decode(
                token,
                public_key,
                algorithms=["ES256"],
                # Audience verification disabled — Supabase sets this
                # inconsistently across versions
                options={"verify_aud": False},
            )

        else:
            # ── HS256 verification ────────────────────────────────────────
            # Older Supabase projects use symmetric HMAC signing
            # Verified using the JWT secret from project settings
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )

        return payload

    except ExpiredSignatureError:
        # Specific error for expired tokens
        # Frontend should catch 401 + "Token has expired" to trigger refresh
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except JWTError as e:
        # Catches all other JWT errors:
        # invalid signature, malformed token, wrong algorithm etc.
        logger.warning(f"JWT validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthenticatedUser:
    """
    FastAPI dependency that extracts and validates the current user.

    Usage in any protected endpoint:
        @router.get("/expenses")
        async def get_expenses(
            user: AuthenticatedUser = Depends(get_current_user)
        ):
            # user.user_id is guaranteed valid here

    Raises 401 if:
      - No Authorization header present
      - Token is malformed or signature invalid
      - Token has expired
      - Token claims are missing required fields
    """
    # No Authorization header provided at all
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Decode and validate the JWT — raises 401 on any failure
    payload = await decode_jwt(token)

    # Extract user identity from JWT payload
    # Supabase stores user_id in the 'sub' (subject) claim
    user_id: Optional[str] = payload.get("sub")
    email: Optional[str] = payload.get("email")
    role: str = payload.get("role", "authenticated")

    # sub claim must always be present in a valid Supabase JWT
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedUser(
        user_id=user_id,
        email=email or "",
        role=role,
    )


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[AuthenticatedUser]:
    """
    Same as get_current_user but returns None instead of raising 401.

    Use for endpoints that work for both authenticated and anonymous users.
    Example: GET /currencies works without login but could return
    user preferences if logged in.
    """
    if not credentials:
        return None

    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None