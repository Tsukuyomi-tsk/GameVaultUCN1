"""Frozen line item of a purchase.

This is the historical record of what was bought, independent of later
catalog changes.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Column, ForeignKey, Integer
from sqlmodel import Field, SQLModel


class OrderItem(SQLModel, table=True):
    """One purchased game, frozen at checkout time.

    `game_id` is nullable and ON DELETE SET NULL: if the referenced game is
    ever hard-deleted, only the catalog link degrades to NULL. The
    `*_snapshot` fields are what the order history actually displays, and
    they never change regardless of what happens to the catalog afterward.
    """

    __tablename__ = "order_items"

    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(
        sa_column=Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    )
    game_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("games.id", ondelete="SET NULL"), nullable=True),
    )
    title_snapshot: str = Field(max_length=255)
    slug_snapshot: str = Field(max_length=280)
    unit_price: Decimal = Field(max_digits=10, decimal_places=2)
    discount_percent: int = Field(default=0)
    final_price: Decimal = Field(max_digits=10, decimal_places=2)
