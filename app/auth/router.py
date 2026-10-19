from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import JSONResponse
from gotrue.errors import AuthApiError
from app.main import limiter
import logging

from app.database import supabase, delete_auth_user
from app.auth.schemas import (
    RegisterRequest,
    LoginRequest,
    AuthResponse,
    AuthUserResponse,
    RefreshRequest,
    MessageResponse,
    MeResponse,
)
from app.auth.dependencies import get_current_user, AuthenticatedUser
from fastapi import Depends

# ── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ── Router ────────────────────────────────────────────────────────────────
router = APIRouter()


# ── Register ──────────────────────────────────────────────────────────────
@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
@limiter.limit("3/minute")
async def register(request: Request, body: RegisterRequest):
    """
    Creates a new user account via Supabase Auth.
    Returns JWT tokens immediately after registration.
    No email confirmation required in development (configured in Supabase dashboard).
    """
    try:
        response = supabase.auth.sign_up({
            "email": body.email,
            "password": body.password,
        })

        # Supabase returns a user object even if email confirmation
        # is pending — check session exists to confirm immediate access
        # When email confirmation is enabled Supabase returns
        # a user but no session until email is confirmed
        if not response.session:
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "requires_confirmation": True,
                    "email": body.email,
                    "message": "Please check your email to confirm your account",
                }
            )

        return AuthResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            user=AuthUserResponse(
                id=response.user.id,
                email=response.user.email,
            ),
        )

    except AuthApiError as e:
        # AuthApiError is raised by supabase-py for known API errors
        # e.g. email already registered, weak password etc.
        logger.warning(f"Registration failed for {body.email}: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        )


# ── Login ─────────────────────────────────────────────────────────────────
@router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Login with email and password",
)
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest):
    """
    Authenticates a user with email and password.
    Returns JWT access token and refresh token.
    Access token expires in 1 hour (configured in Supabase).
    Refresh token is long-lived and used to get new access tokens.
    """
    try:
        response = supabase.auth.sign_in_with_password({
            "email": body.email,
            "password": body.password,
        })

        if not response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        return AuthResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            user=AuthUserResponse(
                id=response.user.id,
                email=response.user.email,
            ),
        )

    except AuthApiError as e:
        # Log as warning not error — failed logins are expected events
        # not application errors
        logger.warning(f"Login failed for {body.email}: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )


# ── Refresh Token ─────────────────────────────────────────────────────────
@router.post(
    "/refresh",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
)
async def refresh_token(body: RefreshRequest):
    """
    Exchanges a refresh token for a new access token.
    Called automatically by the frontend when access token expires.
    Refresh tokens are rotated on each use — old token is invalidated.
    """
    try:
        response = supabase.auth.refresh_session(body.refresh_token)

        if not response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

        return AuthResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            user=AuthUserResponse(
                id=response.user.id,
                email=response.user.email,
            ),
        )

    except AuthApiError as e:
        logger.warning(f"Token refresh failed: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )


# ── Logout ────────────────────────────────────────────────────────────────
@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Logout current user",
)
async def logout(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Invalidates the current session on Supabase Auth.
    Frontend must also clear stored tokens after calling this.
    Requires a valid access token — cannot logout an already
    expired session (frontend should just clear tokens in that case).
    """
    try:
        supabase.auth.sign_out()
        logger.info(f"User {current_user.user_id} logged out")
        return MessageResponse(message="Successfully logged out")

    except AuthApiError as e:
        logger.warning(f"Logout failed for {current_user.user_id}: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        )


# ── Me ────────────────────────────────────────────────────────────────────
@router.get(
    "/me",
    response_model=MeResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user",
)
async def me(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns the current authenticated user info.
    Data is extracted directly from the JWT — no DB query needed.
    Used by frontend on app load to verify token is still valid
    and get the current user identity.
    """
    return MeResponse(
        id=current_user.user_id,
        email=current_user.email,
        role=current_user.role,
    )


# ── Delete Account ────────────────────────────────────────────────────────
@router.delete(
    "/account",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete the authenticated user's account and all their data",
)
async def delete_account(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Deletes the caller's own account. Irreversible.

    The Settings screen already offered this and called this route, which
    did not exist, so the button always failed (defect 15). Deleting the
    Auth user cascades to every row the user owns; see delete_auth_user.

    Only ever the caller's own id, taken from the verified token — never
    from the request — so no request can delete someone else's account.
    """
    try:
        delete_auth_user(current_user.user_id)
    except AuthApiError as e:
        logger.error(f"Account deletion failed for {current_user.user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not delete the account. Nothing was removed; try again.",
        )
    logger.info(f"Deleted account {current_user.user_id}")
