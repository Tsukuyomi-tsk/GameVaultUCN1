"""Business logic for the admin category CRUD (Fase 4). Mirrors
admin_game_service's soft-delete/restore idempotency and uniqueness-check
pattern, at the smaller scale a Category actually needs (no images, no
associations to manage beyond what game CRUD already owns).
"""

from __future__ import annotations

from sqlmodel import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.core.time import utcnow
from app.models import Category
from app.repositories.category_repository import CategoryRepository
from app.schemas.admin_category import CategoryCreate, CategoryUpdate


def list_categories(session: Session) -> list[Category]:
    return CategoryRepository(session).list_all_admin()


def create_category(session: Session, *, payload: CategoryCreate) -> Category:
    categories = CategoryRepository(session)
    if categories.get_by_slug(payload.slug, include_deleted=True) is not None:
        raise ValidationError("Ya existe una categoria con ese slug.")
    if categories.get_by_name(payload.name, include_deleted=True) is not None:
        raise ValidationError("Ya existe una categoria con ese nombre.")

    category = categories.add(
        Category(name=payload.name, slug=payload.slug, description=payload.description)
    )
    session.commit()
    session.refresh(category)
    return category


def update_category(session: Session, *, category_id: int, payload: CategoryUpdate) -> Category:
    categories = CategoryRepository(session)
    category = categories.get(category_id, include_deleted=True)
    if category is None:
        raise NotFoundError("Categoria no encontrada.")

    data = payload.model_dump(exclude_unset=True)
    if "slug" in data and data["slug"] != category.slug:
        existing = categories.get_by_slug(data["slug"], include_deleted=True)
        if existing is not None and existing.id != category.id:
            raise ValidationError("Ya existe una categoria con ese slug.")
    if "name" in data and data["name"] != category.name:
        existing = categories.get_by_name(data["name"], include_deleted=True)
        if existing is not None and existing.id != category.id:
            raise ValidationError("Ya existe una categoria con ese nombre.")

    for field, value in data.items():
        setattr(category, field, value)

    categories.add(category)
    session.commit()
    session.refresh(category)
    return category


def soft_delete_category(session: Session, *, category_id: int) -> None:
    categories = CategoryRepository(session)
    category = categories.get(category_id, include_deleted=True)
    if category is None:
        raise NotFoundError("Categoria no encontrada.")
    if category.deleted_at is not None:
        return  # idempotente
    category.deleted_at = utcnow()
    categories.add(category)
    session.commit()


def restore_category(session: Session, *, category_id: int) -> Category:
    categories = CategoryRepository(session)
    category = categories.get(category_id, include_deleted=True)
    if category is None:
        raise NotFoundError("Categoria no encontrada.")
    if category.deleted_at is not None:
        category.deleted_at = None
        categories.add(category)
        session.commit()
        session.refresh(category)
    return category
