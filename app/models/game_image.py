"""Uploaded images for a game's catalog page (Cloudinary or dev-local)."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer
from sqlmodel import Field, SQLModel


class GameImage(SQLModel, table=True):
    """One image belonging to a game.

    `public_id` is the Cloudinary asset id, needed to delete the asset
    remotely (Fase 4). In dev-local fallback mode it is prefixed with
    "dev:" so it is obvious in the database that the file lives on local
    disk, not on Cloudinary — see the "Contrato del fallback" in the plan.
    """

    __tablename__ = "game_images"

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(
        sa_column=Column(Integer, ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    )
    url: str = Field(max_length=1000)
    public_id: str = Field(max_length=300)
    is_cover: bool = Field(default=False)
    sort_order: int = Field(default=0)
