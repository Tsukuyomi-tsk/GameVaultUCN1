"""Pydantic schema for Category — the public catalog's read-only shape."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None
