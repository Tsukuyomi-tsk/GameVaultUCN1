"""A single game inside a cart — digital goods, so no quantity field."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlmodel import Field, SQLModel


class CartItem(SQLModel, table=True):
    """One game added to a cart.

    Re-adding the same game is idempotent at the service layer (Fase 5): a
    UniqueConstraint violation there is treated as a no-op, not an error.
    """

    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("cart_id", "game_id"),)

    id: int | None = Field(default=None, primary_key=True)
    cart_id: int = Field(
        sa_column=Column(Integer, ForeignKey("carts.id", ondelete="CASCADE"), nullable=False)
    )
    game_id: int = Field(
        sa_column=Column(Integer, ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    )
