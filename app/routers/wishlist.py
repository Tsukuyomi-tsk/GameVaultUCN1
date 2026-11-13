"""Wishlist endpoints (Fase 6). Every route requires CurrentUser, and the
wishlist is always resolved from the JWT's identity — no endpoint takes a
user id, so there is no way to read or edit someone else's list.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import CurrentUser
from app.schemas.errors import errors
from app.schemas.wishlist import WishlistItemRead
from app.services import wishlist_service

router = APIRouter(prefix="/me/wishlist", tags=["wishlist"])

SessionDep = Annotated[Session, Depends(get_session)]


# GET /me/wishlist — los juegos deseados del usuario logueado, con precio
# actual (oferta vigente incluida).
@router.get(
    "",
    response_model=list[WishlistItemRead],
    summary="Ver mi lista de deseados",
    description="Tus juegos deseados con el precio actual (oferta vigente incluida).",
    responses=errors(401, 403),
)
def get_my_wishlist(session: SessionDep, current_user: CurrentUser) -> list[WishlistItemRead]:
    return wishlist_service.list_wishlist(session, user=current_user)


# POST /me/wishlist/{game_id} — agrega un juego. 404 si no existe o no es
# publico, 409 si ya estaba en la lista.
@router.post(
    "/{game_id}",
    response_model=WishlistItemRead,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar un juego a mis deseados",
    description="Agrega el juego indicado a tu lista de deseados.",
    responses=errors(
        401,
        403,
        (404, "El juego no existe o no esta a la venta."),
        (409, "El juego ya esta en tu lista."),
        422,
    ),
)
def add_to_wishlist(
    game_id: int, session: SessionDep, current_user: CurrentUser
) -> WishlistItemRead:
    return wishlist_service.add_to_wishlist(session, user=current_user, game_id=game_id)


# DELETE /me/wishlist/{game_id} — quita un juego. 404 si no estaba.
@router.delete(
    "/{game_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar un juego de mis deseados",
    description="Quita el juego de tu lista de deseados.",
    responses=errors(401, 403, (404, "Ese juego no esta en tu lista."), 422),
)
def remove_from_wishlist(game_id: int, session: SessionDep, current_user: CurrentUser) -> None:
    wishlist_service.remove_from_wishlist(session, user=current_user, game_id=game_id)
