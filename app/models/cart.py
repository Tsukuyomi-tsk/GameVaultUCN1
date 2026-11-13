"""Shopping cart — works for both guests and authenticated users."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer
from sqlmodel import Field, SQLModel

from app.core.time import utcnow


class Cart(SQLModel, table=True):
    """One cart per user (enforced by the unique `user_id`) or one per guest
    session (identified by `session_token`).

    Exactly one of `user_id` / `session_token` must be set — enforced by a
    CheckConstraint, not just at the service layer, so no cart can ever end
    up unreachable by either the session or the account. In SQLite, NULLs
    never collide with a unique constraint, so any number of guest carts
    (user_id NULL) coexist fine alongside the one-per-user constraint.
    """

    __tablename__ = "carts"
    __table_args__ = (
        CheckConstraint(
            "user_id IS NOT NULL OR session_token IS NOT NULL",
            name="owner_present",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = Field(
        default=None,
        sa_column=Column(
            Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=True
        ),
    )
    session_token: str | None = Field(default=None, unique=True, max_length=64, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
