"""Admin offer CRUD (Fase 4). Every route requires AdminUser. Overlap and
date-order validation live in app.services.admin_offer_service.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import AdminUser
from app.schemas.errors import ADMIN_RESPONSES, errors
from app.schemas.offer import OfferCreate, OfferRead, OfferUpdate
from app.services import admin_offer_service

router = APIRouter(prefix="/admin/offers", tags=["admin-offers"], responses=ADMIN_RESPONSES)

SessionDep = Annotated[Session, Depends(get_session)]


# GET /admin/offers — listado, con filtro opcional por juego.
@router.get(
    "",
    response_model=list[OfferRead],
    summary="Listar ofertas",
    description="Todas las ofertas; con `game_id` solo las de ese juego. Fechas en UTC.",
    responses=errors(422),
)
def list_offers(
    session: SessionDep, _admin: AdminUser, game_id: int | None = None
) -> list[OfferRead]:
    # game_id llega como query param opcional (?game_id=5) — si no se
    # manda, queda en None y el servicio no filtra por juego.
    offers = admin_offer_service.list_offers(session, game_id=game_id)
    return [OfferRead.model_validate(o) for o in offers]


# POST /admin/offers — crear una oferta nueva.
@router.post(
    "",
    response_model=OfferRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una oferta",
    description=(
        "Descuento de 1 a 90 % para un juego entre `starts_at` y `ends_at` (la fecha de fin "
        "debe ser posterior a la de inicio). Las fechas pueden llevar zona (`Z`, `-03:00`): se "
        "convierten a **UTC**. No puede solaparse con otra oferta del mismo juego."
    ),
    responses=errors(
        (404, "El juego no existe."),
        (409, "Se solapa con otra oferta del mismo juego."),
        (422, "Datos invalidos (porcentaje fuera de 1-90, o fin no posterior al inicio)."),
    ),
)
def create_offer(payload: OfferCreate, session: SessionDep, _admin: AdminUser) -> OfferRead:
    offer = admin_offer_service.create_offer(session, payload=payload)
    return OfferRead.model_validate(offer)


# PATCH /admin/offers/{offer_id} — actualizacion parcial.
@router.patch(
    "/{offer_id}",
    response_model=OfferRead,
    summary="Editar una oferta",
    description=(
        "Actualizacion parcial. Ningun campo acepta `null`. Si cambias una fecha, se vuelve a "
        "validar el orden y el solapamiento con la ventana resultante."
    ),
    responses=errors(
        (404, "La oferta no existe."),
        (409, "La ventana resultante se solapa con otra oferta del juego."),
        (422, "Datos invalidos, `null` en un campo, o fin no posterior al inicio."),
    ),
)
def update_offer(
    offer_id: int, payload: OfferUpdate, session: SessionDep, _admin: AdminUser
) -> OfferRead:
    offer = admin_offer_service.update_offer(session, offer_id=offer_id, payload=payload)
    return OfferRead.model_validate(offer)


# DELETE /admin/offers/{offer_id} — borrado FISICO (Offer no tiene soft
# delete, ver el comentario en admin_offer_service.delete_offer).
@router.delete(
    "/{offer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar una oferta",
    description="Borrado **fisico**: la oferta se elimina de verdad (no tiene borrado logico).",
    responses=errors((404, "La oferta no existe."), 422),
)
def delete_offer(offer_id: int, session: SessionDep, _admin: AdminUser) -> None:
    admin_offer_service.delete_offer(session, offer_id=offer_id)
