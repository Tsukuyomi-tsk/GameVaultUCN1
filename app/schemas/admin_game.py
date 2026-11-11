"""Request/response schemas for the admin game CRUD (Fase 4).

Separate from schemas/game.py on purpose: those are the public catalog's
shape (never leaks `is_active`/`deleted_at`/timestamps), these are the
backoffice's — an admin needs to see and set exactly the fields a shopper
never does.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import PatchSchema
from app.schemas.category import CategoryRead
from app.schemas.game import GameImageRead

# Patron (regex) que valida el formato de un slug: solo minusculas, digitos
# y guiones simples entre palabras (ej: "the-last-of-us"). No permite
# mayusculas, espacios, guion al principio/final ni guiones dobles.
_SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


# BaseModel de Pydantic: esta clase describe la FORMA que debe tener el
# JSON que un admin manda al crear un juego (POST /admin/games). FastAPI
# valida automaticamente el body de la request contra esta clase antes de
# que el codigo del router se ejecute siquiera.
class GameCreate(BaseModel):
    # Ejemplo que Swagger precarga en 'Try it out'. category_ids 1 y 2 existen tras sembrar la demo.
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "title": "Mi Juego de Prueba",
                    "slug": "mi-juego-de-prueba",
                    "description": "Un juego creado desde Swagger.",
                    "developer": "Estudio UCN",
                    "publisher": "UCN Games",
                    "platform": "PC",
                    "release_date": "2026-01-15",
                    "base_price": 19990,
                    "category_ids": [1, 2],
                }
            ]
        }
    )

    # Field(...) permite agregar validaciones extra ademas del tipo:
    # min_length/max_length limitan el largo del string.
    title: str = Field(min_length=1, max_length=255)
    # pattern aplica el regex de arriba: si el slug no matchea el formato,
    # FastAPI devuelve un 422 automaticamente, sin que el codigo del
    # servicio llegue a ejecutarse.
    slug: str = Field(min_length=1, max_length=280, pattern=_SLUG_PATTERN)
    # "str | None" + default=None: campo opcional. Si no viene en el JSON,
    # se guarda como None (equivalente a NULL en la base de datos).
    description: str | None = Field(default=None, max_length=4000)
    developer: str | None = Field(default=None, max_length=255)
    publisher: str | None = Field(default=None, max_length=255)
    platform: str = Field(min_length=1, max_length=100)
    release_date: date | None = None
    # gt=0: el precio tiene que ser estrictamente mayor a 0 (no se permite
    # un juego gratis con este endpoint, ni un precio negativo).
    # max_digits/decimal_places: limitan la precision del Decimal, igual
    # que la columna de la base de datos (10 digitos totales, 2 decimales).
    base_price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    # Lista de ids de categorias a asociar al juego. default_factory=list
    # (en vez de default=[]) evita el clasico bug de Python de compartir
    # una misma lista mutable entre distintas instancias del modelo.
    category_ids: list[int] = Field(default_factory=list)


class GameUpdate(PatchSchema):
    """Every field optional — the service applies only the keys actually
    present in the request body (`model_dump(exclude_unset=True)`), so a
    field left out is left untouched, never reset to null.
    """

    # Ejemplo: un PATCH manda solo lo que cambia.
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"base_price": 24990, "is_active": True}]}
    )

    # Campos que NO se pueden mandar como null (columna NOT NULL): PatchSchema
    # los rechaza con 422. description, developer, publisher y release_date
    # SI se pueden vaciar con null; category_ids=null equivale a omitirlo.
    non_nullable = frozenset({"title", "slug", "platform", "base_price", "is_active"})

    # Todos los campos son "X | None = None" — un PATCH parcial: el admin
    # solo manda los campos que quiere cambiar, y el resto se omite del
    # JSON directamente (no se manda como null, se OMITE del body).
    title: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=280, pattern=_SLUG_PATTERN)
    description: str | None = Field(default=None, max_length=4000)
    developer: str | None = Field(default=None, max_length=255)
    publisher: str | None = Field(default=None, max_length=255)
    platform: str | None = Field(default=None, min_length=1, max_length=100)
    release_date: date | None = None
    base_price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    is_active: bool | None = None
    # None aca significa "no tocar las categorias"; una lista vacia []
    # significa "sacar TODAS las categorias del juego" — son dos cosas
    # distintas, por eso no se puede usar default_factory=list como en
    # GameCreate (eso forzaria a que "no venia en el body" y "vino como
    # lista vacia" se vean igual, y no es lo que se quiere aca).
    category_ids: list[int] | None = None


class GameAdminListItem(BaseModel):
    """One row of GET /admin/games — inactive and soft-deleted games
    included, distinguished by `is_active`/`deleted_at`.
    """

    # Version "resumida" de un juego para la lista de admin — no trae
    # descripcion, categorias ni imagenes (eso queda para el detalle).
    id: int
    title: str
    slug: str
    platform: str
    base_price: Decimal
    is_active: bool
    # deleted_at != None es la señal de que el juego esta soft-deleted;
    # se expone tal cual para que el frontend de admin pueda mostrar un
    # "Eliminado" en la tabla.
    deleted_at: datetime | None
    created_at: datetime


class GameAdminPage(BaseModel):
    # Envoltorio de paginacion: la lista de juegos de ESTA pagina, mas los
    # datos necesarios para dibujar los controles de paginacion en el
    # frontend (pagina actual, tamaño de pagina, total de resultados y
    # total de paginas).
    items: list[GameAdminListItem]
    page: int
    size: int
    total: int
    pages: int


class GameAdminDetail(BaseModel):
    """Full admin view of one game — every column plus its images and
    categories, no catalog-only computed fields (final_price, etc.) since
    those only make sense for the public storefront.
    """

    # Version completa de un juego para el detalle de admin — todos los
    # campos de la tabla games, mas sus imagenes y categorias asociadas.
    # A diferencia del detalle publico (GameDetail en schemas/game.py),
    # NO incluye final_price/discount_percent/has_active_offer, porque
    # esos son conceptos de "precio para el comprador", no de "estado del
    # registro" — el admin ve el precio base tal cual esta guardado.
    id: int
    title: str
    slug: str
    description: str | None
    developer: str | None
    publisher: str | None
    platform: str
    release_date: date | None
    base_price: Decimal
    is_active: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    categories: list[CategoryRead]
    images: list[GameImageRead]
