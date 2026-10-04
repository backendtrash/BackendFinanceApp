from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional


class RegisterRequest(BaseModel):
    """
    Request body for POST /api/v1/auth/register
    EmailStr validates email format automatically via pydantic
    """
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """
        Enforces password rules at API level before hitting Supabase.
        Supabase also enforces minimum length but we want
        a clear error message from our API not a generic Supabase error.
        """
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter")
        symbols = set("!@#$%^&*()_+-=[]{}|;:,.<>?/~`")
        if not any(c in symbols for c in v):
            raise ValueError("Password must contain at least one symbol (!@#$%^&*...)")
        return v


class LoginRequest(BaseModel):
    """
    Request body for POST /api/v1/auth/login
    """
    email: EmailStr
    password: str


class AuthUserResponse(BaseModel):
    """
    Represents the authenticated user returned after login/register.
    Only exposes safe fields — never return raw Supabase user object.
    """
    id: str
    email: str


class AuthResponse(BaseModel):
    """
    Full response returned on successful login or register.
    Contains the JWT tokens and user info the frontend needs.
    """
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: AuthUserResponse


class RefreshRequest(BaseModel):
    """
    Request body for POST /api/v1/auth/refresh
    Frontend sends this when access_token is expired.
    """
    refresh_token: str


class MessageResponse(BaseModel):
    """
    Generic response for operations that only need a status message.
    Used by logout and other simple confirmation endpoints.
    """
    message: str


class MeResponse(BaseModel):
    """
    Response for GET /api/v1/auth/me
    Returns current authenticated user info extracted from JWT.
    No DB query needed — all data comes from the token itself.
    """
    id: str
    email: str
    role: str