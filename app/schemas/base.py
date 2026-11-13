"""Shared base class for the PATCH (partial update) request schemas."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, model_validator


class PatchSchema(BaseModel):
    """Base for every `*Update` schema: rejects an explicit `null` on fields
    whose database column is NOT NULL.

    In a PATCH, "omit the field" means "leave it as is" and is fine. But the
    types are `X | None`, so Pydantic also accepts an explicit `"title": null`,
    and `model_dump(exclude_unset=True)` lets it through to the database,
    which fails with a 500. Here it becomes a clear 422 instead. Fields that
    CAN be emptied (description, developer...) are simply not listed.
    """

    # Cada subclase lista aca los campos que NO aceptan null. ClassVar le
    # dice a Pydantic que esto es un dato de la clase, no un campo del JSON.
    non_nullable: ClassVar[frozenset[str]] = frozenset()

    # Hook de Pydantic: corre UNA vez cuando se define cada subclase (al
    # importar el modulo), con los campos ya construidos en model_fields.
    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        # Nombres de non_nullable que no son campos del schema (un typo).
        unknown = sorted(cls.non_nullable - cls.model_fields.keys())
        if unknown:
            # Sin esto, un typo desactivaria la proteccion en silencio: mejor
            # que la app ni arranque (falla al importar, no en un PATCH).
            raise TypeError(
                f"{cls.__name__}.non_nullable lista campos que no existen: {', '.join(unknown)}"
            )

    @model_validator(mode="after")
    def _reject_explicit_null(self) -> PatchSchema:
        # model_fields_set = los campos que el cliente SI mando en el JSON
        # (los omitidos no estan). Si uno de los NOT NULL esta ahi pero su
        # valor es None, vino como "campo": null explicito.
        nulls = sorted(
            name
            for name in self.model_fields_set & self.non_nullable
            if getattr(self, name) is None
        )
        if nulls:
            # ValueError => FastAPI responde 422 con el sobre de error estandar.
            raise ValueError(
                f"Los campos no pueden ser null: {', '.join(nulls)}. "
                "Omitelos del body si no quieres modificarlos."
            )
        return self
