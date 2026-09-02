"""Generic repository providing the CRUD primitives every concrete
repository builds on. Routers and services never touch a Session or write
a query directly — every SELECT/INSERT/UPDATE/DELETE in the app funnels
through a repository.

Repositories never commit: a single business operation (e.g. checkout)
spans multiple repository calls inside one transaction, so committing here
would break atomicity. `add`/`delete` only flush (push SQL, run constraint
checks) — the service decides when to commit or roll back.
"""

from __future__ import annotations

from sqlmodel import Session, SQLModel, select


class BaseRepository[ModelType: SQLModel]:
    """CRUD primitives shared by every repository.

    Subclasses for a soft-deletable entity (one with a `deleted_at` column)
    get automatic exclusion of deleted rows from `get`/`list` unless
    `include_deleted=True` is passed explicitly — this is what keeps soft
    delete honest across the app instead of being re-implemented (or
    forgotten) in every repository method.
    """

    model: type[ModelType]

    def __init__(self, session: Session) -> None:
        self.session = session

    @property
    def _has_soft_delete(self) -> bool:
        return hasattr(self.model, "deleted_at")

    def get(self, id_: int, *, include_deleted: bool = False) -> ModelType | None:
        obj = self.session.get(self.model, id_)
        if obj is None:
            return None
        if not include_deleted and self._has_soft_delete and getattr(obj, "deleted_at", None):
            return None
        return obj

    def list(
        self, *, include_deleted: bool = False, offset: int = 0, limit: int = 100
    ) -> list[ModelType]:
        statement = select(self.model)
        if not include_deleted and self._has_soft_delete:
            statement = statement.where(self.model.deleted_at.is_(None))
        statement = statement.offset(offset).limit(limit)
        return list(self.session.exec(statement).all())

    def add(self, obj: ModelType) -> ModelType:
        self.session.add(obj)
        self.session.flush()
        self.session.refresh(obj)
        return obj

    def delete(self, obj: ModelType) -> None:
        """Hard delete.

        Soft-deletable entities are closed by their service (set
        `deleted_at`, then persist via `add`), not by calling this method —
        it exists for genuinely disposable rows (e.g. cart items) and for
        the maintenance jobs in app/jobs.
        """
        self.session.delete(obj)
        self.session.flush()
