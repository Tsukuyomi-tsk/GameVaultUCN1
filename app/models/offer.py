"""Time-bound percentage discount applied to a game."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, ForeignKey, Integer
from sqlmodel import Field, SQLModel


class Offer(SQLModel, table=True):
    """A discount window for one game.

    Vigency is NOT just "now between starts_at and ends_at": it also
    requires `is_active = True`, the admin's manual on/off switch. The
    single source of truth for that predicate is
    app.repositories.offer_repository.active_offer_clause(now) — every
    query that needs "is this offer live" must call it, never re-derive the
    condition inline.
    """

    __tablename__ = "offers"

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(
        sa_column=Column(Integer, ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    )
    discount_percent: int = Field(ge=1, le=90)
    starts_at: datetime
    ends_at: datetime
    is_active: bool = Field(default=True)
