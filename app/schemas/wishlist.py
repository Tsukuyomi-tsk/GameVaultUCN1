"""Response schema for the wishlist endpoints (Fase 6).

The price fields come from the same offer_repository helpers the catalog,
cart and checkout use (active_offer_clause / compute_effective_price) —
never re-derived here.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class WishlistItemRead(BaseModel):
    game_id: int
    title: str
    slug: str
    platform: str
    # base_price: precio de lista, sin ningun descuento aplicado.
    base_price: Decimal
    # final_price: lo que costaria comprarlo AHORA MISMO, con la oferta
    # vigente aplicada si la hay.
    final_price: Decimal
    discount_percent: int
    has_active_offer: bool
    # Cuando el usuario agrego el juego a su wishlist.
    added_at: datetime
