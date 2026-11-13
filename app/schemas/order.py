"""Request/response schemas for checkout and order history (Fase 5).

Mirrors the catalog's GameListItem/GameDetail split (app/schemas/game.py):
OrderSummary is the lighter shape for GET /orders' pages, OrderDetail adds
the line items for a single order (GET /orders/{order_code} and the
checkout response itself).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import OrderStatus


class OrderItemRead(BaseModel):
    # from_attributes=True: permite construir este schema directamente
    # desde un objeto OrderItem del ORM (OrderItemRead.model_validate(item)).
    model_config = ConfigDict(from_attributes=True)

    # game_id puede ser None: ver el docstring de OrderItem — si el juego
    # original se llega a hard-delete alguna vez, esta columna pasa a NULL
    # (ON DELETE SET NULL), pero title_snapshot/slug_snapshot de abajo
    # siguen mostrando que se compro igual.
    game_id: int | None
    title_snapshot: str
    slug_snapshot: str
    unit_price: Decimal
    discount_percent: int
    final_price: Decimal


class OrderSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # order_code es el identificador PUBLICO de la orden — nunca se expone
    # el id interno de la fila.
    order_code: str
    status: OrderStatus
    subtotal: Decimal
    discount_total: Decimal
    total: Decimal
    created_at: datetime
    paid_at: datetime


class OrderPage(BaseModel):
    # Mismo esquema de paginacion que GamePage/UserPage: items de esta
    # pagina, mas los datos para que el cliente arme la navegacion.
    items: list[OrderSummary]
    page: int
    size: int
    total: int
    pages: int


class OrderDetail(BaseModel):
    # Deliberadamente NO hereda de OrderSummary (mismo criterio que
    # GameListItem/GameDetail en el catalogo): son dos formas de respuesta
    # independientes, aunque compartan varios campos.
    order_code: str
    status: OrderStatus
    subtotal: Decimal
    discount_total: Decimal
    total: Decimal
    created_at: datetime
    paid_at: datetime
    # None mientras el correo de confirmacion todavia no se envio (el
    # BackgroundTask del checkout corre despues de responder).
    receipt_sent_at: datetime | None
    items: list[OrderItemRead]
