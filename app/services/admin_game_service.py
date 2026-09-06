"""Business logic for the admin game backoffice (Fase 4): CRUD, soft
delete/restore, and catalog image management.

Uniqueness (slug) and category-id validity need a database read, so they
live here rather than in the request schema — same split the rest of the
app already follows (see auth_service.register for the same pattern with
email uniqueness).
"""

from __future__ import annotations

from sqlmodel import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.core.time import utcnow
from app.integrations import cloudinary_client
from app.models import Game, GameImage
from app.repositories.category_repository import CategoryRepository
from app.repositories.game_image_repository import GameImageRepository
from app.repositories.game_repository import GameAdminRow, GameRepository
from app.schemas.admin_game import GameCreate, GameUpdate


def _validate_category_ids(categories: CategoryRepository, category_ids: list[int]) -> None:
    if not category_ids:
        return
    found = categories.get_many(category_ids)
    missing = set(category_ids) - {c.id for c in found}
    if missing:
        raise ValidationError(f"Categorias invalidas: {sorted(missing)}")


def list_games(
    session: Session, *, q: str | None, page: int, size: int
) -> tuple[list[Game], int, int]:
    games = GameRepository(session)
    offset = (page - 1) * size
    items, total = games.list_admin(q=q, offset=offset, limit=size)
    pages = (total + size - 1) // size if total else 0
    return items, total, pages


def get_game(session: Session, *, game_id: int) -> GameAdminRow:
    games = GameRepository(session)
    game = games.get(game_id, include_deleted=True)
    if game is None:
        raise NotFoundError("Juego no encontrado.")
    return games.load_admin_row(game)


def create_game(session: Session, *, payload: GameCreate) -> GameAdminRow:
    games = GameRepository(session)
    categories = CategoryRepository(session)

    if games.get_by_slug(payload.slug, include_deleted=True) is not None:
        raise ValidationError("Ya existe un juego con ese slug.")
    _validate_category_ids(categories, payload.category_ids)

    game = games.add(
        Game(
            title=payload.title,
            slug=payload.slug,
            description=payload.description,
            developer=payload.developer,
            publisher=payload.publisher,
            platform=payload.platform,
            release_date=payload.release_date,
            base_price=payload.base_price,
        )
    )
    games.set_categories(game.id, payload.category_ids)
    session.commit()
    session.refresh(game)
    return games.load_admin_row(game)


def update_game(session: Session, *, game_id: int, payload: GameUpdate) -> GameAdminRow:
    games = GameRepository(session)
    categories = CategoryRepository(session)

    game = games.get(game_id, include_deleted=True)
    if game is None:
        raise NotFoundError("Juego no encontrado.")

    data = payload.model_dump(exclude_unset=True)
    category_ids = data.pop("category_ids", None)

    if "slug" in data and data["slug"] != game.slug:
        existing = games.get_by_slug(data["slug"], include_deleted=True)
        if existing is not None and existing.id != game.id:
            raise ValidationError("Ya existe un juego con ese slug.")

    for field, value in data.items():
        setattr(game, field, value)

    games.add(game)
    if category_ids is not None:
        _validate_category_ids(categories, category_ids)
        games.set_categories(game.id, category_ids)
    session.commit()
    session.refresh(game)
    return games.load_admin_row(game)


def soft_delete_game(session: Session, *, game_id: int) -> None:
    games = GameRepository(session)
    game = games.get(game_id, include_deleted=True)
    if game is None:
        raise NotFoundError("Juego no encontrado.")
    if game.deleted_at is not None:
        return  # ya eliminado — DELETE es idempotente
    game.deleted_at = utcnow()
    games.add(game)
    session.commit()


def restore_game(session: Session, *, game_id: int) -> GameAdminRow:
    games = GameRepository(session)
    game = games.get(game_id, include_deleted=True)
    if game is None:
        raise NotFoundError("Juego no encontrado.")
    if game.deleted_at is not None:
        game.deleted_at = None
        games.add(game)
        session.commit()
        session.refresh(game)
    return games.load_admin_row(game)


def add_game_image(
    session: Session,
    *,
    game_id: int,
    filename: str,
    content: bytes,
    content_type: str | None,
    is_cover: bool,
) -> GameImage:
    games = GameRepository(session)
    images = GameImageRepository(session)

    game = games.get(game_id, include_deleted=True)
    if game is None:
        raise NotFoundError("Juego no encontrado.")
    if not content_type or not content_type.startswith("image/"):
        raise ValidationError("El archivo debe ser una imagen.")

    url, public_id = cloudinary_client.upload_image(
        game_id=game_id, filename=filename, content=content
    )

    if is_cover:
        images.clear_cover(game_id)

    existing_count = len(images.list_for_game(game_id))
    image = images.add(
        GameImage(
            game_id=game_id,
            url=url,
            public_id=public_id,
            is_cover=is_cover,
            sort_order=existing_count,
        )
    )
    session.commit()
    session.refresh(image)
    return image


def delete_game_image(session: Session, *, game_id: int, image_id: int) -> None:
    images = GameImageRepository(session)
    image = images.get(image_id)
    if image is None or image.game_id != game_id:
        raise NotFoundError("Imagen no encontrada.")

    cloudinary_client.delete_image(image.public_id)
    images.delete(image)
    session.commit()
