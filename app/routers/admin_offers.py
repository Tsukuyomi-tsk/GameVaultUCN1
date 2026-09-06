"""Admin offer CRUD (Fase 4). Every route requires AdminUser. Overlap and
date-order validation live in app.services.admin_offer_service.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import AdminUser
from app.schemas.offer import OfferCreate, OfferRead, OfferUpdate
from app.services import admin_offer_service

router = APIRouter(prefix="/admin/offers", tags=["admin-offers"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[OfferRead])
def list_offers(
    session: SessionDep, _admin: AdminUser, game_id: int | None = None
) -> list[OfferRead]:
    offers = admin_offer_service.list_offers(session, game_id=game_id)
    return [OfferRead.model_validate(o) for o in offers]


@router.post("", response_model=OfferRead, status_code=status.HTTP_201_CREATED)
def create_offer(payload: OfferCreate, session: SessionDep, _admin: AdminUser) -> OfferRead:
    offer = admin_offer_service.create_offer(session, payload=payload)
    return OfferRead.model_validate(offer)


@router.patch("/{offer_id}", response_model=OfferRead)
def update_offer(
    offer_id: int, payload: OfferUpdate, session: SessionDep, _admin: AdminUser
) -> OfferRead:
    offer = admin_offer_service.update_offer(session, offer_id=offer_id, payload=payload)
    return OfferRead.model_validate(offer)


@router.delete("/{offer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_offer(offer_id: int, session: SessionDep, _admin: AdminUser) -> None:
    admin_offer_service.delete_offer(session, offer_id=offer_id)
