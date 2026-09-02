"""A game saved to a user's personal wishlist."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.time import utcnow


class WishlistItem(SQLModel, table=True):
    """One (user, game) pair on a wishlist.

    Counted by the admin popularity panel (Fase 4) as "most wished-for"
    over a period.
    """

    __tablename__ = "wishlist_items"
    __table_args__ = (UniqueConstraint("user_id", "game_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    )
    game_id: int = Field(
        sa_column=Column(Integer, ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    )
    created_at: datetime = Field(default_factory=utcnow)
