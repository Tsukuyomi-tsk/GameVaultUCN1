"""Game catalog entry."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.core.time import utcnow


class Game(SQLModel, table=True):
    """A title in the catalog.

    Soft-deleted via `deleted_at`; `is_active` is a separate, admin-controlled
    switch (a game can be inactive without being deleted, e.g. temporarily
    pulled from sale). The public catalog (Fase 3) requires both
    `is_active = True` and `deleted_at IS NULL`.
    """

    __tablename__ = "games"

    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(max_length=255, index=True)
    slug: str = Field(unique=True, max_length=280, index=True)
    description: str | None = Field(default=None, max_length=4000)
    developer: str | None = Field(default=None, max_length=255)
    publisher: str | None = Field(default=None, max_length=255)
    platform: str = Field(max_length=100, index=True)
    release_date: date | None = Field(default=None)
    base_price: Decimal = Field(max_digits=10, decimal_places=2)
    is_active: bool = Field(default=True)
    deleted_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
