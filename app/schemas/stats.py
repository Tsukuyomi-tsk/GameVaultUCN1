"""Response schema for GET /admin/stats/popularity (Fase 4)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PopularityEntry(BaseModel):
    game_id: int
    title: str
    slug: str
    count: int


class PopularityStats(BaseModel):
    date_from: datetime | None
    date_to: datetime | None
    top_wishlisted: list[PopularityEntry]
    top_purchased: list[PopularityEntry]
