"""Database engine and session management.

The SQLModel naming convention is set here, at import time, before any model
or Alembic revision is generated: SQLite migrations rely on Alembic's batch
mode, which needs every constraint to have a predictable name to be able to
recreate it. Setting this after the first revision would force redoing the
migration history — see the plan's "Riesgos conocidos".
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

SQLModel.metadata.naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        """Enforce FKs on every new connection.

        SQLite ships with foreign_keys=OFF by default, which silently
        disables every ON DELETE CASCADE/SET NULL/RESTRICT declared on the
        models (see app/models) unless this pragma is set per connection.
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped database session."""
    with Session(engine) as session:
        yield session
