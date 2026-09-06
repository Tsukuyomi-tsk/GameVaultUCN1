"""Aggregation queries for the admin popularity panel (Fase 4). Not a
BaseRepository subclass — there's no single model this owns, it's a pure
read-side aggregate over WishlistItem/OrderItem joined to Game.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import Game, Order, OrderItem, WishlistItem
from app.models.enums import OrderStatus


@dataclass
class PopularityRow:
    game_id: int
    title: str
    slug: str
    count: int


class StatsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def top_wishlisted(
        self, *, date_from: datetime | None, date_to: datetime | None, limit: int
    ) -> list[PopularityRow]:
        statement = (
            select(Game.id, Game.title, Game.slug, func.count(WishlistItem.id).label("count"))
            .join(WishlistItem, WishlistItem.game_id == Game.id)
            .group_by(Game.id, Game.title, Game.slug)
            .order_by(func.count(WishlistItem.id).desc())
            .limit(limit)
        )
        if date_from is not None:
            statement = statement.where(WishlistItem.created_at >= date_from)
        if date_to is not None:
            statement = statement.where(WishlistItem.created_at <= date_to)

        rows = self.session.exec(statement).all()
        return [PopularityRow(game_id=r[0], title=r[1], slug=r[2], count=r[3]) for r in rows]

    def top_purchased(
        self, *, date_from: datetime | None, date_to: datetime | None, limit: int
    ) -> list[PopularityRow]:
        """Counts OrderItem rows from PAID orders only — a game bought
        twice by two different orders counts twice, matching "units sold",
        not "distinct buyers".
        """
        statement = (
            select(Game.id, Game.title, Game.slug, func.count(OrderItem.id).label("count"))
            .join(OrderItem, OrderItem.game_id == Game.id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.status == OrderStatus.PAID)
            .group_by(Game.id, Game.title, Game.slug)
            .order_by(func.count(OrderItem.id).desc())
            .limit(limit)
        )
        if date_from is not None:
            statement = statement.where(Order.paid_at >= date_from)
        if date_to is not None:
            statement = statement.where(Order.paid_at <= date_to)

        rows = self.session.exec(statement).all()
        return [PopularityRow(game_id=r[0], title=r[1], slug=r[2], count=r[3]) for r in rows]
