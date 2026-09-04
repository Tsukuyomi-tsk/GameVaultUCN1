"""Pydantic schemas for the public catalog: game list items, game detail,
and the sort enum shared by the router (query param) and the repository
(ORDER BY selection).

`base_price` is always the catalog price with no discount applied;
`final_price`/`discount_percent`/`has_active_offer` are always resolved via
app.repositories.offer_repository (active_offer_clause + compute_effective_price)
— never re-derived here or in the router.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.schemas.category import CategoryRead


class GameSort(StrEnum):
    """Combinable-with-filters sort options for GET /games."""

    TITLE_ASC = "title_asc"
    TITLE_DESC = "title_desc"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    RELEASE_DATE_ASC = "release_date_asc"
    RELEASE_DATE_DESC = "release_date_desc"
    POPULARITY_ASC = "popularity_asc"
    POPULARITY_DESC = "popularity_desc"


class GameImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    is_cover: bool
    sort_order: int


class GameListItem(BaseModel):
    """One row of GET /games.

    Deliberately lighter than GameDetail (no description/developer/
    publisher) — the listing payload should stay small when it's paginating
    over dozens of games.
    """

    id: int
    title: str
    slug: str
    platform: str
    release_date: date | None
    base_price: Decimal
    final_price: Decimal
    discount_percent: int
    has_active_offer: bool
    cover_image_url: str | None


class GamePage(BaseModel):
    """Paginated envelope for GET /games."""

    items: list[GameListItem]
    page: int
    size: int
    total: int
    pages: int


class GameDetail(BaseModel):
    """Full payload for GET /games/{slug}."""

    id: int
    title: str
    slug: str
    description: str | None
    developer: str | None
    publisher: str | None
    platform: str
    release_date: date | None
    base_price: Decimal
    final_price: Decimal
    discount_percent: int
    has_active_offer: bool
    images: list[GameImageRead]
    categories: list[CategoryRead]
    rating_average: float | None
    rating_count: int
