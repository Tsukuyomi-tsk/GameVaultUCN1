"""The single canonical definition of "is this offer live right now".

Introduced in Fase 1 (ahead of the catalog/checkout phases) because the
seeder needs correct, non-duplicated pricing to produce trustworthy demo
data. Every place in the app that needs an effective price — catalog
(Fase 3), cart and checkout (Fase 5), and this seeder — must call these
helpers, never re-derive the condition inline. A copy that forgets
`is_active` would apply discounts an admin explicitly turned off.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, select

from app.models.offer import Offer
from app.repositories.base import BaseRepository


def active_offer_clause(now: datetime) -> ColumnElement[bool]:
    """SQLAlchemy boolean clause: is an Offer row live at `now`?

    Vigency requires all three: the admin's manual switch is on, and `now`
    falls inside [starts_at, ends_at].
    """
    return Offer.is_active.is_(True) & (Offer.starts_at <= now) & (Offer.ends_at >= now)


def get_active_offer_for_game(session: Session, game_id: int, now: datetime) -> Offer | None:
    """The live offer for a game, if any.

    Offer creation (Fase 4) is responsible for not letting two offers on
    the same game overlap in time — this just returns whichever one query
    finds, since at most one should ever match.
    """
    statement = select(Offer).where(Offer.game_id == game_id, active_offer_clause(now))
    return session.exec(statement).first()


def compute_effective_price(base_price: Decimal, offer: Offer | None) -> tuple[Decimal, int]:
    """The (final_price, discount_percent) for a game given its possibly-None
    active offer, rounded to 2 decimals like any other currency amount.
    """
    if offer is None:
        return base_price, 0
    discount = (base_price * offer.discount_percent) / Decimal(100)
    final_price = (base_price - discount).quantize(Decimal("0.01"))
    return final_price, offer.discount_percent


class OfferRepository(BaseRepository[Offer]):
    """Admin CRUD for offers (Fase 4). `Offer` has no `deleted_at` — nothing
    else references an offer by id, so removing one is a genuine hard
    delete via BaseRepository.delete(), not a soft one.
    """

    model = Offer

    def list_all(self, *, game_id: int | None = None) -> list[Offer]:
        statement = select(Offer).order_by(Offer.starts_at.desc())
        if game_id is not None:
            statement = statement.where(Offer.game_id == game_id)
        return list(self.session.exec(statement).all())

    def list_overlapping_active(
        self,
        *,
        game_id: int,
        starts_at: datetime,
        ends_at: datetime,
        exclude_offer_id: int | None = None,
    ) -> list[Offer]:
        """Active offers on this game whose [starts_at, ends_at] window
        intersects the given one — the check admin create/update calls
        before saving, so at most one offer is ever live for a game at a
        time (the invariant active_offer_clause/get_active_offer_for_game
        already assume). Only `is_active` offers count: two disabled
        offers overlapping in date range can't both apply a discount, so
        there's nothing to protect against.
        """
        statement = select(Offer).where(
            Offer.game_id == game_id,
            Offer.is_active.is_(True),
            Offer.starts_at <= ends_at,
            Offer.ends_at >= starts_at,
        )
        if exclude_offer_id is not None:
            statement = statement.where(Offer.id != exclude_offer_id)
        return list(self.session.exec(statement).all())
