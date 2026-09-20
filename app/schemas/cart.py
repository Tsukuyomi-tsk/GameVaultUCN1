"""Request/response schemas for the shopping cart (Fase 5).

`final_price`/`discount_percent`/`has_active_offer` come from the exact
same offer_repository helpers the catalog (Fase 3) and checkout use — see
app.services.cart_service._build_view. `cart_token` only ever carries a
value for a guest request (see cart_service): a logged-in user's identity
already comes from their JWT, so there is nothing for the client to store.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class AddCartItemRequest(BaseModel):
    # El unico dato que manda el cliente al agregar un item: que juego
    # quiere agregar. Todo lo demas (precio, descuento) lo calcula el
    # servidor.
    game_id: int


class CartItemRead(BaseModel):
    game_id: int
    title: str
    slug: str
    # base_price: precio de lista, sin ningun descuento aplicado.
    base_price: Decimal
    # final_price: lo que el usuario pagaria si comprara AHORA MISMO — ya
    # con el descuento de la oferta vigente aplicado, si hay una.
    final_price: Decimal
    discount_percent: int
    has_active_offer: bool


class CartRead(BaseModel):
    items: list[CartItemRead]
    subtotal: Decimal
    discount_total: Decimal
    total: Decimal
    # Solo viene con valor para un carrito de INVITADO recien creado o
    # identificado por header — el cliente debe guardarlo y reenviarlo en
    # "X-Cart-Token" en las siguientes llamadas. Para un usuario logueado
    # siempre es null: su identidad ya viene del JWT.
    cart_token: str | None = Field(default=None)
