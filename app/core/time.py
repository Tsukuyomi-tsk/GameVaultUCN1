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


def utcnow() -> datetime:
    """Current time in UTC, returned as a naive datetime."""
    return datetime.now(UTC).replace(tzinfo=None)
