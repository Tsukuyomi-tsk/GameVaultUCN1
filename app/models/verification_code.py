"""Email verification codes issued during registration.

Only one code is ever "live" per user: issuing a new one invalidates every
previous unconsumed code in the same transaction. That invariant is
enforced by services/auth_service.py (Fase 2), not by this model — the
model only stores the state the service needs to check.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, ForeignKey, Integer
from sqlmodel import Field, SQLModel

from app.core.time import utcnow


class VerificationCode(SQLModel, table=True):
    """A hashed, single-use code sent by email to verify an account.

    The code itself is never stored in plain text — only `code_hash`.
    """

    __tablename__ = "verification_codes"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    )
    code_hash: str = Field(max_length=255)
    expires_at: datetime
    consumed_at: datetime | None = Field(default=None)
    invalidated_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
