"""Request/response schemas for the admin category CRUD (Fase 4)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import PatchSchema

_SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class CategoryCreate(BaseModel):
    # Forma del JSON esperado en POST /admin/categories — los 3 campos que
    # tiene el modelo Category, sin id (lo genera la base de datos) y sin
    # deleted_at (una categoria recien creada nunca nace eliminada).
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=120, pattern=_SLUG_PATTERN)
    description: str | None = Field(default=None, max_length=500)


class CategoryUpdate(PatchSchema):
    # name y slug son NOT NULL: un null explicito se rechaza con 422.
    non_nullable = frozenset({"name", "slug"})

    # Igual que GameUpdate: todo opcional, para un PATCH parcial. Si un
    # campo no viene en el JSON, el servicio no lo toca.
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, min_length=1, max_length=120, pattern=_SLUG_PATTERN)
    description: str | None = Field(default=None, max_length=500)


class CategoryAdminRead(BaseModel):
    # from_attributes=True le dice a Pydantic que puede construir esta
    # clase leyendo ATRIBUTOS de un objeto (como el Category del ORM,
    # category.name, category.slug, etc.) en vez de solo aceptar un dict
    # — asi router puede hacer CategoryAdminRead.model_validate(category)
    # directamente sobre el objeto que devuelve el repositorio.
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None
    # A diferencia de CategoryRead (schemas/category.py, la version
    # publica), esta SI expone deleted_at — el admin necesita verlo para
    # saber que categorias puede restaurar.
    deleted_at: datetime | None
