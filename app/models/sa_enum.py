"""Helper for persisting a StrEnum column by its value, not its member name.

SQLAlchemy's `Enum` type defaults to storing a Python enum's `.name`
("ADMIN") rather than its `.value` ("admin"). Left alone, that makes the
raw database rows disagree with what the API actually returns — FastAPI
serializes StrEnum members by value. Every enum-backed column in this app
goes through this helper instead of a bare `Enum(...)`, so the two never
drift apart.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum
from sqlalchemy.types import TypeEngine


def str_enum_column(enum_cls: type[StrEnum], **kwargs: object) -> TypeEngine:
    """A SQLAlchemy Enum type that stores/reads `enum_cls` by `.value`."""
    return Enum(
        enum_cls,
        values_callable=lambda cls: [member.value for member in cls],
        **kwargs,
    )
