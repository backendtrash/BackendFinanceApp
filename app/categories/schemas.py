from pydantic import BaseModel, field_validator
from typing import Optional
from uuid import UUID
from enum import Enum


class TransactionType(str, Enum):
    """
    Mirrors the transaction_type ENUM defined in PostgreSQL.
    Using Python Enum ensures only valid values are accepted
    at the API level before hitting the database.
    """
    expense = "expense"
    income  = "income"


class CategoryCreate(BaseModel):
    """
    DTO for POST /api/v1/categories
    user_id is NOT included — injected from JWT in service layer.
    System categories (user_id=NULL) cannot be created via API.
    """
    name:  str
    color: str            = "#6366F1"
    icon:  str            = "tag"
    type:  TransactionType = TransactionType.expense

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """
        Strips whitespace and enforces length limits.
        Matches VARCHAR(50) constraint in DB.
        """
        v = v.strip()
        if not v:
            raise ValueError("Category name cannot be empty")
        if len(v) > 50:
            raise ValueError("Category name cannot exceed 50 characters")
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        """
        Validates hex color format #RRGGBB.
        Enforces 7-char limit matching VARCHAR(7) in DB.
        """
        v = v.strip()
        if not v.startswith("#") or len(v) != 7:
            raise ValueError("Color must be a valid hex color e.g. #FF5733")
        try:
            int(v[1:], 16)
        except ValueError:
            raise ValueError("Color must be a valid hex color e.g. #FF5733")
        return v.upper()

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Icon cannot be empty")
        if len(v) > 50:
            raise ValueError("Icon name cannot exceed 50 characters")
        return v.lower()


class CategoryUpdate(BaseModel):
    """
    DTO for PATCH /api/v1/categories/{id}
    All fields optional — partial update semantics.
    type cannot be changed after creation — would break
    existing expenses/earnings linked to this category.
    """
    name:  Optional[str] = None
    color: Optional[str] = None
    icon:  Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Category name cannot be empty")
            if len(v) > 50:
                raise ValueError("Category name cannot exceed 50 characters")
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v.startswith("#") or len(v) != 7:
                raise ValueError("Color must be a valid hex color e.g. #FF5733")
            try:
                int(v[1:], 16)
            except ValueError:
                raise ValueError("Color must be a valid hex color e.g. #FF5733")
            return v.upper()
        return v

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Icon cannot be empty")
            if len(v) > 50:
                raise ValueError("Icon name cannot exceed 50 characters")
            return v.lower()
        return v


class CategoryResponse(BaseModel):
    """
    DTO for all category responses.
    is_system flag tells frontend whether category is
    editable/deletable (False) or read-only (True).
    """
    id:         UUID
    user_id:    Optional[UUID]
    name:       str
    color:      str
    icon:       str
    type:       TransactionType
    is_system:  bool
    created_at: str

    class Config:
        from_attributes = True