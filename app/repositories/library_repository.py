"""Data access for LibraryItem — ownership records created at checkout
(Fase 5), read back for GET /me/library and for the "already owned" check
both the cart and checkout perform.
"""

from __future__ import annotations

from sqlmodel import select

from app.models import Game, LibraryItem, Order
from app.repositories.base import BaseRepository


class LibraryRepository(BaseRepository[LibraryItem]):
    # Le indica a BaseRepository sobre que tabla trabajan get()/add()/
    # delete() heredados: "library_items".
    model = LibraryItem

    def owns(self, *, user_id: int, game_id: int) -> bool:
        # select(LibraryItem.id) (no select(LibraryItem) completo) trae solo
        # la columna id — mas liviano, porque a este metodo solo le importa
        # si EXISTE la fila, no su contenido completo.
        statement = select(LibraryItem.id).where(
            LibraryItem.user_id == user_id, LibraryItem.game_id == game_id
        )
        # .first() is not None: True si aparecio al menos una fila (el
        # usuario ya posee este juego), False si la consulta no trajo nada.
        return self.session.exec(statement).first() is not None

    def list_for_user_detailed(self, user_id: int) -> list[tuple[LibraryItem, Game, Order]]:
        """Joined to Game and Order so the router never has to look either
        up separately. Both joins are safe as inner joins: LibraryItem's
        game_id and order_id are ON DELETE RESTRICT (see library_item.py),
        so a row here always has a live Game and Order.
        """
        # select(LibraryItem, Game, Order) trae las TRES tablas en cada
        # fila, en una sola consulta — asi GET /me/library nunca necesita
        # una consulta separada por cada juego para saber su titulo/slug o
        # el order_code de la orden que lo origino.
        statement = (
            select(LibraryItem, Game, Order)
            .join(Game, Game.id == LibraryItem.game_id)
            .join(Order, Order.id == LibraryItem.order_id)
            .where(LibraryItem.user_id == user_id)
            # Los juegos adquiridos mas recientemente aparecen primero.
            .order_by(LibraryItem.acquired_at.desc())
        )
        return list(self.session.exec(statement).all())
