"""Business logic for the admin offer CRUD (Fase 4).

Overlap validation is the one rule that matters here: at most one *active*
offer may be live on a game at any given moment, because
offer_repository.get_active_offer_for_game (and the catalog's price join)
both assume exactly that — "at most one should ever match". Create/update
both re-check it against the resolved window before saving.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import Offer
from app.repositories.game_repository import GameRepository
from app.repositories.offer_repository import OfferRepository
from app.schemas.offer import OfferCreate, OfferUpdate


def _check_no_overlap(
    offers: OfferRepository,
    *,
    game_id: int,
    starts_at: datetime,
    ends_at: datetime,
    is_active: bool,
    exclude_offer_id: int | None = None,
) -> None:
    # Funcion privada compartida por create_offer y update_offer: ambas
    # necesitan hacer exactamente el mismo chequeo, solo que update_offer
    # ademas tiene que excluirse a si misma de la comparacion.
    if not is_active:
        # Si la oferta que se esta guardando NO va a estar activa, no
        # puede "chocar" con ninguna otra — una oferta apagada nunca
        # aplica descuento, asi que no hay nada que proteger.
        return
    overlapping = offers.list_overlapping_active(
        game_id=game_id, starts_at=starts_at, ends_at=ends_at, exclude_offer_id=exclude_offer_id
    )
    if overlapping:
        # Si la consulta devolvio aunque sea una oferta que se solapa, se
        # corta la operacion con un 409 (conflicto): el pedido esta bien
        # formado, pero choca con el estado actual de la base de datos.
        raise ConflictError(
            "Ya existe una oferta activa que se superpone con este rango de fechas para este juego."
        )


def list_offers(session: Session, *, game_id: int | None) -> list[Offer]:
    # Funcion trivial: solo delega en el repositorio.
    return OfferRepository(session).list_all(game_id=game_id)


def create_offer(session: Session, *, payload: OfferCreate) -> Offer:
    games = GameRepository(session)
    offers = OfferRepository(session)

    # No tiene sentido crear una oferta para un juego que no existe (o que
    # ya fue eliminado) — get() sin include_deleted=True ya excluye los
    # juegos soft-deleted automaticamente.
    if games.get(payload.game_id) is None:
        raise NotFoundError("Juego no encontrado.")

    # Reutiliza la funcion privada de arriba para chequear solapamiento
    # contra las ofertas activas YA existentes de este juego.
    _check_no_overlap(
        offers,
        game_id=payload.game_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        is_active=payload.is_active,
    )

    offer = offers.add(
        Offer(
            game_id=payload.game_id,
            discount_percent=payload.discount_percent,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            is_active=payload.is_active,
        )
    )
    session.commit()
    session.refresh(offer)
    return offer


def update_offer(session: Session, *, offer_id: int, payload: OfferUpdate) -> Offer:
    offers = OfferRepository(session)
    offer = offers.get(offer_id)
    if offer is None:
        raise NotFoundError("Oferta no encontrada.")

    # Solo entran al dict los campos que el admin realmente mando en el
    # body del PATCH.
    data = payload.model_dump(exclude_unset=True)
    # Aca esta la parte clave de un PATCH parcial sobre una oferta: como
    # la validacion de fechas necesita starts_at Y ends_at juntos, se
    # "resuelve" el valor final de cada uno combinando lo que vino en el
    # body con lo que la oferta YA tenia guardado. data.get("starts_at",
    # offer.starts_at) significa: "si starts_at vino en el body, usa ese
    # valor; si no, usa el que la oferta ya tenia".
    resolved_starts_at = data.get("starts_at", offer.starts_at)
    resolved_ends_at = data.get("ends_at", offer.ends_at)
    resolved_is_active = data.get("is_active", offer.is_active)

    # Se valida el rango YA COMBINADO — asi se detecta, por ejemplo, que
    # mandar solo un nuevo starts_at posterior al ends_at existente
    # tambien es invalido, aunque el body en si mismo solo traiga un campo.
    if resolved_ends_at <= resolved_starts_at:
        raise ValidationError("ends_at debe ser posterior a starts_at.")

    # Mismo chequeo de solapamiento que en create_offer, pero excluyendo
    # esta misma oferta de la comparacion (exclude_offer_id=offer.id) —
    # si no, la oferta siempre "chocaria contra si misma".
    _check_no_overlap(
        offers,
        game_id=offer.game_id,
        starts_at=resolved_starts_at,
        ends_at=resolved_ends_at,
        is_active=resolved_is_active,
        exclude_offer_id=offer.id,
    )

    # Recien aca, despues de que TODAS las validaciones pasaron, se
    # aplican los cambios sobre el objeto real.
    for field, value in data.items():
        setattr(offer, field, value)

    offers.add(offer)
    session.commit()
    session.refresh(offer)
    return offer


def delete_offer(session: Session, *, offer_id: int) -> None:
    offers = OfferRepository(session)
    offer = offers.get(offer_id)
    if offer is None:
        raise NotFoundError("Oferta no encontrada.")
    # A diferencia de juegos/categorias, Offer NO tiene columna
    # deleted_at — nada mas en la base de datos referencia una oferta por
    # su id, asi que acá se hace un borrado FISICO y real de la fila
    # (BaseRepository.delete hace un DELETE de verdad, no un soft delete).
    offers.delete(offer)
    session.commit()
