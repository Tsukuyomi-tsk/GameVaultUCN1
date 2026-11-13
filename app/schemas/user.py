"""Pydantic schemas for User — the shape returned at the API boundary.

The table model (app.models.user.User) is never returned directly from a
router: it carries `password_hash` and other fields the API must not leak.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.enums import UserRole


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_verified: bool
    created_at: datetime
