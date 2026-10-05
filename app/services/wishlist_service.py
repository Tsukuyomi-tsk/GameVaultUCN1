"""Business logic for the personal wishlist (Fase 6).

Adding a game that is already on the list is a 409 (ConflictError), the same
answer a duplicate review gets; removing one that isn't there is a 404.
Concurrent duplicate adds are settled by WishlistItem's UniqueConstraint:
the loser's IntegrityError becomes that same 409.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.time import utcnow
from app.models import Game, User, WishlistItem
from app.repositories.game_repository import GameRepository
from app.repositories.offer_repository import compute_effective_price, get_active_offer_for_game
from app.repositories.wishlist_repository import WishlistRepository
from app.schemas.wishlist import WishlistItemRead


def _to_read(session: Session, item: WishlistItem, game: Game) -> WishlistItemRead:
    # Mismo calculo de precio que el catalogo, el carrito y el checkout:
    # nunca se re-deriva el descuento a mano.
    offer = get_active_offer_for_game(session, game.id, utcnow())
    final_price, discount_percent = compute_effective_price(game.base_price, offer)
    return WishlistItemRead(
        game_id=game.id,
        title=game.title,
        slug=game.slug,
        platform=game.platform,
        base_price=game.base_price,
        final_price=final_price,
        discount_percent=discount_percent,
        has_active_offer=offer is not None,
        added_at=item.created_at,
    )


def list_wishlist(session: Session, *, user: User) -> list[WishlistItemRead]:
    rows = WishlistRepository(session).list_for_user_detailed(user.id)
    return [_to_read(session, item, game) for item, game in rows]


def add_to_wishlist(session: Session, *, user: User, game_id: int) -> WishlistItemRead:
    games = GameRepository(session)
    wishlist = WishlistRepository(session)

    # games.get() ya excluye los juegos soft-deleted; is_active se chequea
    # aparte (igual que el carrito). No se puede desear un juego que el
    # catalogo publico no muestra.
    game = games.get(game_id)
    if game is None or not game.is_active:
        raise NotFoundError("Juego no encontrado.")

    if wishlist.get_by_user_and_game(user_id=user.id, game_id=game.id) is not None:
        raise ConflictError("Este juego ya esta en tu wishlist.")

    # El IntegrityError de una carrera concurrente salta en el flush() que
    # hace wishlist.add(), no recien en el commit(): el try envuelve ambos.
    try:
        item = wishlist.add(WishlistItem(user_id=user.id, game_id=game.id))
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ConflictError("Este juego ya esta en tu wishlist.") from None
    session.refresh(item)
    return _to_read(session, item, game)


def remove_from_wishlist(session: Session, *, user: User, game_id: int) -> None:
    wishlist = WishlistRepository(session)
    # Se busca por (user_id del JWT, game_id): un usuario solo puede quitar
    # items de SU propia wishlist — no existe forma de apuntar a la de otro.
    item = wishlist.get_by_user_and_game(user_id=user.id, game_id=game_id)
    if item is None:
        raise NotFoundError("Ese juego no esta en tu wishlist.")
    # Hard delete: WishlistItem no tiene deleted_at (ver el repositorio).
    wishlist.delete(item)
    session.commit()
