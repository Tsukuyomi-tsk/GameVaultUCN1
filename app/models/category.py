"""Product category / genre used to classify games."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel


class Category(SQLModel, table=True):
    """A game genre/category. Soft-deleted, never hard-deleted.

    Games keep referencing a deleted category through GameCategoryLink so
    historical catalog data stays coherent; the public catalog simply
    filters `deleted_at IS NULL` when listing categories.
    """

    __tablename__ = "categories"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, max_length=100)
    slug: str = Field(unique=True, max_length=120, index=True)
    description: str | None = Field(default=None, max_length=500)
    deleted_at: datetime | None = Field(default=None)
