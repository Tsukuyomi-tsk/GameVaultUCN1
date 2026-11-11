"""Admin game backoffice: CRUD, soft delete/restore, catalog images.

Every route requires AdminUser — see the plan's "Modelo de autorizacion".
Like every other router, this only translates HTTP <-> Python; every rule
lives in app.services.admin_game_service.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import AdminUser
from app.schemas.admin_game import (
    GameAdminDetail,
    GameAdminListItem,
    GameAdminPage,
    GameCreate,
    GameUpdate,
)
from app.schemas.category import CategoryRead
from app.schemas.errors import ADMIN_RESPONSES, errors
from app.schemas.game import GameImageRead
from app.services import admin_game_service

# prefix="/admin/games": todas las rutas de este router quedan bajo ese
# prefijo automaticamente (no hace falta repetirlo en cada @router.get/post).
# tags=["admin-games"] es solo para agrupar visualmente estos endpoints en
# la documentacion automatica de /docs.
router = APIRouter(prefix="/admin/games", tags=["admin-games"], responses=ADMIN_RESPONSES)

# Alias reutilizable: en vez de escribir "Annotated[Session, Depends(get_session)]"
# en cada funcion, se usa este nombre corto. Depends(get_session) le dice a
# FastAPI "antes de ejecutar esta ruta, llama a get_session() y pasame lo
# que devuelva como este parametro" — asi cada request obtiene su propia
# sesion de base de datos.
SessionDep = Annotated[Session, Depends(get_session)]


def _to_detail(row) -> GameAdminDetail:
    # Funcion privada que arma la respuesta GameAdminDetail a partir de un
    # GameAdminRow (el "paquete" juego+imagenes+categorias que devuelve el
    # repositorio) — se reutiliza en 4 endpoints distintos (get, create,
    # update, restore) para no repetir este mapeo 4 veces.
    game = row.game
    return GameAdminDetail(
        id=game.id,
        title=game.title,
        slug=game.slug,
        description=game.description,
        developer=game.developer,
        publisher=game.publisher,
        platform=game.platform,
        release_date=game.release_date,
        base_price=game.base_price,
        is_active=game.is_active,
        deleted_at=game.deleted_at,
        created_at=game.created_at,
        updated_at=game.updated_at,
        # Convierte cada objeto Category/GameImage del ORM a su schema
        # Pydantic correspondiente — nunca se devuelve un objeto del ORM
        # directamente desde un router (regla de arquitectura del proyecto).
        categories=[CategoryRead.model_validate(c) for c in row.categories],
        images=[GameImageRead.model_validate(i) for i in row.images],
    )


# GET /admin/games — listado paginado.
@router.get(
    "",
    response_model=GameAdminPage,
    summary="Listar juegos (admin)",
    description=(
        "Listado paginado con **todos** los juegos, incluidos inactivos y eliminados "
        "(`deleted_at` distinto de null). `q` busca en titulo y descripcion."
    ),
    responses=errors(422),
)
def list_games(
    session: SessionDep,
    # AdminUser es una dependencia de FastAPI que exige un JWT valido de
    # un usuario con rol "admin" — si no se cumple, FastAPI corta la
    # ejecucion con 401/403 ANTES de que el cuerpo de esta funcion
    # siquiera empiece a correr. El nombre empieza con "_" porque esta
    # funcion no necesita USAR el objeto admin, solo exigir que exista.
    _admin: AdminUser,
    # Query params opcionales, con sus valores por defecto:
    q: str | None = None,
    # Query(ge=1): ademas del tipo int, exige que sea >= 1 (no se permite
    # pedir la "pagina 0" ni paginas negativas).
    page: Annotated[int, Query(ge=1)] = 1,
    # Query(ge=1, le=100): tamaño de pagina entre 1 y 100 — evita que
    # alguien pida size=999999 y sobrecargue la base de datos de un tiron.
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> GameAdminPage:
    # Toda la logica real (consulta, paginacion) vive en el servicio; el
    # router solo la invoca con los parametros ya validados.
    items, total, pages = admin_game_service.list_games(session, q=q, page=page, size=size)
    return GameAdminPage(
        # List comprehension: arma una lista de GameAdminListItem, uno por
        # cada juego (g) que devolvio el servicio, tomando solo los campos
        # que ese schema necesita (mas liviano que el detalle completo).
        items=[
            GameAdminListItem(
                id=g.id,
                title=g.title,
                slug=g.slug,
                platform=g.platform,
                base_price=g.base_price,
                is_active=g.is_active,
                deleted_at=g.deleted_at,
                created_at=g.created_at,
            )
            for g in items
        ],
        page=page,
        size=size,
        total=total,
        pages=pages,
    )


# GET /admin/games/{game_id} — detalle de un juego puntual.
@router.get(
    "/{game_id}",
    response_model=GameAdminDetail,
    summary="Ver un juego (admin)",
    description="Todos los campos de un juego, con sus categorias e imagenes.",
    responses=errors((404, "El juego no existe."), 422),
)
def get_game(game_id: int, session: SessionDep, _admin: AdminUser) -> GameAdminDetail:
    # game_id se toma automaticamente del segmento {game_id} de la URL —
    # FastAPI lo convierte a int y, si no es un numero valido, devuelve un
    # 422 sin que este codigo llegue a ejecutarse.
    row = admin_game_service.get_game(session, game_id=game_id)
    return _to_detail(row)


# POST /admin/games — crear un juego nuevo. status_code=201 (Created) es
# el codigo HTTP convencional para "se creo un recurso nuevo con exito".
@router.post(
    "",
    response_model=GameAdminDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un juego",
    description=(
        "Crea un juego. El `slug` (minusculas, numeros y guiones) debe ser unico y las "
        "`category_ids` deben existir (ve los ids en `GET /admin/categories`)."
    ),
    responses=errors((422, "Datos invalidos, `slug` repetido o `category_ids` inexistentes.")),
)
def create_game(payload: GameCreate, session: SessionDep, _admin: AdminUser) -> GameAdminDetail:
    # payload: FastAPI ya parseo y valido el JSON del body contra el
    # schema GameCreate antes de que esta funcion se ejecute — si el body
    # no cumple las reglas de GameCreate (campos faltantes, slug con
    # formato invalido, etc.), nunca se llega hasta aca.
    row = admin_game_service.create_game(session, payload=payload)
    return _to_detail(row)


# PATCH /admin/games/{game_id} — actualizacion parcial.
@router.patch(
    "/{game_id}",
    response_model=GameAdminDetail,
    summary="Editar un juego",
    description=(
        "Actualizacion parcial: manda solo los campos a cambiar. `title`, `slug`, `platform`, "
        "`base_price` e `is_active` no aceptan `null`; `description`, `developer`, `publisher` "
        "y `release_date` si (los vacian). `category_ids: []` quita todas las categorias; "
        "omitir `category_ids` no las toca."
    ),
    responses=errors(
        (404, "El juego no existe."),
        (422, "Datos invalidos, `null` en un campo obligatorio o `slug` repetido."),
    ),
)
def update_game(
    game_id: int, payload: GameUpdate, session: SessionDep, _admin: AdminUser
) -> GameAdminDetail:
    row = admin_game_service.update_game(session, game_id=game_id, payload=payload)
    return _to_detail(row)


# DELETE /admin/games/{game_id} — soft delete. 204 No Content: la
# operacion fue exitosa pero no hay nada que devolver en el body (por eso
# la funcion devuelve None y no un schema).
@router.delete(
    "/{game_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un juego (borrado logico)",
    description=(
        "Marca el juego como eliminado: desaparece del catalogo pero se conserva en el "
        "historial de pedidos. Se puede deshacer con `/restore`."
    ),
    responses=errors((404, "El juego no existe."), 422),
)
def delete_game(game_id: int, session: SessionDep, _admin: AdminUser) -> None:
    admin_game_service.soft_delete_game(session, game_id=game_id)


# POST /admin/games/{game_id}/restore — deshace el soft delete.
@router.post(
    "/{game_id}/restore",
    response_model=GameAdminDetail,
    summary="Restaurar un juego eliminado",
    description="Deshace el borrado logico del juego.",
    responses=errors((404, "El juego no existe."), 422),
)
def restore_game(game_id: int, session: SessionDep, _admin: AdminUser) -> GameAdminDetail:
    row = admin_game_service.restore_game(session, game_id=game_id)
    return _to_detail(row)


# POST /admin/games/{game_id}/images — subir una imagen para el juego.
# "async def" (en vez de "def"): esta funcion usa "await" adentro (para
# leer el archivo subido), asi que tiene que declararse como corutina
# asincrona — FastAPI soporta ambos estilos (sync y async) en sus rutas.
@router.post(
    "/{game_id}/images",
    response_model=GameImageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Subir una imagen del juego",
    description=(
        "Sube un archivo de imagen (formulario `multipart/form-data`; en Swagger usa el "
        "boton de elegir archivo). Con `is_cover=true` pasa a ser la portada. **Modo dev:** "
        "sin credenciales de Cloudinary la imagen se guarda en `./media/`."
    ),
    responses=errors(
        (404, "El juego no existe."), (422, "No se envio un archivo o no es una imagen.")
    ),
)
async def upload_game_image(
    game_id: int,
    session: SessionDep,
    _admin: AdminUser,
    # File(): le dice a FastAPI que este parametro viene de un archivo
    # subido en un formulario multipart (no de JSON) — UploadFile es un
    # objeto que da acceso al nombre, tipo de contenido y a los bytes del
    # archivo sin cargarlo entero en memoria de entrada.
    file: Annotated[UploadFile, File()],
    # Form(): este parametro tambien viene del formulario multipart (no
    # del JSON ni de la URL) — es un campo de texto normal que viaja junto
    # con el archivo en el mismo request.
    is_cover: Annotated[bool, Form()] = False,
) -> GameImageRead:
    # await file.read(): lee TODO el contenido del archivo subido y lo
    # trae a memoria como bytes crudos — recien ahi se puede pasar al
    # servicio (que a su vez se lo pasa a cloudinary_client).
    content = await file.read()
    image = admin_game_service.add_game_image(
        session,
        game_id=game_id,
        # file.filename puede venir vacio segun el cliente; "image" es un
        # nombre de respaldo para no dejar el campo vacio.
        filename=file.filename or "image",
        content=content,
        content_type=file.content_type,
        is_cover=is_cover,
    )
    return GameImageRead.model_validate(image)


# DELETE /admin/games/{game_id}/images/{image_id} — borra una imagen
# puntual (tanto el archivo real como la fila en la base de datos).
@router.delete(
    "/{game_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar una imagen del juego",
    description="Borra la imagen (el archivo real y su registro).",
    responses=errors((404, "El juego o la imagen no existen."), 422),
)
def delete_game_image(game_id: int, image_id: int, session: SessionDep, _admin: AdminUser) -> None:
    admin_game_service.delete_game_image(session, game_id=game_id, image_id=image_id)
