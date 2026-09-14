"""Response schema for GET /me/library (Fase 5)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class LibraryItemRead(BaseModel):
    # Datos del juego (no del LibraryItem crudo): el usuario quiere ver
    # QUE juego posee, no el id interno de la fila de propiedad.
    game_id: int
    title: str
    slug: str
    platform: str
    acquired_at: datetime
    # order_code (no order_id): el identificador publico de la orden que
    # origino esta compra, para que el usuario pueda ir a ver el detalle o
    # la boleta desde su biblioteca.
    order_code: str
