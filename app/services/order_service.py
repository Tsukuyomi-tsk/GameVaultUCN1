"""Business logic for checkout, order history and the owned-games library
(Fase 5).

Checkout idempotency has two paths, both keyed on Order's
(user_id, idempotency_key) UniqueConstraint (see order.py's docstring and
the plan's "Idempotencia de checkout"):

- Sequential retry: a client resends the same request after already getting
  a response. `checkout` re-queries by idempotency_key *before* doing any
  work and returns the existing order untouched.
- Concurrent retry: two requests with the same key both pass that first
  check (neither has committed yet) and both try to build an order. The
  loser's insert/commit raises IntegrityError on the UniqueConstraint; it
  rolls back and re-reads the winner's order instead of failing.

`generate_and_send_receipt` runs from a FastAPI BackgroundTasks callback,
strictly after the checkout response has already been sent — it opens its
own database session because the request-scoped one is closed by then.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.database import engine
from app.core.dependencies import ensure_owner_or_admin
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import log_event
from app.core.time import utcnow
from app.integrations.pdf_client import generate_receipt_pdf
from app.integrations.resend_client import send_receipt_email
from app.models import Game, LibraryItem, Order, OrderItem, User
from app.repositories.cart_repository import CartRepository
from app.repositories.game_repository import GameRepository
from app.repositories.library_repository import LibraryRepository
from app.repositories.offer_repository import compute_effective_price, get_active_offer_for_game
from app.repositories.order_repository import OrderRepository
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# Cuantas veces se intenta generar un order_code que todavia no exista
# antes de darse por vencido (ver _generate_unique_order_code).
_ORDER_CODE_ATTEMPTS = 5


def _generate_unique_order_code(orders: OrderRepository, *, now: datetime) -> str:
    for _ in range(_ORDER_CODE_ATTEMPTS):
        # Formato: GV-<fecha>-<8 caracteres hex al azar>, ej.
        # "GV-20260914-8CFFC6C4". secrets.token_hex (no random) porque es
        # criptograficamente seguro, igual que el resto de los valores
        # sensibles del proyecto (ver core/security.py).
        candidate = f"GV-{now.strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"
        # Se verifica que nadie mas tenga YA ese codigo antes de usarlo —
        # con 8 caracteres hex al azar una colision es astronomicamente
        # improbable, pero el chequeo es barato y elimina la duda.
        if orders.get_by_code(candidate) is None:
            return candidate
    # Si esto pasa, algo mas anda mal (ej. un bug generando siempre el
    # mismo valor) — se prefiere fallar ruidosamente antes que guardar una
    # orden con un codigo posiblemente duplicado.
    raise RuntimeError("No se pudo generar un order_code unico tras varios intentos.")


def checkout(
    session: Session, *, user: User, idempotency_key: str
) -> tuple[Order, list[OrderItem]]:
    orders = OrderRepository(session)

    # Camino secuencial: si esta misma clave ya produjo una orden antes
    # (reintento del cliente tras, por ejemplo, perder la respuesta por un
    # timeout de red), se devuelve esa orden tal cual, sin tocar nada mas.
    existing = orders.get_by_idempotency(user_id=user.id, idempotency_key=idempotency_key)
    if existing is not None:
        # Un reintento legitimo (no una compra nueva): se deja constancia
        # para poder distinguir en los logs "compro" de "reintento".
        log_event(
            logger,
            "checkout_replayed",
            user_id=user.id,
            order_code=existing.order_code,
            path="sequential",
        )
        return existing, orders.list_items(existing.id)

    # Se resuelve el carrito del usuario y se listan sus items (cada uno
    # con su Game asociado, ver CartRepository.list_items_with_games).
    carts = CartRepository(session)
    cart = carts.get_by_user(user.id)
    cart_rows = carts.list_items_with_games(cart.id) if cart is not None else []
    if not cart_rows:
        # Un carrito vacio (o inexistente) no es un 404 — es una violacion
        # de una regla de negocio ("no se puede pagar la nada"), asi que se
        # usa ValidationError (422), no NotFoundError.
        raise ValidationError("El carrito esta vacio.")

    games = GameRepository(session)
    library = LibraryRepository(session)
    now = utcnow()

    subtotal = Decimal("0.00")
    total = Decimal("0.00")
    # Los OrderItem se arman en memoria primero, y solo se persisten
    # despues de que CADA item del carrito paso todas las validaciones —
    # asi un solo item invalido corta el checkout ENTERO antes de escribir
    # nada en la base de datos.
    pending_items: list[OrderItem] = []

    for _cart_item, cart_game in cart_rows:
        # Revalidacion completa contra el ULTIMO estado en base de datos —
        # nunca se confia en el precio que el carrito venia mostrando, que
        # pudo quedar viejo si una oferta cambio (o el juego se desactivo)
        # mientras tanto. games.get() vuelve a consultar la tabla games en
        # vez de reusar el objeto `cart_game` que ya se tenia en memoria.
        fresh_game = games.get(cart_game.id)
        if fresh_game is None or not fresh_game.is_active:
            raise ConflictError(f"El juego '{cart_game.title}' ya no esta disponible para compra.")
        # No se puede comprar dos veces el mismo juego — si ya esta en la
        # biblioteca del usuario, se corta el checkout completo (no solo se
        # salta ese item), para que el cliente decida que hacer con el
        # carrito antes de reintentar.
        if library.owns(user_id=user.id, game_id=fresh_game.id):
            raise ConflictError(f"Ya posees '{fresh_game.title}' en tu biblioteca.")

        # Mismo calculo de precio que el catalogo y el carrito — nunca se
        # re-deriva el descuento a mano.
        offer = get_active_offer_for_game(session, fresh_game.id, now)
        final_price, discount_percent = compute_effective_price(fresh_game.base_price, offer)

        subtotal += fresh_game.base_price
        total += final_price
        # OrderItem "congela" el titulo/slug/precio de ESTE momento — ver
        # order_item.py: estos valores nunca cambian aunque el catalogo
        # cambie despues.
        pending_items.append(
            OrderItem(
                game_id=fresh_game.id,
                title_snapshot=fresh_game.title,
                slug_snapshot=fresh_game.slug,
                unit_price=fresh_game.base_price,
                discount_percent=discount_percent,
                final_price=final_price,
            )
        )

    # Recien aca, con TODOS los items ya validados, se arma la orden.
    order = Order(
        order_code=_generate_unique_order_code(orders, now=now),
        user_id=user.id,
        subtotal=subtotal,
        discount_total=subtotal - total,
        total=total,
        idempotency_key=idempotency_key,
    )

    try:
        # El bloque que puede chocar con la carrera concurrente va DENTRO
        # del try: orders.add() ya hace flush(), y un flush emite el INSERT
        # de verdad contra la base de datos — el UNIQUE constraint de
        # (user_id, idempotency_key) puede saltar aca mismo, no solo en el
        # commit() final. Si el try solo envolviera el commit(), esta
        # excepcion se escaparia sin manejar.
        orders.add(order)  # order.id ya queda disponible para las FK de abajo

        for item in pending_items:
            item.order_id = order.id
            session.add(item)
        session.flush()

        # Por cada item comprado, se crea el registro de propiedad
        # (LibraryItem) que le da al usuario acceso permanente al juego.
        for item in pending_items:
            session.add(LibraryItem(user_id=user.id, game_id=item.game_id, order_id=order.id))

        # El carrito se vacia recien cuando la compra esta confirmada.
        carts.clear(cart.id)

        session.commit()
    except IntegrityError:
        # Camino concurrente: otra request con la MISMA idempotency_key
        # gano la carrera (su INSERT o su commit se confirmo primero). Se
        # descarta este intento (rollback deshace TODO lo de este bloque:
        # la orden, los items, la biblioteca, el vaciado del carrito) y se
        # relee la orden ganadora en vez de fallar.
        session.rollback()
        winning_order = orders.get_by_idempotency(user_id=user.id, idempotency_key=idempotency_key)
        if winning_order is not None:
            log_event(
                logger,
                "checkout_replayed",
                user_id=user.id,
                order_code=winning_order.order_code,
                path="concurrent",
            )
            return winning_order, orders.list_items(winning_order.id)
        # Si no hay orden ganadora con ESTA clave, el choque fue contra
        # otro checkout del mismo usuario con una Idempotency-Key DISTINTA:
        # los dos intentaron comprar los mismos juegos y el UNIQUE
        # (user_id, game_id) de la biblioteca dejo pasar solo a uno. No hay
        # doble cobro; a este se le avisa con un 409 en vez de un 500.
        log_event(logger, "checkout_conflict", level=logging.WARNING, user_id=user.id)
        raise ConflictError(
            "Otra solicitud de compra de tu carrito se proceso al mismo tiempo. "
            "Revisa tu historial de pedidos."
        ) from None

    session.refresh(order)
    # La compra ya esta confirmada (commit hecho): este es EL evento de
    # negocio mas importante del sistema.
    log_event(
        logger,
        "checkout_completed",
        user_id=user.id,
        order_code=order.order_code,
        total=str(order.total),
        item_count=len(pending_items),
    )
    return order, pending_items


def list_orders(
    session: Session, *, current_user: User, page: int, size: int
) -> tuple[list[Order], int, int]:
    # offset/limit clasico de paginacion: pagina 1 arranca en la fila 0.
    offset = (page - 1) * size
    rows, total = OrderRepository(session).list_for_user(current_user.id, offset=offset, limit=size)
    # Redondeo hacia arriba de total/size sin usar float — el mismo truco
    # que ya usa catalog_service.list_games.
    pages = (total + size - 1) // size if total else 0
    return rows, total, pages


def get_order_detail(
    session: Session, *, current_user: User, order_code: str
) -> tuple[Order, list[OrderItem]]:
    orders = OrderRepository(session)
    order = orders.get_by_code(order_code)
    if order is None:
        raise NotFoundError("Orden no encontrada.")
    # 404, no 403: ver ensure_owner_or_admin en core/dependencies.py — un
    # pedido ajeno no debe confirmarle a un desconocido que ese order_code
    # existe.
    ensure_owner_or_admin(order.user_id, current_user)
    return order, orders.list_items(order.id)


def get_receipt_path(session: Session, *, current_user: User, order_code: str) -> str:
    # Reusa get_order_detail: asi la boleta hereda el MISMO chequeo de
    # dueño/admin que el detalle de la orden, sin repetirlo.
    order, _items = get_order_detail(session, current_user=current_user, order_code=order_code)
    if not order.receipt_path:
        # El BackgroundTask que genera el PDF corre DESPUES de responder el
        # checkout — es posible (aunque poco probable) que el cliente pida
        # la boleta antes de que termine. Se informa con un 404 explicito
        # en vez de dejar que el router intente abrir un archivo inexistente.
        raise NotFoundError(
            "La boleta todavia no esta disponible; intenta de nuevo en unos segundos."
        )
    return order.receipt_path


def list_library(session: Session, *, user_id: int) -> list[tuple[LibraryItem, Game, Order]]:
    # Funcion trivial: solo delega en el repositorio — la unica logica de
    # GET /me/library vive en como se arma la respuesta (ver
    # routers/library.py).
    return LibraryRepository(session).list_for_user_detailed(user_id)


def generate_and_send_receipt(order_id: int) -> None:
    """BackgroundTasks callback (see routers/orders.py): builds the PDF
    boleta, saves its path on the order, then emails the customer — neither
    step blocks the checkout response, which has already been returned by
    the time this runs. Uses its own session, since the request's session
    is already closed here.
    """
    # Esta funcion corre DESPUES de que la respuesta ya se envio: una
    # excepcion aqui no tiene a quien llegarle (el cliente ya recibio su
    # 201). Por eso se captura y se deja como evento de ERROR con el
    # traceback, en vez de perderse en el log interno del servidor. La
    # compra NO se deshace: la orden ya esta confirmada; solo falto la
    # boleta/correo.
    try:
        _generate_and_send_receipt(order_id)
    except Exception:
        logger.exception("receipt_failed", extra={"event": "receipt_failed", "order_id": order_id})


def _generate_and_send_receipt(order_id: int) -> None:
    # `with Session(engine) as session` abre una conexion NUEVA a la base
    # de datos — la sesion del request original ya se cerro cuando esta
    # funcion arranca (BackgroundTasks corre DESPUES de enviar la
    # respuesta al cliente).
    with Session(engine) as session:
        orders = OrderRepository(session)
        order = orders.get(order_id)
        if order is None:
            # Caso extremo (la orden se borro entre el checkout y que esta
            # tarea corriera) — no hay nada que hacer, se sale sin error.
            return
        # Un reintento idempotente del checkout (misma Idempotency-Key)
        # tambien encola esta tarea. Si la boleta de esta orden ya se envio,
        # no se regenera ni se vuelve a mandar el correo: reintentar una
        # compra no debe llenarle la bandeja al cliente.
        if order.receipt_sent_at is not None:
            log_event(logger, "receipt_skipped", order_code=order.order_code, reason="already_sent")
            return
        items = orders.list_items(order.id)
        user = UserRepository(session).get(order.user_id)
        if user is None:
            return

        # Paso 1: generar el PDF y guardar su ruta en la orden.
        pdf_path = generate_receipt_pdf(order=order, items=items, user=user)
        order.receipt_path = str(pdf_path)
        session.add(order)
        session.commit()

        # Paso 2: enviar el correo de confirmacion (o escribirlo en
        # ./outbox/ si RESEND_API_KEY no esta configurada) y marcar cuando
        # se envio.
        send_receipt_email(to_email=user.email, order=order)
        order.receipt_sent_at = utcnow()
        session.add(order)
        session.commit()
        log_event(logger, "receipt_sent", order_code=order.order_code, user_id=user.id)
