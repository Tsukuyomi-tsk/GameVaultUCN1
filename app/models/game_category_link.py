"""Many-to-many association between Game and Category."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer
from sqlmodel import Field, SQLModel


class GameCategoryLink(SQLModel, table=True):
    """Pure association row — no attributes of its own."""

    __tablename__ = "game_category_links"

    game_id: int = Field(
        sa_column=Column(Integer, ForeignKey("games.id", ondelete="CASCADE"), primary_key=True)
    )
    category_id: int = Field(
        sa_column=Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True)
    )
