"""Idempotent database seeder.

Run manually with `python -m app.seeders.run`, or automatically at startup
when SEED_ON_STARTUP=true (see app/main.py's lifespan). Every insert is
guarded by a lookup on the entity's natural key, so running this twice in a
row never duplicates a row — required for it to be safe on every app
restart in development.

Assumes the schema already exists (`alembic upgrade head` has run). This
module never creates tables itself, to avoid the seeder and Alembic
disagreeing about what the schema looks like.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from urllib.parse import quote

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.config import settings
from app.core.database import engine
from app.core.security import hash_password
from app.core.time import utcnow
from app.models import (
    Category,
    Game,
    GameCategoryLink,
    GameImage,
    LibraryItem,
    Offer,
    Order,
    OrderItem,
    Review,
    User,
    UserRole,
    WishlistItem,
)
from app.seeders.data import (
    CATEGORIES,
    GAMES,
    OFFERS,
    SEED_ORDERS,
    SEED_REVIEWS,
    SEED_USER_PASSWORD,
    SEED_WISHLISTS,
    TEST_USERS,
)

logger = logging.getLogger(__name__)


def _seed_categories(session: Session) -> dict[str, Category]:
    by_slug: dict[str, Category] = {}
    created = 0
    for data in CATEGORIES:
        category = session.exec(select(Category).where(Category.slug == data["slug"])).first()
        if category is None:
            category = Category(**data)
            session.add(category)
            session.flush()
            created += 1
        by_slug[category.slug] = category
    logger.info("Categorias: %s creadas, %s ya existian", created, len(CATEGORIES) - created)
    return by_slug


def _seed_games(session: Session, categories_by_slug: dict[str, Category]) -> dict[str, Game]:
    by_slug: dict[str, Game] = {}
    created = 0
    for data in GAMES:
        category_slugs = data["categories"]
        game_fields = {k: v for k, v in data.items() if k != "categories"}
        game = session.exec(select(Game).where(Game.slug == game_fields["slug"])).first()
        if game is None:
            game = Game(**game_fields)
            session.add(game)
            session.flush()
            created += 1

            for slug in category_slugs:
                session.add(
                    GameCategoryLink(game_id=game.id, category_id=categories_by_slug[slug].id)
                )

            placeholder_url = f"https://placehold.co/600x800?text={quote(game.title)}"
            session.add(
                GameImage(
                    game_id=game.id,
                    url=placeholder_url,
                    public_id=f"seed:{game.slug}",
                    is_cover=True,
                    sort_order=0,
                )
            )
            session.flush()
        by_slug[game.slug] = game
    logger.info("Juegos: %s creados, %s ya existian", created, len(GAMES) - created)
    return by_slug


def _seed_offers(session: Session, games_by_slug: dict[str, Game]) -> None:
    now = utcnow()
    created = 0
    for data in OFFERS:
        game = games_by_slug[data["game_slug"]]
        existing = session.exec(select(Offer).where(Offer.game_id == game.id)).first()
        if existing is not None:
            continue
        session.add(
            Offer(
                game_id=game.id,
                discount_percent=data["discount_percent"],
                starts_at=now + timedelta(days=data["starts_offset_days"]),
                ends_at=now + timedelta(days=data["ends_offset_days"]),
                is_active=True,
            )
        )
        created += 1
    session.flush()
    logger.info("Ofertas: %s creadas, %s ya existian", created, len(OFFERS) - created)


def _get_or_create_user(
    session: Session,
    *,
    email: str,
    full_name: str,
    password: str,
    role: UserRole,
) -> tuple[User, bool]:
    user = session.exec(select(User).where(User.email == email)).first()
    if user is not None:
        return user, False
    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
        is_verified=True,
    )
    session.add(user)
    session.flush()
    return user, True


def _seed_users(session: Session) -> dict[str, User]:
    by_email: dict[str, User] = {}
    created = 0

    admin, was_created = _get_or_create_user(
        session,
        email=settings.admin_email,
        full_name=settings.admin_full_name,
        password=settings.admin_password,
        role=UserRole.ADMIN,
    )
    created += int(was_created)
    by_email[admin.email] = admin

    for data in TEST_USERS:
        user, was_created = _get_or_create_user(
            session,
            email=data["email"],
            full_name=data["full_name"],
            password=SEED_USER_PASSWORD,
            role=UserRole.USER,
        )
        created += int(was_created)
        by_email[user.email] = user

    total = 1 + len(TEST_USERS)
    logger.info("Usuarios: %s creados, %s ya existian", created, total - created)
    return by_email


def _next_order_code(session: Session) -> str:
    year = utcnow().year
    count = session.exec(select(func.count()).select_from(Order)).one()
    return f"GV-{year}-{count + 1:06d}"


def _seed_orders(
    session: Session, users_by_email: dict[str, User], games_by_slug: dict[str, Game]
) -> None:
    created = 0
    for index, data in enumerate(SEED_ORDERS):
        user = users_by_email[data["user_email"]]
        idempotency_key = f"seed-order-{index}"
        existing = session.exec(
            select(Order).where(Order.user_id == user.id, Order.idempotency_key == idempotency_key)
        ).first()
        if existing is not None:
            continue

        games = [games_by_slug[slug] for slug in data["game_slugs"]]
        subtotal = sum((game.base_price for game in games), Decimal("0"))
        order = Order(
            order_code=_next_order_code(session),
            user_id=user.id,
            subtotal=subtotal,
            discount_total=Decimal("0"),
            total=subtotal,
            idempotency_key=idempotency_key,
        )
        session.add(order)
        session.flush()

        for game in games:
            session.add(
                OrderItem(
                    order_id=order.id,
                    game_id=game.id,
                    title_snapshot=game.title,
                    slug_snapshot=game.slug,
                    unit_price=game.base_price,
                    discount_percent=0,
                    final_price=game.base_price,
                )
            )
            already_owned = session.exec(
                select(LibraryItem).where(
                    LibraryItem.user_id == user.id, LibraryItem.game_id == game.id
                )
            ).first()
            if already_owned is None:
                session.add(LibraryItem(user_id=user.id, game_id=game.id, order_id=order.id))
        session.flush()
        created += 1
    logger.info("Pedidos: %s creados, %s ya existian", created, len(SEED_ORDERS) - created)


def _seed_wishlists(
    session: Session, users_by_email: dict[str, User], games_by_slug: dict[str, Game]
) -> None:
    created = 0
    total = 0
    for data in SEED_WISHLISTS:
        user = users_by_email[data["user_email"]]
        for slug in data["game_slugs"]:
            total += 1
            game = games_by_slug[slug]
            existing = session.exec(
                select(WishlistItem).where(
                    WishlistItem.user_id == user.id, WishlistItem.game_id == game.id
                )
            ).first()
            if existing is not None:
                continue
            session.add(WishlistItem(user_id=user.id, game_id=game.id))
            created += 1
    session.flush()
    logger.info("Wishlist: %s creados, %s ya existian", created, total - created)


def _seed_reviews(
    session: Session, users_by_email: dict[str, User], games_by_slug: dict[str, Game]
) -> None:
    created = 0
    for data in SEED_REVIEWS:
        user = users_by_email[data["user_email"]]
        game = games_by_slug[data["game_slug"]]
        existing = session.exec(
            select(Review).where(Review.user_id == user.id, Review.game_id == game.id)
        ).first()
        if existing is not None:
            continue
        session.add(
            Review(
                user_id=user.id,
                game_id=game.id,
                rating=data["rating"],
                comment=data["comment"],
            )
        )
        created += 1
    session.flush()
    logger.info("Resenas: %s creadas, %s ya existian", created, len(SEED_REVIEWS) - created)


def run_seeders() -> None:
    """Populate the database with demo data. Safe to call on every startup."""
    with Session(engine) as session:
        categories_by_slug = _seed_categories(session)
        games_by_slug = _seed_games(session, categories_by_slug)
        _seed_offers(session, games_by_slug)
        session.commit()

        users_by_email = _seed_users(session)
        session.commit()

        _seed_orders(session, users_by_email, games_by_slug)
        _seed_wishlists(session, users_by_email, games_by_slug)
        _seed_reviews(session, users_by_email, games_by_slug)
        session.commit()

    logger.info("Seeder completado.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_seeders()
