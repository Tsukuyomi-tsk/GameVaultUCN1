"""Data access for WishlistItem (Fase 6) — the one place that queries the
`wishlist_items` table.

WishlistItem has no `deleted_at`: removing a game from a wishlist is a real
DELETE (the row has no value of its own once removed — see
BaseRepository.delete), unlike Review, which keeps a soft-deleted trail.
"""

from __future__ import annotations

from sqlmodel import select

from app.models import Game, WishlistItem
from app.repositories.base import BaseRepository


class WishlistRepository(BaseRepository[WishlistItem]):
    # Le indica a BaseRepository sobre que tabla trabajan get()/add()/
    # delete() heredados: "wishlist_items".
    model = WishlistItem

    def get_by_user_and_game(self, *, user_id: int, game_id: int) -> WishlistItem | None:
        # Busca por la MISMA combinacion que protege el UniqueConstraint del
        # modelo (user_id + game_id): es lo que permite responder "ya esta
        # en tu wishlist" antes de intentar un INSERT duplicado.
        statement = select(WishlistItem).where(
            WishlistItem.user_id == user_id, WishlistItem.game_id == game_id
        )
        return self.session.exec(statement).first()

    def list_for_user_detailed(self, user_id: int) -> list[tuple[WishlistItem, Game]]:
        """Joined to Game so the service never looks each game up separately.
        Games that are inactive or soft-deleted are left out: a wishlist
        shouldn't advertise something the public catalog no longer shows.
        """
        # select(WishlistItem, Game) trae las dos tablas en cada fila, en
        # una sola consulta.
        statement = (
            select(WishlistItem, Game)
            .join(Game, Game.id == WishlistItem.game_id)
            .where(
                WishlistItem.user_id == user_id,
                # Mismo criterio de "juego publico" que el catalogo: activo
                # y no soft-deleted.
                Game.is_active.is_(True),
                Game.deleted_at.is_(None),
            )
            # Los agregados mas recientemente aparecen primero.
            .order_by(WishlistItem.created_at.desc(), WishlistItem.id.desc())
        )
        return list(self.session.exec(statement).all())
