"""Request/response schemas for the admin offer CRUD (Fase 4).

Overlap against other offers on the same game needs a database read, so
that check lives in admin_offer_service.py, not here — this only validates
what a single request body can determine on its own (percent range, and
that the window isn't backwards or empty).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OfferCreate(BaseModel):
    # A que juego pertenece la oferta — se manda explicito en el body (no
    # viene de la URL) porque el endpoint es POST /admin/offers, uno solo
    # para todos los juegos, no uno por juego.
    game_id: int
    # ge=1, le=90: el porcentaje de descuento tiene que estar entre 1 y 90
    # (inclusive) — mismo rango que ya exige la columna en el modelo Offer,
    # pero validado aca ANTES de llegar a la base de datos, para devolver
    # un 422 claro en vez de un error de constraint de SQL.
    discount_percent: int = Field(ge=1, le=90)
    starts_at: datetime
    ends_at: datetime
    # is_active tiene un valor por defecto (True): si el admin no lo manda
    # explicitamente, la oferta se crea activa.
    is_active: bool = True

    # @model_validator(mode="after") corre DESPUES de que Pydantic ya
    # valido cada campo por separado — se usa cuando la validacion depende
    # de la relacion ENTRE dos campos (aca: que ends_at sea posterior a
    # starts_at), algo que Field() por si solo no puede expresar porque
    # solo mira un campo a la vez.
    @model_validator(mode="after")
    def _window_is_ordered(self) -> OfferCreate:
        # self ya tiene starts_at y ends_at parseados como datetime en
        # este punto, listos para comparar directamente.
        if self.ends_at <= self.starts_at:
            # Lanzar ValueError aca hace que FastAPI devuelva un 422 con
            # este mensaje, exactamente igual que si hubiera fallado la
            # validacion de un campo individual.
            raise ValueError("ends_at debe ser posterior a starts_at.")
        # Un @model_validator(mode="after") tiene que devolver la instancia
        # (self) para que Pydantic siga usandola normalmente.
        return self


class OfferUpdate(BaseModel):
    """Every field optional. If either `starts_at`/`ends_at` is provided,
    the service resolves the full window (patched values merged onto the
    existing offer) before re-validating order and overlap — a partial
    body alone can't tell if the resulting window still makes sense.
    """

    # Todo opcional para un PATCH parcial. Notese que ACA no hay un
    # @model_validator como en OfferCreate: si el admin solo manda
    # ends_at (sin starts_at), este schema no tiene forma de saber si el
    # resultado final tiene sentido — esa validacion la hace el SERVICIO,
    # despues de combinar estos valores con los que ya tenia la oferta
    # guardada en la base de datos.
    discount_percent: int | None = Field(default=None, ge=1, le=90)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool | None = None


class OfferRead(BaseModel):
    # from_attributes=True: permite construir este schema directamente
    # desde un objeto Offer del ORM (OfferRead.model_validate(offer)).
    model_config = ConfigDict(from_attributes=True)

    id: int
    game_id: int
    discount_percent: int
    starts_at: datetime
    ends_at: datetime
    is_active: bool
