"""Request/response schemas for the admin user management endpoints
(Fase 4). Separate from schemas/user.py's UserRead (the public /auth/me
shape), which deliberately omits suspension fields a shopper never needs.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole


class AdminUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_verified: bool
    is_suspended: bool
    suspended_at: datetime | None
    suspension_reason: str | None
    created_at: datetime


class UserPage(BaseModel):
    items: list[AdminUserRead]
    page: int
    size: int
    total: int
    pages: int


class SuspendUserRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
