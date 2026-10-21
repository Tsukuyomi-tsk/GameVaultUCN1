"""Timezone-aware "now", normalized to a naive UTC datetime.

SQLite has no native timezone-aware datetime type: SQLAlchemy round-trips a
tz-aware value as naive on read-back, so comparing a freshly created
`datetime.now(timezone.utc)` against a value just read from the database
raises "can't compare offset-naive and offset-aware datetimes". Every
timestamp in this project is therefore naive-but-always-UTC, by convention.

Never call `datetime.now()` or the deprecated `datetime.utcnow()` directly
anywhere else in the codebase — always import `utcnow` from here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator


def utcnow() -> datetime:
    """Current time in UTC, returned as a naive datetime."""
    return datetime.now(UTC).replace(tzinfo=None)


def to_utc_naive(value: datetime) -> datetime:
    """Convert any incoming datetime to the project's naive-UTC convention.

    A value with a timezone ("...Z", "...-03:00") is converted to UTC and the
    tzinfo is dropped, so the INSTANT is preserved; a value without timezone
    is assumed to be UTC already and returned as is.
    """
    # tzinfo None = el cliente no mando zona: se asume UTC, igual que utcnow().
    if value.tzinfo is None:
        return value
    # astimezone(UTC) mueve la hora al equivalente en UTC; replace(tzinfo=None)
    # la deja "naive" para poder compararla con las columnas de SQLite.
    return value.astimezone(UTC).replace(tzinfo=None)


# Tipo reutilizable para cualquier fecha que llegue de un cliente (body o
# query): Pydantic la parsea y luego to_utc_naive la normaliza.
UtcNaiveDatetime = Annotated[datetime, AfterValidator(to_utc_naive)]
