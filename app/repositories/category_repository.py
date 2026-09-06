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
        statement = select(Category).order_by(Category.name)
        return list(self.session.exec(statement).all())

    def get_by_slug(self, slug: str, *, include_deleted: bool = False) -> Category | None:
        statement = select(Category).where(Category.slug == slug)
        if not include_deleted:
            statement = statement.where(Category.deleted_at.is_(None))
        return self.session.exec(statement).first()

    def get_by_name(self, name: str, *, include_deleted: bool = False) -> Category | None:
        statement = select(Category).where(Category.name == name)
        if not include_deleted:
            statement = statement.where(Category.deleted_at.is_(None))
        return self.session.exec(statement).first()

    def get_many(self, category_ids: list[int]) -> list[Category]:
        """Non-deleted categories among the given ids — used to validate a
        game's `category_ids` before linking them.
        """
        if not category_ids:
            return []
        statement = select(Category).where(
            Category.id.in_(category_ids), Category.deleted_at.is_(None)
        )
        return list(self.session.exec(statement).all())
