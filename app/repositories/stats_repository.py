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


# @dataclass genera automaticamente __init__, __repr__, etc. a partir de
# los campos declarados abajo — es una forma liviana de definir "un
# resultado con estos 4 campos" sin escribir una clase entera a mano.
# No es un modelo de tabla (no tiene table=True): nunca se guarda en la
# base de datos, solo se usa para devolver el resultado de una consulta
# agregada de forma ordenada.
@dataclass
class PopularityRow:
    game_id: int
    title: str
    slug: str
    count: int


class StatsRepository:
    # Esta clase NO hereda de BaseRepository porque no representa "la
    # tabla X" — combina varias tablas (Game, WishlistItem, OrderItem,
    # Order) en consultas de agregacion. Por eso arma su propio __init__
    # en vez de reutilizar el de BaseRepository.
    def __init__(self, session: Session) -> None:
        self.session = session

    def top_wishlisted(
        self, *, date_from: datetime | None, date_to: datetime | None, limit: int
    ) -> list[PopularityRow]:
        statement = (
            # Selecciona 4 columnas sueltas (no el objeto Game completo):
            # id/title/slug del juego, mas una columna calculada "count"
            # que cuenta cuantas filas de wishlist_items tiene cada juego.
            select(Game.id, Game.title, Game.slug, func.count(WishlistItem.id).label("count"))
            # INNER JOIN entre games y wishlist_items: solo entran los
            # juegos que tienen AL MENOS una fila en la wishlist de alguien
            # (si nadie lo deseo, no aparece en el resultado).
            .join(WishlistItem, WishlistItem.game_id == Game.id)
            # GROUP BY es obligatorio junto con func.count(): agrupa todas
            # las filas de wishlist_items por juego antes de contarlas.
            .group_by(Game.id, Game.title, Game.slug)
            # Ordena de mayor a menor cantidad de "deseos" — el juego mas
            # deseado primero.
            .order_by(func.count(WishlistItem.id).desc())
            # Se queda solo con los primeros `limit` resultados (el "top N").
            .limit(limit)
        )
        # Filtros de fecha OPCIONALES: si el llamador paso date_from/
        # date_to, se agrega una condicion WHERE extra sobre la fecha en
        # que se agrego el juego a la wishlist. Si son None, no se filtra
        # por fecha en absoluto (se cuentan todos los deseos, de siempre).
        if date_from is not None:
            statement = statement.where(WishlistItem.created_at >= date_from)
        if date_to is not None:
            statement = statement.where(WishlistItem.created_at <= date_to)

        # Ejecuta la consulta. Como el SELECT trae 4 columnas sueltas (no
        # un objeto Game completo), cada fila del resultado es una tupla
        # tipo (id, title, slug, count) accesible por indice.
        rows = self.session.exec(statement).all()
        # Convierte cada tupla cruda en un PopularityRow, mas comodo y
        # legible de usar en el resto de la app que una tupla posicional.
        return [PopularityRow(game_id=r[0], title=r[1], slug=r[2], count=r[3]) for r in rows]

    def top_purchased(
        self, *, date_from: datetime | None, date_to: datetime | None, limit: int
    ) -> list[PopularityRow]:
        """Counts OrderItem rows from PAID orders only — a game bought
        twice by two different orders counts twice, matching "units sold",
        not "distinct buyers".
        """
        statement = (
            # Igual que arriba, pero contando order_items en vez de
            # wishlist_items — "cuantas veces se compro cada juego".
            select(Game.id, Game.title, Game.slug, func.count(OrderItem.id).label("count"))
            # Primer join: de Game a OrderItem (juegos que aparecen en
            # algun detalle de compra).
            .join(OrderItem, OrderItem.game_id == Game.id)
            # Segundo join: de OrderItem a Order, porque el estado de la
            # compra (pagada o no) vive en la tabla Order, no en OrderItem.
            .join(Order, Order.id == OrderItem.order_id)
            # Solo cuentan las compras efectivamente pagadas — en este
            # proyecto el checkout es sincronico y siempre deja la orden
            # en PAID, pero el filtro queda explicito igual, por claridad
            # y por si en el futuro se agregan otros estados.
            .where(Order.status == OrderStatus.PAID)
            .group_by(Game.id, Game.title, Game.slug)
            .order_by(func.count(OrderItem.id).desc())
            .limit(limit)
        )
        # Igual que en top_wishlisted, pero el filtro de fecha aca se
        # aplica sobre CUANDO SE PAGO la orden (Order.paid_at), no sobre
        # cuando se agrego un item a una wishlist.
        if date_from is not None:
            statement = statement.where(Order.paid_at >= date_from)
        if date_to is not None:
            statement = statement.where(Order.paid_at <= date_to)

        rows = self.session.exec(statement).all()
        return [PopularityRow(game_id=r[0], title=r[1], slug=r[2], count=r[3]) for r in rows]
