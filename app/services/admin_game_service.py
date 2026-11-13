"""Business logic for the admin game backoffice (Fase 4): CRUD, soft
delete/restore, and catalog image management.

Uniqueness (slug) and category-id validity need a database read, so they
live here rather than in the request schema — same split the rest of the
app already follows (see auth_service.register for the same pattern with
email uniqueness).
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.core.time import utcnow
from app.integrations import cloudinary_client
from app.models import Game, GameImage
from app.repositories.category_repository import CategoryRepository
from app.repositories.game_image_repository import GameImageRepository
from app.repositories.game_repository import GameAdminRow, GameRepository
from app.schemas.admin_game import GameCreate, GameUpdate


def _validate_category_ids(categories: CategoryRepository, category_ids: list[int]) -> None:
    # Funcion privada (el "_" al principio es la convencion de Python
    # para "esto es interno de este archivo, no lo importes desde otro
    # lado") que reutilizan tanto create_game como update_game.
    if not category_ids:
        # Lista vacia: no hay nada que validar, se corta aca.
        return
    # Trae de la base de datos las categorias que SI existen (y no estan
    # eliminadas) entre los ids pedidos.
    found = categories.get_many(category_ids)
    # Resta de conjuntos: category_ids (lo que se pidio) menos los ids que
    # realmente se encontraron = los ids que NO existen o estan eliminados.
    missing = set(category_ids) - {c.id for c in found}
    if missing:
        # Si sobro algo en "missing", se corta la operacion con un error
        # claro que lista exactamente que ids fallaron (mas facil de
        # depurar para el admin que un error generico).
        raise ValidationError(f"Categorias invalidas: {sorted(missing)}")


def list_games(
    session: Session, *, q: str | None, page: int, size: int
) -> tuple[list[Game], int, int]:
    # Se crea el repositorio "envolviendo" la sesion de base de datos
    # actual — cada request tiene su propia sesion (ver get_session en
    # core/database.py), asi que este repositorio vive solo mientras dura
    # el request.
    games = GameRepository(session)
    # Convierte "pagina N de tamaño size" a "saltar tantas filas" (offset).
    # Ej: pagina 1 -> offset 0; pagina 2 con size=20 -> offset 20.
    offset = (page - 1) * size
    items, total = games.list_admin(q=q, offset=offset, limit=size)
    # Calcula cuantas paginas hay en total redondeando hacia arriba (si
    # hay 21 juegos y el tamaño de pagina es 20, hacen falta 2 paginas,
    # no 1). Si total es 0, se evita la division y se devuelve 0 paginas
    # directamente.
    pages = (total + size - 1) // size if total else 0
    return items, total, pages


def get_game(session: Session, *, game_id: int) -> GameAdminRow:
    games = GameRepository(session)
    # include_deleted=True: a diferencia del catalogo publico, el admin
    # tiene que poder ver el detalle de un juego aunque este soft-deleted
    # (por ejemplo, para decidir si restaurarlo).
    game = games.get(game_id, include_deleted=True)
    if game is None:
        # Ni siquiera existe la fila en la base de datos (id inventado) ->
        # 404, distinto del caso "existe pero esta eliminado" (ese SI
        # se puede ver, por el include_deleted=True de arriba).
        raise NotFoundError("Juego no encontrado.")
    # Arma la respuesta completa (juego + imagenes + categorias) en un
    # solo viaje de logica, reutilizando el metodo del repositorio.
    return games.load_admin_row(game)


def create_game(session: Session, *, payload: GameCreate) -> GameAdminRow:
    games = GameRepository(session)
    categories = CategoryRepository(session)

    # Chequeo de unicidad de slug ANTES de intentar insertar — asi se
    # puede devolver un error de negocio claro (422) en vez de dejar que
    # la base de datos reviente con un error de constraint UNIQUE, que
    # seria mucho menos informativo para quien consuma la API.
    if games.get_by_slug(payload.slug, include_deleted=True) is not None:
        raise ValidationError("Ya existe un juego con ese slug.")
    # Valida que todas las categorias pedidas existan de verdad, antes de
    # crear el juego (asi no se crea un juego "a medias" si alguna
    # categoria es invalida).
    _validate_category_ids(categories, payload.category_ids)

    try:
        # Construye el objeto Game (todavia sin id, sin guardar) copiando
        # cada campo del payload validado por Pydantic.
        game = games.add(
            Game(
                title=payload.title,
                slug=payload.slug,
                description=payload.description,
                developer=payload.developer,
                publisher=payload.publisher,
                platform=payload.platform,
                release_date=payload.release_date,
                base_price=payload.base_price,
            )
        )
        # games.add() ya hizo flush() y refresh(), asi que en este punto
        # game.id ya existe (la base de datos ya le asigno un id
        # autoincremental) aunque la transaccion todavia no este
        # confirmada (commit).
        games.set_categories(game.id, payload.category_ids)
        # commit(): recien ACA se confirma la transaccion completa (el
        # juego nuevo + sus vinculos de categoria) de forma atomica — si
        # algo hubiera fallado antes de esta linea, nada se habria
        # guardado.
        session.commit()
    except IntegrityError:
        # Dos admins crearon el mismo slug a la vez: ambos pasaron el
        # chequeo de arriba y el UNIQUE de la base de datos desempato. Se
        # deshace este intento y se repite el chequeo, que ahora SI
        # encuentra a la ganadora y responde con el mensaje de siempre
        # (422) en vez de un 500.
        session.rollback()
        if games.get_by_slug(payload.slug, include_deleted=True) is not None:
            raise ValidationError("Ya existe un juego con ese slug.") from None
        raise
    # refresh() vuelve a leer el objeto desde la base de datos, por si
    # algun campo se genero o modifico del lado del servidor (por ejemplo,
    # created_at/updated_at con su valor por defecto).
    session.refresh(game)
    return games.load_admin_row(game)


def update_game(session: Session, *, game_id: int, payload: GameUpdate) -> GameAdminRow:
    games = GameRepository(session)
    categories = CategoryRepository(session)

    game = games.get(game_id, include_deleted=True)
    if game is None:
        raise NotFoundError("Juego no encontrado.")

    # exclude_unset=True es la clave de un PATCH parcial: model_dump()
    # normalmente convertiria TODOS los campos del schema a un dict
    # (incluidos los que quedaron en None por default), pero con
    # exclude_unset=True solo aparecen los campos que el cliente
    # realmente mando en el JSON. Asi un campo omitido nunca se pisa.
    data = payload.model_dump(exclude_unset=True)
    # category_ids se maneja aparte (no es una columna de la tabla games,
    # es una relacion) — se saca del dict con pop() para que el for de
    # abajo no intente hacer game.category_ids = [...] (eso no existe
    # como atributo directo del modelo Game).
    category_ids = data.pop("category_ids", None)

    # Si el slug esta cambiando de verdad (vino en el body Y es distinto
    # al que ya tenia el juego), hay que re-chequear que el nuevo valor
    # no este ya tomado por OTRO juego.
    if "slug" in data and data["slug"] != game.slug:
        existing = games.get_by_slug(data["slug"], include_deleted=True)
        # existing.id != game.id: si el slug "ya existe" pero pertenece
        # justamente a este mismo juego, no es un conflicto real.
        if existing is not None and existing.id != game.id:
            raise ValidationError("Ya existe un juego con ese slug.")

    # Aplica cada campo presente en el body directamente sobre el objeto
    # ya cargado desde la base de datos. setattr(objeto, "titulo", "X")
    # es lo mismo que escribir objeto.titulo = "X", pero permite usar el
    # nombre del campo como una variable (viene del dict).
    for field, value in data.items():
        setattr(game, field, value)

    # Vuelve a agregar el objeto modificado a la sesion — SQLAlchemy ya
    # sabe que esta fila existe (tiene id), asi que esto se traduce en un
    # UPDATE, no en un INSERT nuevo.
    try:
        games.add(game)
        # Solo se tocan las categorias si category_ids vino explicito en el
        # body (None = "no cambiar categorias", ver el comentario en
        # schemas/admin_game.py sobre por que no se usa una lista vacia
        # como valor por defecto).
        if category_ids is not None:
            _validate_category_ids(categories, category_ids)
            games.set_categories(game.id, category_ids)
        session.commit()
    except IntegrityError:
        # Misma carrera que en create_game: otro admin tomo el slug entre
        # el chequeo y el UPDATE.
        session.rollback()
        new_slug = data.get("slug")
        existing = games.get_by_slug(new_slug, include_deleted=True) if new_slug else None
        if existing is not None and existing.id != game_id:
            raise ValidationError("Ya existe un juego con ese slug.") from None
        raise
    session.refresh(game)
    return games.load_admin_row(game)


def soft_delete_game(session: Session, *, game_id: int) -> None:
    games = GameRepository(session)
    game = games.get(game_id, include_deleted=True)
    if game is None:
        raise NotFoundError("Juego no encontrado.")
    if game.deleted_at is not None:
        # El juego ya estaba eliminado: no se hace nada mas. DELETE es
        # idempotente a proposito — llamarlo dos veces seguidas no es un
        # error, el resultado final (juego eliminado) es el mismo.
        return
    # Soft delete real: en vez de borrar la fila, se le pone fecha/hora al
    # campo deleted_at. Un juego con deleted_at != None deja de aparecer
    # en el catalogo publico (ver game_repository.search()), pero la fila
    # sigue existiendo en la base de datos.
    game.deleted_at = utcnow()
    games.add(game)
    session.commit()


def restore_game(session: Session, *, game_id: int) -> GameAdminRow:
    games = GameRepository(session)
    game = games.get(game_id, include_deleted=True)
    if game is None:
        raise NotFoundError("Juego no encontrado.")
    if game.deleted_at is not None:
        # Solo hay algo que hacer si el juego estaba efectivamente
        # eliminado — restaurar consiste en volver deleted_at a None.
        game.deleted_at = None
        games.add(game)
        session.commit()
        session.refresh(game)
    # Si el juego NO estaba eliminado, este return simplemente devuelve su
    # estado actual sin tocar nada — restaurar algo que ya esta activo
    # tambien es una operacion idempotente.
    return games.load_admin_row(game)


def add_game_image(
    session: Session,
    *,
    game_id: int,
    filename: str,
    content: bytes,
    content_type: str | None,
    is_cover: bool,
) -> GameImage:
    games = GameRepository(session)
    images = GameImageRepository(session)

    game = games.get(game_id, include_deleted=True)
    if game is None:
        raise NotFoundError("Juego no encontrado.")
    # Validacion basica de que el archivo subido sea realmente una imagen:
    # content_type es el "Content-Type" que el navegador/cliente mando
    # junto con el archivo (ej: "image/png", "image/jpeg"). Si no empieza
    # con "image/", se rechaza antes de gastar tiempo subiendolo a
    # Cloudinary (o guardarlo en disco).
    if not content_type or not content_type.startswith("image/"):
        raise ValidationError("El archivo debe ser una imagen.")

    # Delega la subida real (a Cloudinary o al disco local, segun haya
    # credenciales) al modulo de integracion — este servicio no sabe ni
    # le importa CUAL de los dos backends se uso.
    url, public_id = cloudinary_client.upload_image(
        game_id=game_id, filename=filename, content=content
    )

    if is_cover:
        # Si esta nueva imagen va a ser la portada, primero hay que
        # "apagar" la bandera is_cover de cualquier otra imagen del mismo
        # juego — nunca puede haber dos portadas al mismo tiempo.
        images.clear_cover(game_id)

    # El nuevo sort_order es simplemente "cuantas imagenes tenia antes" —
    # asi las imagenes quedan ordenadas en el orden en que se subieron.
    existing_count = len(images.list_for_game(game_id))
    image = images.add(
        GameImage(
            game_id=game_id,
            url=url,
            public_id=public_id,
            is_cover=is_cover,
            sort_order=existing_count,
        )
    )
    session.commit()
    session.refresh(image)
    return image


def delete_game_image(session: Session, *, game_id: int, image_id: int) -> None:
    images = GameImageRepository(session)
    image = images.get(image_id)
    # Dos formas de fallar se tratan igual (mismo error 404):
    # 1) la imagen directamente no existe.
    # 2) la imagen existe, pero pertenece a OTRO juego (alguien mando un
    #    image_id valido pero de un juego distinto al de la URL) — no se
    #    distingue este caso del anterior para no dar pistas de que ids
    #    de imagen existen en el sistema.
    if image is None or image.game_id != game_id:
        raise NotFoundError("Imagen no encontrada.")

    # Primero se borra el archivo real (Cloudinary o disco local)...
    cloudinary_client.delete_image(image.public_id)
    # ...y despues la fila de la base de datos. Si el archivo remoto ya no
    # existiera (por ejemplo, borrado a mano), delete_image() no revienta
    # (ver el manejo de missing_ok en cloudinary_client.py).
    images.delete(image)
    session.commit()
