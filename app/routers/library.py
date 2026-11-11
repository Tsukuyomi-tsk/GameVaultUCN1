"""GET /me/library (Fase 5) — the games the logged-in user owns."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import CurrentUser
from app.schemas.errors import errors
from app.schemas.library import LibraryItemRead
from app.services import order_service

router = APIRouter(tags=["library"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get(
    "/me/library",
    response_model=list[LibraryItemRead],
    summary="Ver mi biblioteca",
    description="Los juegos que ya compraste, con la fecha y el codigo de la orden de compra.",
    responses=errors(401, 403),
)
def get_my_library(session: SessionDep, current_user: CurrentUser) -> list[LibraryItemRead]:
    # Cada fila viene como (LibraryItem, Game, Order) ya unidos — ver
    # LibraryRepository.list_for_user_detailed — asi que aca solo queda
    # tomar el campo que corresponde de cada uno para armar la respuesta.
    rows = order_service.list_library(session, user_id=current_user.id)
    return [
        LibraryItemRead(
            game_id=game.id,
            title=game.title,
            slug=game.slug,
            platform=game.platform,
            acquired_at=item.acquired_at,
            order_code=order.order_code,
        )
        for item, game, order in rows
    ]
