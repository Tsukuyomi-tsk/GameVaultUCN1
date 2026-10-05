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

from sqlalchemy import update
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, select

from app.models.game import Game
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

    # Le indica a BaseRepository sobre que tabla trabajan get()/add()/
    # delete() heredados: "offers".
    model = Offer

    def list_all(self, *, game_id: int | None = None) -> list[Offer]:
        # Trae todas las ofertas, mas nuevas (por fecha de inicio) primero.
        statement = select(Offer).order_by(Offer.starts_at.desc())
        # game_id es un filtro opcional: si se paso, se limita el listado
        # a las ofertas de ESE juego; si no, se listan las ofertas de
        # todos los juegos.
        if game_id is not None:
            statement = statement.where(Offer.game_id == game_id)
        return list(self.session.exec(statement).all())

    def lock_game_offers(self, game_id: int) -> None:
        """Serialize every offer write for this game until the transaction
        ends.

        "No two active offers overlap" is a rule about SEVERAL rows, so no
        database constraint can enforce it: two admins creating the same
        window at once both ran list_overlapping_active, both saw nothing,
        and both inserted (8 simultaneous creations left 4 overlapping
        active offers). The check and the write must not interleave, so
        the caller takes this lock BEFORE checking. It is a no-op UPDATE of
        the game row: writing is what takes the lock — SQLite locks the
        whole database for the first writer and makes the rest wait for its
        commit; PostgreSQL would lock just this row. Whoever waits then
        runs its overlap check against data that already includes the
        winner's offer, and is rejected with a 409.
        """
        self.session.execute(
            update(Game).where(Game.id == game_id).values(id=Game.id),
            execution_options={"synchronize_session": False},
        )

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
            # Solo interesan las ofertas del mismo juego...
            Offer.game_id == game_id,
            # ...que esten activas (una oferta desactivada no compite por
            # el mismo motivo que dos ofertas inactivas tampoco compiten
            # entre si: si esta apagada, no aplica ningun descuento).
            Offer.is_active.is_(True),
            # Estas dos condiciones juntas son la formula clasica de
            # "interseccion de rangos de fechas": dos rangos [A,B] y [C,D]
            # se solapan si A <= D Y B >= C. Aca A/B son el rango nuevo que
            # se quiere guardar (starts_at/ends_at) y C/D es el rango de
            # cada oferta ya existente en la base de datos (Offer.starts_at/
            # Offer.ends_at) — si ambas condiciones se cumplen a la vez,
            # los dos rangos comparten al menos un instante en comun.
            Offer.starts_at <= ends_at,
            Offer.ends_at >= starts_at,
        )
        # Al actualizar una oferta existente, hay que excluir A LA MISMA
        # oferta de la comparacion — si no, siempre "chocaria contra si
        # misma" y ninguna edicion de fechas podria guardarse nunca.
        if exclude_offer_id is not None:
            statement = statement.where(Offer.id != exclude_offer_id)
        return list(self.session.exec(statement).all())
