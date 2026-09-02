"""A game the user owns.

Created at checkout; drives review eligibility (Fase 6) and duplicate
purchase prevention (Fase 5).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.time import utcnow


class LibraryItem(SQLModel, table=True):
    """Ownership record: this user owns this game, acquired via this order.

    All three foreign keys are ON DELETE RESTRICT — ownership is proof of a
    real transaction and must never silently disappear if a related row is
    removed elsewhere.
    """

    __tablename__ = "library_items"
    __table_args__ = (UniqueConstraint("user_id", "game_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    )
    game_id: int = Field(
        sa_column=Column(Integer, ForeignKey("games.id", ondelete="RESTRICT"), nullable=False)
    )
    order_id: int = Field(
        sa_column=Column(Integer, ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False)
    )
    acquired_at: datetime = Field(default_factory=utcnow)
