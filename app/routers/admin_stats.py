"""Admin popularity stats (Fase 4): top wishlisted, top purchased.

`from`/`to` are the query param names the plan specifies; `from` is a
Python keyword, so the function parameters are `date_from`/`date_to`
aliased back to `from`/`to` for the actual query string.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import AdminUser
from app.schemas.stats import PopularityEntry, PopularityStats
from app.services import admin_stats_service

router = APIRouter(prefix="/admin/stats", tags=["admin-stats"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/popularity", response_model=PopularityStats)
def get_popularity(
    session: SessionDep,
    _admin: AdminUser,
    date_from: Annotated[datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> PopularityStats:
    top_wishlisted, top_purchased = admin_stats_service.get_popularity(
        session, date_from=date_from, date_to=date_to, limit=limit
    )
    return PopularityStats(
        date_from=date_from,
        date_to=date_to,
        top_wishlisted=[
            PopularityEntry(game_id=r.game_id, title=r.title, slug=r.slug, count=r.count)
            for r in top_wishlisted
        ],
        top_purchased=[
            PopularityEntry(game_id=r.game_id, title=r.title, slug=r.slug, count=r.count)
            for r in top_purchased
        ],
    )
