"""Alembic environment.

The connection string comes from app.core.config.settings (DATABASE_URL in
.env), never from alembic.ini — see the comment left there. `render_as_batch`
is required for SQLite: it has no real ALTER TABLE, so Alembic recreates the
table under the hood to apply a change, and doing that safely needs every
constraint to already have a predictable name (see
app.core.database.SQLModel.metadata.naming_convention, which is why
`app.models` — not just `app.core.database` — must be imported before
`target_metadata` is read below.
"""

from logging.config import fileConfig

from alembic import context
from sqlmodel import SQLModel

# Populates SQLModel.metadata with every table (see app/models/__init__.py)
# and sets the naming convention as a side effect of importing app.core.database.
import app.models  # noqa: E402, F401
from app.core.config import settings
from app.core.database import engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live database connection."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection.

    Reuses the same engine as the running app (app.core.database.engine)
    instead of building a second one from alembic.ini, so migrations and
    the app always agree on connection settings.
    """
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
