"""Request/response schemas for the admin category CRUD (Fase 4)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

_SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=120, pattern=_SLUG_PATTERN)
    description: str | None = Field(default=None, max_length=500)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, min_length=1, max_length=120, pattern=_SLUG_PATTERN)
    description: str | None = Field(default=None, max_length=500)


class CategoryAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None
    deleted_at: datetime | None
