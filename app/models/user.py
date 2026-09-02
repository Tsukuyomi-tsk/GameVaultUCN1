"""User model — identity, role, verification and suspension state."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column
from sqlmodel import Field, SQLModel

from app.core.time import utcnow
from app.models.enums import UserRole
from app.models.sa_enum import str_enum_column


class User(SQLModel, table=True):
    """A registered account: either a shopper or an administrator.

    `verification_attempts` and `verification_blocked_until` live here, not
    on VerificationCode — if the counter lived on the code, requesting a new
    one would reset it and the max-attempts limit would be trivial to
    bypass (see app/models/verification_code.py).

    Suspension does not revoke already-issued JWTs directly (TokenBlacklist
    only tracks explicit logouts, see token_blacklist.py). Instead,
    `is_suspended` is re-checked against this row on every authenticated
    request (app/core/dependencies.py), which is what actually makes a
    suspension take effect on tokens issued before it.
    """

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=255)
    password_hash: str
    full_name: str = Field(max_length=255)
    role: UserRole = Field(
        default=UserRole.USER,
        sa_column=Column(str_enum_column(UserRole), nullable=False),
    )

    is_verified: bool = Field(default=False)
    is_suspended: bool = Field(default=False)
    suspended_at: datetime | None = Field(default=None)
    suspension_reason: str | None = Field(default=None, max_length=500)

    verification_attempts: int = Field(default=0)
    verification_blocked_until: datetime | None = Field(default=None)

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
