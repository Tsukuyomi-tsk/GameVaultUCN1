"""Data access for the public game catalog — the only place that builds the
search/filter/sort/paginate query, and the only place (besides the seeder,
via offer_repository) that joins Game to Offer.

Two read paths:

- `search()` powers GET /games. It joins every game against its (at most
  one) active offer, review stats and sales count in a single statement so
  listing N games never costs N+1 queries — filters/sort operate on that
  same joined statement, and pagination happens after a COUNT built from
  the exact same filters.
- `get_detail_by_slug()` powers GET /games/{slug}. It fetches one game and
  reuses `get_active_offer_for_game`/`compute_effective_price` from
  offer_repository directly instead of the joined-query trick, since a
  single-row detail page has no N+1 to avoid.

Both paths call `active_offer_clause`/`compute_effective_price` — never a
re-derived "is this offer live" or discount-math expression. The one
exception is the SQL expression used purely to filter/sort by price
(`_effective_price_expr`): it recomputes the same formula in SQL because
`compute_effective_price` needs a Python `Offer` object per row, which a
multi-row listing query doesn't have until after it runs. That expression
is never returned to a caller — every displayed price still goes through
`compute_effective_price`, so a rounding difference at a sub-cent boundary
can, at most, place a game one position off at a price_min/price_max edge,
never show a wrong price.

Like offer_repository itself, this assumes at most one active offer exists
per game at any given time (Fase 4's admin offer creation is responsible
for not letting two overlap) — an outer join to Offer therefore never fans
a game out into duplicate rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, delete, func
from sqlmodel import select

from app.models import Category, Game, GameCategoryLink, GameImage, Offer, Order, OrderItem, Review
from app.models.enums import OrderStatus
from app.repositories.base import BaseRepository
from app.repositories.offer_repository import (
    active_offer_clause,
    compute_effective_price,
    get_active_offer_for_game,
)
from app.schemas.game import GameSort


@dataclass
class GameSummaryRow:
    """One row of a catalog listing: the Game plus everything computed for
    display. Never a raw ORM object — the router maps this to GameListItem
    field by field, so it's explicit which computed values are public.
    """

    game: Game
    final_price: Decimal
    discount_percent: int
    has_active_offer: bool
    cover_image_url: str | None


@dataclass
class GameDetailRow:
    """Full detail for a single game's catalog page."""

    game: Game
    final_price: Decimal
    discount_percent: int
    has_active_offer: bool
    images: list[GameImage]
    categories: list[Category]
    rating_average: float | None
    rating_count: int


# GameAdminRow es el "paquete" que arma load_admin_row(): junta el juego
# con sus imagenes y categorias en un solo objeto, para que el router de
# admin no tenga que hacer 3 consultas sueltas por separado.
@dataclass
class GameAdminRow:
    """Full admin view of one game: the row itself plus its images and
    categories — no catalog-only computed pricing, unlike GameDetailRow.
    """

    game: Game
    images: list[GameImage]
    categories: list[Category]


class GameRepository(BaseRepository[Game]):
    model = Game

    def _sales_count_subquery(self):
        """Times each game has been bought, from paid orders only — the
        catalog's "popularidad" sort. Reuses OrderItem, the same table
        Fase 4's admin popularity stats (top comprados) will aggregate.
        """
        return (
            select(OrderItem.game_id, func.count(OrderItem.id).label("sales_count"))
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.status == OrderStatus.PAID, OrderItem.game_id.is_not(None))
            .group_by(OrderItem.game_id)
            .subquery()
        )

    def _rating_subquery(self):
        return (
            select(
                Review.game_id,
                func.avg(Review.rating).label("avg_rating"),
                func.count(Review.id).label("review_count"),
            )
            .where(Review.deleted_at.is_(None))
            .group_by(Review.game_id)
            .subquery()
        )

    def _cover_image_expr(self):
        """Scalar subquery: the flagged cover image if there is one,
        otherwise the lowest sort_order image, otherwise NULL.
        """
        return (
            select(GameImage.url)
            .where(GameImage.game_id == Game.id)
            .order_by(GameImage.is_cover.desc(), GameImage.sort_order.asc())
            .limit(1)
            .correlate(Game)
            .scalar_subquery()
        )

    def _effective_price_expr(self, discount_expr):
        """SQL-only mirror of compute_effective_price's formula, for
        filtering/sorting by price — see the module docstring for why this
        never reaches a response body.
        """
        return func.round(Game.base_price - (Game.base_price * discount_expr / 100.0), 2)

    def search(
        self,
        *,
        now: datetime,
        q: str | None,
        categories: list[str] | None,
        platform: str | None,
        price_min: Decimal | None,
        price_max: Decimal | None,
        on_offer: bool | None,
        min_rating: float | None,
        sort: GameSort,
        offset: int,
        limit: int,
    ) -> tuple[list[GameSummaryRow], int]:
        """Filtered, sorted, paginated catalog listing plus the total count
        of matching games (for the response's `total`/`pages`).
        """
        sales_subq = self._sales_count_subquery()
        rating_subq = self._rating_subquery()
        discount_expr = func.coalesce(Offer.discount_percent, 0)
        price_expr = self._effective_price_expr(discount_expr)
        popularity_expr = func.coalesce(sales_subq.c.sales_count, 0)

        statement = (
            select(Game, Offer, self._cover_image_expr().label("cover_image_url"))
            .outerjoin(Offer, and_(Offer.game_id == Game.id, active_offer_clause(now)))
            .outerjoin(sales_subq, sales_subq.c.game_id == Game.id)
            .outerjoin(rating_subq, rating_subq.c.game_id == Game.id)
            .where(Game.is_active.is_(True), Game.deleted_at.is_(None))
        )

        if q:
            # icontains(autoescape=True) arma el LIKE '%q%' ESCAPANDO los
            # comodines de q: sin eso, un "%" o "_" escrito por el usuario se
            # interpretaria como comodin y "q=%" listaria todo el catalogo.
            statement = statement.where(
                Game.title.icontains(q, autoescape=True)
                | Game.description.icontains(q, autoescape=True)
            )
        if platform:
            statement = statement.where(func.lower(Game.platform) == platform.lower())
        if price_min is not None:
            statement = statement.where(price_expr >= price_min)
        if price_max is not None:
            statement = statement.where(price_expr <= price_max)
        if on_offer is True:
            statement = statement.where(Offer.id.is_not(None))
        elif on_offer is False:
            statement = statement.where(Offer.id.is_(None))
        if min_rating is not None:
            statement = statement.where(rating_subq.c.avg_rating >= min_rating)
        if categories:
            statement = statement.where(
                Game.id.in_(
                    select(GameCategoryLink.game_id)
                    .join(Category, Category.id == GameCategoryLink.category_id)
                    .where(Category.slug.in_(categories), Category.deleted_at.is_(None))
                )
            )

        total = self.session.execute(statement.with_only_columns(func.count(Game.id))).scalar_one()

        sort_map = {
            GameSort.TITLE_ASC: (Game.title.asc(),),
            GameSort.TITLE_DESC: (Game.title.desc(),),
            GameSort.PRICE_ASC: (price_expr.asc(),),
            GameSort.PRICE_DESC: (price_expr.desc(),),
            GameSort.RELEASE_DATE_ASC: (Game.release_date.asc(),),
            GameSort.RELEASE_DATE_DESC: (Game.release_date.desc(),),
            GameSort.POPULARITY_ASC: (popularity_expr.asc(),),
            GameSort.POPULARITY_DESC: (popularity_expr.desc(),),
        }
        statement = statement.order_by(*sort_map[sort], Game.id.asc()).offset(offset).limit(limit)

        rows = self.session.exec(statement).all()
        summaries = []
        for game, offer, cover_image_url in rows:
            final_price, discount_percent = compute_effective_price(game.base_price, offer)
            summaries.append(
                GameSummaryRow(
                    game=game,
                    final_price=final_price,
                    discount_percent=discount_percent,
                    has_active_offer=offer is not None,
                    cover_image_url=cover_image_url,
                )
            )
        return summaries, int(total)

    def get_detail_by_slug(self, *, slug: str, now: datetime) -> GameDetailRow | None:
        game = self.session.exec(
            select(Game).where(
                Game.slug == slug, Game.is_active.is_(True), Game.deleted_at.is_(None)
            )
        ).first()
        if game is None:
            return None

        offer = get_active_offer_for_game(self.session, game.id, now)
        final_price, discount_percent = compute_effective_price(game.base_price, offer)

        images = self.session.exec(
            select(GameImage)
            .where(GameImage.game_id == game.id)
            .order_by(GameImage.is_cover.desc(), GameImage.sort_order.asc())
        ).all()

        categories = self.session.exec(
            select(Category)
            .join(GameCategoryLink, GameCategoryLink.category_id == Category.id)
            .where(GameCategoryLink.game_id == game.id, Category.deleted_at.is_(None))
            .order_by(Category.name.asc())
        ).all()

        rating_average, rating_count = self.session.execute(
            select(func.avg(Review.rating), func.count(Review.id)).where(
                Review.game_id == game.id, Review.deleted_at.is_(None)
            )
        ).one()

        return GameDetailRow(
            game=game,
            final_price=final_price,
            discount_percent=discount_percent,
            has_active_offer=offer is not None,
            images=list(images),
            categories=list(categories),
            rating_average=float(rating_average) if rating_average is not None else None,
            rating_count=int(rating_count),
        )

    def get_by_slug(self, slug: str, *, include_deleted: bool = False) -> Game | None:
        """Used by the admin service to enforce slug uniqueness on create
        and on update — unlike `get_detail_by_slug`, this ignores
        `is_active` entirely, since an admin must be able to look up an
        inactive game by slug too.
        """
        statement = select(Game).where(Game.slug == slug)
        # include_deleted=True se usa para chequear unicidad: un slug de
        # un juego soft-deleted sigue "ocupado" en la base de datos, asi
        # que un juego nuevo no puede reutilizarlo.
        if not include_deleted:
            statement = statement.where(Game.deleted_at.is_(None))
        return self.session.exec(statement).first()

    def list_admin(self, *, q: str | None, offset: int, limit: int) -> tuple[list[Game], int]:
        """Every game the backoffice can manage — inactive and soft-deleted
        included, unlike the public `search()`. The admin UI is what
        distinguishes them (via `is_active`/`deleted_at` on the response),
        not this query.
        """
        # A diferencia de search() (Fase 3), aca NO hay ningun WHERE sobre
        # is_active/deleted_at: el admin tiene que poder ver y gestionar
        # absolutamente todos los juegos, esten activos, inactivos o
        # eliminados.
        statement = select(Game)
        # Busqueda de texto opcional, solo sobre el titulo (mas simple que
        # la busqueda publica de Fase 3, que tambien mira la descripcion).
        if q:
            # autoescape=True: "%" y "_" del usuario se buscan como texto literal.
            statement = statement.where(Game.title.icontains(q, autoescape=True))

        # Cuenta cuantos juegos en total cumplen el filtro de busqueda
        # (antes de aplicar offset/limit), para el "total" de la respuesta
        # paginada.
        total = self.session.execute(statement.with_only_columns(func.count(Game.id))).scalar_one()

        # Trae la pagina pedida: los juegos mas nuevos primero (created_at
        # descendente), con el id como criterio de desempate para que el
        # orden sea siempre el mismo aunque dos juegos tengan la misma
        # fecha de creacion.
        rows = self.session.exec(
            statement.order_by(Game.created_at.desc(), Game.id.desc()).offset(offset).limit(limit)
        ).all()
        return list(rows), int(total)

    def set_categories(self, game_id: int, category_ids: list[int]) -> None:
        """Replaces every category link for a game with exactly
        `category_ids` — simplest correct semantics for a PATCH that
        accepts the full desired set, and avoids needing separate
        add/remove-category endpoints.
        """
        # Paso 1: borra TODOS los vinculos categoria<->juego que existieran
        # previamente para este juego. delete(GameCategoryLink) arma un
        # DELETE FROM game_category_links WHERE game_id = ... — se ejecuta
        # con session.execute() (no session.exec()) porque es una
        # sentencia DELETE, no un SELECT.
        self.session.execute(delete(GameCategoryLink).where(GameCategoryLink.game_id == game_id))
        # Paso 2: inserta un vinculo nuevo por cada category_id recibido.
        # Si category_ids llega vacia, este for simplemente no itera y el
        # juego queda sin categorias — comportamiento valido.
        for category_id in category_ids:
            self.session.add(GameCategoryLink(game_id=game_id, category_id=category_id))
        # flush() manda los INSERT/DELETE a la base de datos dentro de la
        # transaccion actual, pero sin confirmarla (commit) todavia — eso
        # queda a cargo del servicio que orquesta la operacion completa.
        self.session.flush()

    def load_admin_row(self, game: Game) -> GameAdminRow:
        """Bundles a Game already fetched by the service with its images
        and categories, for GameAdminDetail. Unlike get_detail_by_slug,
        categories here are NOT filtered by deleted_at — an admin editing
        a game needs to see a link to a category that's since been
        soft-deleted, not have it silently vanish.
        """
        # Trae todas las imagenes del juego, portada primero.
        images = self.session.exec(
            select(GameImage)
            .where(GameImage.game_id == game.id)
            .order_by(GameImage.is_cover.desc(), GameImage.sort_order.asc())
        ).all()
        # Trae las categorias asociadas al juego, uniendo la tabla puente
        # game_category_links con categories. A diferencia de la vista
        # publica (Fase 3), aca NO se filtra Category.deleted_at.is_(None):
        # el admin necesita ver aunque sea una categoria eliminada para
        # poder decidir si desvincularla o restaurarla.
        categories = self.session.exec(
            select(Category)
            .join(GameCategoryLink, GameCategoryLink.category_id == Category.id)
            .where(GameCategoryLink.game_id == game.id)
            .order_by(Category.name.asc())
        ).all()
        # Empaqueta las tres piezas (juego + imagenes + categorias) en un
        # solo objeto GameAdminRow para devolver.
        return GameAdminRow(game=game, images=list(images), categories=list(categories))
