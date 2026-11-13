"""Shopping cart endpoints (Fase 5). Works for both guests (via the
X-Cart-Token header) and authenticated users (via the standard Bearer
JWT) — see app.services.cart_service for how identity is resolved. No
route here touches a Session or writes a query directly; every rule and
query lives in the service/repository layers.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import CurrentUser, OptionalCurrentUser
from app.schemas.cart import AddCartItemRequest, CartItemRead, CartRead
from app.schemas.errors import errors
from app.services import cart_service
from app.services.cart_service import CartView

router = APIRouter(prefix="/cart", tags=["cart"])

SessionDep = Annotated[Session, Depends(get_session)]
# alias="X-Cart-Token": el nombre del header no sigue la convencion
# snake_case de Python, por eso se declara explicito en vez de dejar que
# FastAPI lo derive del nombre del parametro (que seria "X_Cart_Token").
CartTokenHeader = Annotated[
    str | None,
    Header(
        alias="X-Cart-Token",
        description=(
            "Token del carrito de **invitado**. La primera vez no lo mandes: `POST /cart/items` "
            "crea el carrito y lo devuelve en `cart_token`; guardalo y enviarlo en las llamadas "
            "siguientes. Con sesion iniciada no hace falta (el carrito sale del JWT)."
        ),
    ),
]

# Autenticacion OPCIONAL en OpenAPI. FastAPI ya publica `security:
# [{"HTTPBearer": []}]` (el JWT) para estas rutas, lo que en /docs se lee como
# "obligatorio". openapi_extra se FUSIONA con lo generado y las listas se
# concatenan: agregar `{}` (una alternativa sin credenciales) deja
# `[{"HTTPBearer": []}, {}]`, que es la forma estandar de OpenAPI para "con
# JWT o sin nada". Solo cambia la documentacion: en tiempo de ejecucion un
# JWT presente pero invalido sigue rechazandose con 401 (ver
# get_optional_current_user).
OPTIONAL_AUTH = {"security": [{}]}
_INVALID_TOKEN_RESPONSE = errors(
    (401, "Se envio un JWT, pero es invalido, expiro o la sesion fue cerrada.")
)
# Texto comun: explica el doble modo (invitado / con sesion) de estas rutas.
_GUEST_NOTE = (
    "\n\n**Auth opcional:** funciona como invitado (cabecera `X-Cart-Token`) o con sesion "
    "(Authorize). Para probar como invitado, pulsa Authorize -> Logout. Un JWT presente pero "
    "invalido se rechaza con `401` (no se trata como invitado)."
)


def _to_read(view: CartView) -> CartRead:
    # Funcion privada compartida por todas las rutas de este archivo:
    # convierte el CartView interno (dataclasses del servicio) al schema
    # Pydantic que realmente sale por HTTP — nunca se devuelve un CartView
    # directo desde una ruta.
    return CartRead(
        items=[
            CartItemRead(
                game_id=row.game.id,
                title=row.game.title,
                slug=row.game.slug,
                base_price=row.game.base_price,
                final_price=row.final_price,
                discount_percent=row.discount_percent,
                has_active_offer=row.has_active_offer,
            )
            for row in view.items
        ],
        subtotal=view.subtotal,
        discount_total=view.discount_total,
        total=view.total,
        cart_token=view.cart_token,
    )


# GET /cart — el carrito actual (del usuario logueado, o del invitado
# identificado por X-Cart-Token). Nunca crea un carrito nuevo por si solo.
# current_user usa OptionalCurrentUser (no CurrentUser): esta ruta funciona
# tanto logueado como sin loguearse.
@router.get(
    "",
    response_model=CartRead,
    summary="Ver el carrito",
    description=(
        "Devuelve el carrito actual con precios y descuentos recalculados por el servidor. "
        "Nunca crea un carrito: si no hay ninguno, responde uno vacio." + _GUEST_NOTE
    ),
    openapi_extra=OPTIONAL_AUTH,
    responses=_INVALID_TOKEN_RESPONSE | errors(422),
)
def get_cart(
    session: SessionDep, current_user: OptionalCurrentUser, x_cart_token: CartTokenHeader = None
) -> CartRead:
    view = cart_service.get_cart(session, user=current_user, cart_token=x_cart_token)
    return _to_read(view)


# POST /cart/items — agrega un juego. Si es un invitado sin X-Cart-Token
# todavia, crea un carrito nuevo y devuelve su token en la respuesta
# (campo cart_token de CartRead) para que el cliente lo guarde.
@router.post(
    "/items",
    response_model=CartRead,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar un juego al carrito",
    description=(
        "Agrega el juego (si ya estaba, no lo duplica). Un invitado sin `X-Cart-Token` recibe "
        "uno nuevo en el campo `cart_token` de la respuesta: **guardalo**." + _GUEST_NOTE
    ),
    openapi_extra=OPTIONAL_AUTH,
    responses=_INVALID_TOKEN_RESPONSE
    | errors((404, "El juego no existe o no esta a la venta."), 422),
)
def add_item(
    payload: AddCartItemRequest,
    session: SessionDep,
    current_user: OptionalCurrentUser,
    x_cart_token: CartTokenHeader = None,
) -> CartRead:
    view = cart_service.add_item(
        session, user=current_user, cart_token=x_cart_token, game_id=payload.game_id
    )
    return _to_read(view)


# DELETE /cart/items/{game_id} — quita un juego puntual del carrito.
@router.delete(
    "/items/{game_id}",
    response_model=CartRead,
    summary="Quitar un juego del carrito",
    description="Quita el juego indicado y devuelve el carrito actualizado." + _GUEST_NOTE,
    openapi_extra=OPTIONAL_AUTH,
    responses=_INVALID_TOKEN_RESPONSE | errors(422),
)
def remove_item(
    game_id: int,
    session: SessionDep,
    current_user: OptionalCurrentUser,
    x_cart_token: CartTokenHeader = None,
) -> CartRead:
    view = cart_service.remove_item(
        session, user=current_user, cart_token=x_cart_token, game_id=game_id
    )
    return _to_read(view)


# DELETE /cart — vacia el carrito completo. 204 sin body, como cualquier
# otro DELETE del proyecto (ver, por ejemplo, admin_offers.py).
@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Vaciar el carrito",
    description="Quita todos los juegos del carrito. No devuelve cuerpo." + _GUEST_NOTE,
    openapi_extra=OPTIONAL_AUTH,
    responses=_INVALID_TOKEN_RESPONSE | errors(422),
)
def clear_cart(
    session: SessionDep, current_user: OptionalCurrentUser, x_cart_token: CartTokenHeader = None
) -> None:
    cart_service.clear_cart(session, user=current_user, cart_token=x_cart_token)


# POST /cart/merge — fusiona el carrito de invitado (X-Cart-Token) en el
# carrito del usuario que acaba de iniciar sesion. Requiere estar logueado
# (CurrentUser, no OptionalCurrentUser): no tiene sentido "fusionar" sin un
# destino — pensado para que el cliente lo llame justo despues de POST
# /auth/login, mandando el token de invitado que venia usando.
@router.post(
    "/merge",
    response_model=CartRead,
    summary="Fusionar el carrito de invitado con mi cuenta",
    description=(
        "Pasa los juegos del carrito de invitado (`X-Cart-Token`) al carrito del usuario. "
        "Llamalo justo despues de `POST /auth/login`. **Exige sesion** (a diferencia del "
        "resto de `/cart`). No filtra juegos ya comprados: eso lo valida el checkout."
    ),
    responses=errors(401, 403, 422),
)
def merge_cart(
    session: SessionDep, current_user: CurrentUser, x_cart_token: CartTokenHeader = None
) -> CartRead:
    view = cart_service.merge_cart(session, user=current_user, cart_token=x_cart_token)
    return _to_read(view)
