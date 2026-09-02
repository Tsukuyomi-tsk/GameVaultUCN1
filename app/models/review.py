"""A user's rating and comment on a game they own.

One review per user per game; soft-deleted, never hard-deleted.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.time import utcnow


class Review(SQLModel, table=True):
    """A rating (1-5) plus an optional comment, tied to library ownership.

    Eligibility (must own the game) is enforced by services/review_service.py
    (Fase 6), not by a database constraint — SQLite cannot declaratively
    express "a row must exist in another table".
    """

    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("user_id", "game_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    )
    game_id: int = Field(
        sa_column=Column(Integer, ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    )
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)
    deleted_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
