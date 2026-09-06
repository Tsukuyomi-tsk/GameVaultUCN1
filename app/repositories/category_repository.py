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
