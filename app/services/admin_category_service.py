"""Business logic for the admin category CRUD (Fase 4). Mirrors
admin_game_service's soft-delete/restore idempotency and uniqueness-check
pattern, at the smaller scale a Category actually needs (no images, no
associations to manage beyond what game CRUD already owns).
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
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


def _check_unique(
    categories: CategoryRepository, *, slug: str, name: str, exclude_id: int | None = None
) -> None:
    # Dos chequeos de unicidad, uno por cada columna que el modelo Category
    # exige unica: slug Y name. include_deleted=True porque una categoria
    # eliminada sigue "ocupando" su slug/nombre en la base de datos (no se
    # liberan al hacer soft delete). exclude_id sirve para el PATCH: una
    # categoria no choca contra si misma.
    existing = categories.get_by_slug(slug, include_deleted=True)
    if existing is not None and existing.id != exclude_id:
        raise ValidationError("Ya existe una categoria con ese slug.")
    existing = categories.get_by_name(name, include_deleted=True)
    if existing is not None and existing.id != exclude_id:
        raise ValidationError("Ya existe una categoria con ese nombre.")


def create_category(session: Session, *, payload: CategoryCreate) -> Category:
    categories = CategoryRepository(session)
    _check_unique(categories, slug=payload.slug, name=payload.name)

    try:
        category = categories.add(
            Category(name=payload.name, slug=payload.slug, description=payload.description)
        )
        session.commit()
    except IntegrityError:
        # Dos admins crearon la misma categoria a la vez: ambos pasaron el
        # chequeo de arriba y el UNIQUE de la base de datos desempato. Se
        # deshace este intento y se repite el chequeo — ahora SI encuentra
        # a la ganadora y responde con el mismo mensaje preciso de siempre.
        session.rollback()
        _check_unique(categories, slug=payload.slug, name=payload.name)
        raise
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
    # Si existe otra categoria (con OTRO id) con ese slug/nombre, es un
    # conflicto real; _check_unique ya excluye a esta misma categoria.
    final_slug = data.get("slug", category.slug)
    final_name = data.get("name", category.name)
    if final_slug != category.slug or final_name != category.name:
        _check_unique(categories, slug=final_slug, name=final_name, exclude_id=category.id)

    # Aplica cada campo presente en el body sobre el objeto ya cargado.
    for field, value in data.items():
        setattr(category, field, value)

    try:
        categories.add(category)
        session.commit()
    except IntegrityError:
        # Misma carrera que en create_category (otro admin tomo el slug o
        # el nombre entre el chequeo y el UPDATE).
        session.rollback()
        _check_unique(categories, slug=final_slug, name=final_name, exclude_id=category_id)
        raise
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
