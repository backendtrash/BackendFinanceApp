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
    Decodes and validates a Supabase JWT.

    ES256 only, verified against the public keys Supabase publishes at its
    JWKS endpoint.

    There used to be an HS256 branch here for older Supabase projects,
    selected by reading the "alg" field out of the token's own header
    before any signature had been checked. Two problems with that:

      - the attacker picks the algorithm. Choosing which key to verify
        with based on an unverified claim is algorithm confusion, and the
        whole point of verification is that nothing in the token is
        trusted until the signature holds.
      - it required SUPABASE_JWT_SECRET to be configured even though this
        project issues ES256, so a shared secret was carried in the
        environment for a path that never ran.

    The design approved at H2 specifies ES256 via JWKS. This now matches it.

    Every failure here is a 401. Reading the header is inside the try block
    on purpose: a token that is not three base64 segments raises JWTError
    there, and when that call sat above the try it escaped as an unhandled
    exception, turning any malformed token into a 500 on all 69 protected
    endpoints.
    """
    try:
        # Not trusted — only used to find which published key to verify
        # against. The signature check below is what actually decides.
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        jwks = await get_jwks()

        public_key = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                public_key = jwk.construct(key)
                break

        if not public_key:
            # kid matches no known key: forged, or signed before a rotation.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to find matching public key",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return jwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            # Audience verification disabled — Supabase sets this
            # inconsistently across versions
            options={"verify_aud": False},
        )

    except ExpiredSignatureError:
        # Frontend watches for this exact detail to trigger a refresh.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except JWTError as e:
        # Invalid signature, malformed token, wrong algorithm, bad header.
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
