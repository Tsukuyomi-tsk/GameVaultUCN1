"""Explicitly revoked JWTs (logout). See app/core/dependencies.py.

This table does NOT enumerate every token ever issued — only the ones a
user chose to invalidate via logout. It cannot be used to revoke a user's
sessions in bulk (e.g. on suspension); that is handled by re-checking the
user's own state on every request instead. See app/models/user.py.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, ForeignKey, Integer
from sqlmodel import Field, SQLModel

from app.core.time import utcnow


class TokenBlacklist(SQLModel, table=True):
    """One row per revoked access token, keyed by its JWT id (`jti`)."""

    __tablename__ = "token_blacklist"

    id: int | None = Field(default=None, primary_key=True)
    jti: str = Field(unique=True, index=True, max_length=36)
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    )
    expires_at: datetime
    revoked_at: datetime = Field(default_factory=utcnow)
