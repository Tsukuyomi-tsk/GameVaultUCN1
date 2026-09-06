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
    game_id: int
    discount_percent: int = Field(ge=1, le=90)
    starts_at: datetime
    ends_at: datetime
    is_active: bool = True

    @model_validator(mode="after")
    def _window_is_ordered(self) -> OfferCreate:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at debe ser posterior a starts_at.")
        return self


class OfferUpdate(BaseModel):
    """Every field optional. If either `starts_at`/`ends_at` is provided,
    the service resolves the full window (patched values merged onto the
    existing offer) before re-validating order and overlap — a partial
    body alone can't tell if the resulting window still makes sense.
    """

    discount_percent: int | None = Field(default=None, ge=1, le=90)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool | None = None


class OfferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    game_id: int
    discount_percent: int
    starts_at: datetime
    ends_at: datetime
    is_active: bool
