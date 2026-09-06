"""Business logic for the admin popularity panel (Fase 4). Thin — the
aggregation itself lives in stats_repository.py; this only owns the
default `limit` and hands both lists back together.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session

from app.repositories.stats_repository import PopularityRow, StatsRepository


def get_popularity(
    session: Session, *, date_from: datetime | None, date_to: datetime | None, limit: int
) -> tuple[list[PopularityRow], list[PopularityRow]]:
    stats = StatsRepository(session)
    top_wishlisted = stats.top_wishlisted(date_from=date_from, date_to=date_to, limit=limit)
    top_purchased = stats.top_purchased(date_from=date_from, date_to=date_to, limit=limit)
    return top_wishlisted, top_purchased
