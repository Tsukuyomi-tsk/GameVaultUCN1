"""Business logic for the shopping cart (Fase 5).

Works identically for guests (identified by an opaque `X-Cart-Token`) and
authenticated users (identified by `CurrentUser`) — see the plan's Fase 5
section. A logged-in user's cart is resolved purely from their user_id, so
`cart_token` is ignored for every mutating operation except `merge_cart`,
whose entire job is to reconcile the two.

Every price shown here goes through offer_repository's
get_active_offer_for_game/compute_effective_price — never re-derived, same
rule as the catalog (Fase 3) and checkout (this same phase, order_service.py).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.exceptions import NotFoundError
from app.core.time import utcnow
from app.models import Cart, Game, User
from app.repositories.cart_repository import CartRepository
from app.repositories.game_repository import GameRepository
from app.repositories.offer_repository import compute_effective_price, get_active_offer_for_game


# CartItemView es el "paquete" que arma _build_view(): junta el Game con su
# precio ya calculado (final_price/discount_percent), igual que
# GameSummaryRow hace en el catalogo (Fase 3) — el router nunca recibe un
# objeto CartItem/Game crudo del ORM.
@dataclass
class CartItemView:
    game: Game
    final_price: Decimal
    discount_percent: int
    has_active_offer: bool


# CartView es el carrito completo ya armado: sus items, los tres totales
# (subtotal sin descuento, cuanto se descuenta, total final) y el token de
# invitado si corresponde.
@dataclass
class CartView:
    items: list[CartItemView]
    subtotal: Decimal
    discount_total: Decimal
    total: Decimal
    cart_token: str | None


# Constante reutilizada como "carrito vacio" en varios puntos — evita
# escribir Decimal("0.00") suelto siete veces distintas.
_EMPTY_TOTAL = Decimal("0.00")


def _get_or_create_user_cart(session: Session, user_id: int) -> Cart:
    # Funcion privada compartida por varias operaciones: siempre que se
    # necesita EL carrito de un usuario logueado (hay a lo sumo uno, por el
    # unique=True en Cart.user_id), se busca primero y solo se crea uno
    # nuevo si todavia no tenia ninguno.
    carts = CartRepository(session)
    cart = carts.get_by_user(user_id)
    if cart is None:
        cart = carts.add(Cart(user_id=user_id))
    return cart


def _resolve_or_create_cart(
    session: Session, *, user: User | None, cart_token: str | None
) -> tuple[Cart, str | None]:
    """Returns (cart, new_cart_token). `new_cart_token` is only non-None the
    first time a guest cart is created — the caller must hand it back to the
    client, since there is no session to remember it in otherwise.
    """
    if user is not None:
        # Usuario logueado: su carrito se resuelve solo por su user_id, el
        # cart_token (si vino) se ignora por completo.
        return _get_or_create_user_cart(session, user.id), None

    carts = CartRepository(session)
    if cart_token:
        # Invitado que ya tenia un token: si el carrito todavia existe
        # (no fue purgado por el job de limpieza de la Fase 7), se
        # reutiliza tal cual, sin generar un token nuevo.
        existing = carts.get_by_session_token(cart_token)
        if existing is not None:
            return existing, None

    # Invitado sin token (primera visita) o con un token que ya no
    # corresponde a ningun carrito: se genera un token nuevo, criptografi-
    # camente aleatorio, y se crea el carrito de invitado desde cero.
    new_token = secrets.token_urlsafe(32)
    cart = carts.add(Cart(session_token=new_token))
    return cart, new_token


def _resolve_cart_readonly(
    session: Session, *, user: User | None, cart_token: str | None
) -> Cart | None:
    """Like _resolve_or_create_cart, but never creates a row — used by
    reads/removals so an anonymous probe or a stale/expired guest token
    never litters the carts table.
    """
    if user is not None:
        return CartRepository(session).get_by_user(user.id)
    if cart_token:
        return CartRepository(session).get_by_session_token(cart_token)
    # Invitado sin token: no hay nada que buscar ni que crear.
    return None


def _build_view(session: Session, cart: Cart, *, cart_token: str | None) -> CartView:
    now = utcnow()
    # Trae todos los items del carrito, cada uno ya con su Game asociado
    # (ver CartRepository.list_items_with_games — una sola consulta, sin
    # N+1).
    rows = CartRepository(session).list_items_with_games(cart.id)

    items: list[CartItemView] = []
    subtotal = _EMPTY_TOTAL
    total = _EMPTY_TOTAL
    for _cart_item, game in rows:
        # Por cada juego del carrito, se resuelve su oferta vigente (si
        # tiene) y su precio final EXACTAMENTE igual que en el catalogo —
        # nunca se re-deriva el descuento a mano aca.
        offer = get_active_offer_for_game(session, game.id, now)
        final_price, discount_percent = compute_effective_price(game.base_price, offer)
        items.append(
            CartItemView(
                game=game,
                final_price=final_price,
                discount_percent=discount_percent,
                has_active_offer=offer is not None,
            )
        )
        # Acumula el subtotal (precio de lista, sin descuento) y el total
        # (ya con descuento aplicado) sumando cada item.
        subtotal += game.base_price
        total += final_price

    return CartView(
        items=items,
        subtotal=subtotal,
        # El descuento total es simplemente la diferencia entre ambos
        # acumuladores — nunca se calcula por separado, para que subtotal -
        # discount_total = total sea una identidad que siempre se cumple.
        discount_total=subtotal - total,
        total=total,
        cart_token=cart_token,
    )


def _empty_view(cart_token: str | None) -> CartView:
    # Representa un carrito "vacio" sin tener que crear ninguna fila en la
    # base de datos — usado cuando un invitado consulta/borra un carrito
    # que en realidad nunca existio (o ya no existe).
    return CartView(
        items=[],
        subtotal=_EMPTY_TOTAL,
        discount_total=_EMPTY_TOTAL,
        total=_EMPTY_TOTAL,
        cart_token=cart_token,
    )


def get_cart(session: Session, *, user: User | None, cart_token: str | None) -> CartView:
    # Resolucion de SOLO LECTURA: nunca crea un carrito por el solo hecho de
    # consultarlo.
    cart = _resolve_cart_readonly(session, user=user, cart_token=cart_token)
    if cart is None:
        # Un usuario logueado nunca necesita que se le devuelva SU token (no
        # tiene uno); solo un invitado recibe el cart_token de vuelta.
        return _empty_view(cart_token if user is None else None)
    return _build_view(session, cart, cart_token=cart_token if user is None else None)


def add_item(
    session: Session, *, user: User | None, cart_token: str | None, game_id: int
) -> CartView:
    games = GameRepository(session)
    game = games.get(game_id)
    # get() ya excluye los juegos soft-deleted; is_active se chequea aparte
    # porque un juego puede estar "pausado" temporalmente sin estar borrado.
    if game is None or not game.is_active:
        raise NotFoundError("Juego no encontrado.")

    # Esta si es la version que CREA un carrito si hace falta (a diferencia
    # de get_cart): agregar un item es la operacion que en la practica
    # "nace" el carrito de un invitado nuevo.
    def _add() -> tuple[Cart, str | None]:
        cart, new_token = _resolve_or_create_cart(session, user=user, cart_token=cart_token)
        CartRepository(session).add_item(cart_id=cart.id, game_id=game_id)
        session.commit()
        return cart, new_token

    try:
        cart, new_token = _add()
    except IntegrityError:
        # Dos requests simultaneas de un usuario sin carrito intentaron
        # CREARLO a la vez (Cart.user_id es unico): la base de datos
        # desempato y esta perdio. Se deshace y se repite UNA vez: ahora el
        # carrito ya existe (la ganadora hizo commit), asi que el segundo
        # intento lo encuentra. (Agregar el mismo juego dos veces ya no
        # puede fallar: lo resuelve CartRepository.add_item.)
        session.rollback()
        cart, new_token = _add()

    # Si se genero un token nuevo (invitado sin carrito previo), ese es el
    # que hay que devolver; si no, se repite el que ya traia la request.
    effective_token = new_token if user is None else None
    return _build_view(session, cart, cart_token=effective_token or cart_token)


def remove_item(
    session: Session, *, user: User | None, cart_token: str | None, game_id: int
) -> CartView:
    # Solo lectura para RESOLVER el carrito: si no existe, no hay nada que
    # quitar (no se crea un carrito solo para "vaciarlo").
    cart = _resolve_cart_readonly(session, user=user, cart_token=cart_token)
    if cart is None:
        return _empty_view(cart_token if user is None else None)

    CartRepository(session).remove_item(cart_id=cart.id, game_id=game_id)
    session.commit()
    return _build_view(session, cart, cart_token=cart_token if user is None else None)


def clear_cart(session: Session, *, user: User | None, cart_token: str | None) -> None:
    cart = _resolve_cart_readonly(session, user=user, cart_token=cart_token)
    if cart is None:
        # Nada que vaciar — no es un error, es simplemente un no-op.
        return
    CartRepository(session).clear(cart.id)
    session.commit()


def merge_cart(session: Session, *, user: User, cart_token: str | None) -> CartView:
    """Folds a guest cart into the now-logged-in user's cart. A missing,
    unknown or already-claimed token is treated as "nothing to merge" — not
    an error — since this is meant to be safe to call after every login,
    whether or not the client actually had a guest cart going.
    """
    # El destino de la fusion SIEMPRE es el carrito del usuario logueado —
    # se crea si todavia no tenia uno.
    user_cart = _get_or_create_user_cart(session, user.id)

    carts = CartRepository(session)
    guest_cart = carts.get_by_session_token(cart_token) if cart_token else None
    # Solo se fusiona si el token corresponde a un carrito real Y ese
    # carrito es genuinamente de invitado (guest_cart.user_id is None) — un
    # token que por error apuntara al carrito de OTRO usuario nunca se
    # fusiona con el de quien esta llamando.
    if guest_cart is not None and guest_cart.user_id is None:
        carts.merge_into(source_cart_id=guest_cart.id, target_cart_id=user_cart.id)
        # El carrito de invitado, ya vacio, se borra fisicamente — no tiene
        # sentido dejar una fila huerfana en la tabla carts.
        carts.delete(guest_cart)

    session.commit()
    return _build_view(session, user_cart, cart_token=None)
