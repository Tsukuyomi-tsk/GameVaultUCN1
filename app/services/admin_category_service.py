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
    # Funcion muy simple: solo delega en el repositorio la version
    # "admin" del listado (que incluye tambien las categorias eliminadas).
    return CategoryRepository(session).list_all_admin()


def create_category(session: Session, *, payload: CategoryCreate) -> Category:
    categories = CategoryRepository(session)
    # Dos chequeos de unicidad, uno por cada columna que el modelo
    # Category exige unica: slug Y name. include_deleted=True porque una
    # categoria eliminada sigue "ocupando" su slug/nombre en la base de
    # datos (no se liberan al hacer soft delete).
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

    # exclude_unset=True: solo entran al dict los campos que el admin
    # realmente mando en el body del PATCH (ver la explicacion detallada
    # de este mismo patron en admin_game_service.update_game).
    data = payload.model_dump(exclude_unset=True)
    # Solo se re-valida unicidad si el campo vino en el body Y ademas es
    # distinto al valor que la categoria ya tenia — si el admin manda el
    # mismo slug que ya tenia, no hace falta chequear nada.
    if "slug" in data and data["slug"] != category.slug:
        existing = categories.get_by_slug(data["slug"], include_deleted=True)
        # Si existe otra categoria (con OTRO id) con ese slug, es un
        # conflicto real; si el "existing" resulta ser esta misma
        # categoria, no hay problema.
        if existing is not None and existing.id != category.id:
            raise ValidationError("Ya existe una categoria con ese slug.")
    if "name" in data and data["name"] != category.name:
        existing = categories.get_by_name(data["name"], include_deleted=True)
        if existing is not None and existing.id != category.id:
            raise ValidationError("Ya existe una categoria con ese nombre.")

    # Aplica cada campo presente en el body sobre el objeto ya cargado.
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
        # Ya estaba eliminada — DELETE es idempotente, no se hace nada
        # mas ni se lanza ningun error.
        return
    # Soft delete: se marca la fecha de eliminacion en vez de borrar la
    # fila. Los juegos que ya estaban vinculados a esta categoria NO
    # pierden el vinculo (game_category_links no se toca) — solo deja de
    # listarse esta categoria en el catalogo publico.
    category.deleted_at = utcnow()
    categories.add(category)
    session.commit()


def restore_category(session: Session, *, category_id: int) -> Category:
    categories = CategoryRepository(session)
    category = categories.get(category_id, include_deleted=True)
    if category is None:
        raise NotFoundError("Categoria no encontrada.")
    if category.deleted_at is not None:
        # Solo hay algo que hacer si de verdad estaba eliminada.
        category.deleted_at = None
        categories.add(category)
        session.commit()
        session.refresh(category)
    # Si ya estaba activa, se devuelve tal cual — restaurar tambien es
    # idempotente.
    return category
