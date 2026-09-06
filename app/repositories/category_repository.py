"""Data access for Category — no query outside this class touches the
categories table directly.
"""

from __future__ import annotations

from sqlmodel import select

from app.models import Category
from app.repositories.base import BaseRepository


class CategoryRepository(BaseRepository[Category]):
    model = Category

    def list_all(self) -> list[Category]:
        """Every non-deleted category, alphabetically — the whole public
        catalog is small enough (Fase 3) that this doesn't need pagination.
        """
        statement = select(Category).where(Category.deleted_at.is_(None)).order_by(Category.name)
        return list(self.session.exec(statement).all())

    def list_all_admin(self) -> list[Category]:
        """Every category, deleted ones included — the backoffice needs to
        see what it can restore, not just what's currently public.
        """
        # A diferencia de list_all(), aca NO se filtra por deleted_at: el
        # admin necesita ver tambien las categorias eliminadas (soft
        # delete) para poder restaurarlas — si se filtraran, desaparecerian
        # para siempre de la vista del admin en cuanto se borraran.
        statement = select(Category).order_by(Category.name)
        return list(self.session.exec(statement).all())

    def get_by_slug(self, slug: str, *, include_deleted: bool = False) -> Category | None:
        statement = select(Category).where(Category.slug == slug)
        # Por defecto (include_deleted=False) se ignoran las categorias ya
        # eliminadas, como si no existieran. El servicio de admin pasa
        # include_deleted=True cuando necesita chequear duplicados contra
        # TODAS las categorias, incluidas las borradas — el slug sigue
        # "ocupado" en la base de datos aunque este soft-deleted.
        if not include_deleted:
            statement = statement.where(Category.deleted_at.is_(None))
        # .first() devuelve la primera fila que matchea, o None si ninguna
        # categoria tiene ese slug.
        return self.session.exec(statement).first()

    def get_by_name(self, name: str, *, include_deleted: bool = False) -> Category | None:
        # Misma logica que get_by_slug, pero buscando por el campo "name"
        # (el modelo Category tambien exige name unico, no solo slug).
        statement = select(Category).where(Category.name == name)
        if not include_deleted:
            statement = statement.where(Category.deleted_at.is_(None))
        return self.session.exec(statement).first()

    def get_many(self, category_ids: list[int]) -> list[Category]:
        """Non-deleted categories among the given ids — used to validate a
        game's `category_ids` before linking them.
        """
        # Si la lista de ids viene vacia, no hace falta ni consultar la
        # base de datos — la respuesta ya se sabe que es una lista vacia.
        if not category_ids:
            return []
        statement = select(Category).where(
            # .in_() arma un WHERE id IN (1, 2, 3, ...) — trae de un solo
            # viaje a la base de datos todas las categorias cuyo id este
            # en la lista recibida, en vez de consultar una por una.
            Category.id.in_(category_ids),
            # Se ignoran las categorias eliminadas: no tiene sentido dejar
            # que un juego quede asociado a una categoria que ya no existe
            # de cara al publico.
            Category.deleted_at.is_(None),
        )
        return list(self.session.exec(statement).all())
