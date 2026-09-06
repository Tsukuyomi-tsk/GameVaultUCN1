"""Public catalog endpoints: game search/listing, game detail, categories.

No authentication anywhere in this router — level 1 ("publico") of the
plan's "Modelo de autorizacion". Like every other router, it only
translates HTTP <-> Python; every rule and query lives in
app.services.catalog_service / app.repositories.game_repository.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.category import CategoryRead
from app.schemas.game import GameDetail, GameImageRead, GameListItem, GamePage, GameSort
from app.services import catalog_service

router = APIRouter(tags=["catalog"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/games", response_model=GamePage)
def list_games(
    session: SessionDep,
    q: Annotated[
        str | None, Query(max_length=255, description="Busqueda en titulo y descripcion.")
    ] = None,
    categories: Annotated[
        list[str] | None, Query(description="Slugs de categoria; repetir el parametro para varias.")
    ] = None,
    platform: str | None = None,
    price_min: Annotated[Decimal | None, Query(ge=0)] = None,
    price_max: Annotated[Decimal | None, Query(ge=0)] = None,
    on_offer: bool | None = None,
    min_rating: Annotated[float | None, Query(ge=1, le=5)] = None,
    sort: GameSort = GameSort.TITLE_ASC,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> GamePage:
    items, total, pages = catalog_service.list_games(
        session,
        q=q,
        categories=categories,
        platform=platform,
        price_min=price_min,
        price_max=price_max,
        on_offer=on_offer,
        min_rating=min_rating,
        sort=sort,
        page=page,
        size=size,
    )
    return GamePage(
        items=[
            GameListItem(
                id=row.game.id,
                title=row.game.title,
                slug=row.game.slug,
                platform=row.game.platform,
                release_date=row.game.release_date,
                base_price=row.game.base_price,
                final_price=row.final_price,
                discount_percent=row.discount_percent,
                has_active_offer=row.has_active_offer,
                cover_image_url=row.cover_image_url,
            )
            for row in items
        ],
        page=page,
        size=size,
        total=total,
        pages=pages,
    )


@router.get("/games/{slug}", response_model=GameDetail)
def get_game(slug: str, session: SessionDep) -> GameDetail:
    detail = catalog_service.get_game_detail(session, slug=slug)
    return GameDetail(
        id=detail.game.id,
        title=detail.game.title,
        slug=detail.game.slug,
        description=detail.game.description,
        developer=detail.game.developer,
        publisher=detail.game.publisher,
        platform=detail.game.platform,
        release_date=detail.game.release_date,
        base_price=detail.game.base_price,
        final_price=detail.final_price,
        discount_percent=detail.discount_percent,
        has_active_offer=detail.has_active_offer,
        images=[GameImageRead.model_validate(image) for image in detail.images],
        categories=[CategoryRead.model_validate(category) for category in detail.categories],
        rating_average=detail.rating_average,
        rating_count=detail.rating_count,
    )


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(session: SessionDep) -> list[CategoryRead]:
    categories = catalog_service.list_categories(session)
    return [CategoryRead.model_validate(category) for category in categories]
