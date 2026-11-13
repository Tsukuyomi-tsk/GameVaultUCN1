"""Request/response schemas for game reviews (Fase 6).

`ReviewRead` exposes the author's display name (`author_name`), never the
internal `user_id` — a public review list has no reason to reveal account
ids. The page envelope mirrors GamePage/OrderPage/UserPage.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewCreate(BaseModel):
    # Ejemplo precargado en Swagger.
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"rating": 5, "comment": "Excelente juego, lo recomiendo."}]
        }
    )

    # Puntaje de 1 a 5: Field(ge=1, le=5) hace que FastAPI responda 422
    # solo, sin codigo extra, si llega un 0 o un 6.
    rating: int = Field(ge=1, le=5)
    # El comentario es opcional (se puede dejar solo el puntaje) y no puede
    # pasar de 2000 caracteres, el mismo limite que tiene la columna.
    comment: str | None = Field(default=None, max_length=2000)


class ReviewUpdate(BaseModel):
    # Ejemplo precargado en Swagger.
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"rating": 4, "comment": "Mejor de lo que esperaba."}]}
    )

    """PATCH body: every field optional. Which ones the client actually sent
    is read with `model_dump(exclude_unset=True)` in the service, so an
    omitted field stays untouched while an explicit `"comment": null`
    clears the comment.
    """

    # Ambos campos son opcionales: en un PATCH el cliente manda solo lo que
    # quiere cambiar. Las mismas restricciones de ReviewCreate aplican
    # cuando el campo viene.
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class ReviewRead(BaseModel):
    id: int
    game_id: int
    # Nombre visible del autor (User.full_name), no su id interno.
    author_name: str
    rating: int
    comment: str | None
    created_at: datetime
    updated_at: datetime


class ReviewPage(BaseModel):
    # Mismo esquema de paginacion que GamePage/OrderPage: items de esta
    # pagina, mas los datos para que el cliente arme la navegacion.
    items: list[ReviewRead]
    page: int
    size: int
    total: int
    pages: int
