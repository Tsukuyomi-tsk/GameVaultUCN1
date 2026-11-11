"""Checkout and order history endpoints (Fase 5). Every route requires
CurrentUser — there is no "someone else's order" view, only
ensure_owner_or_admin (enforced in app.services.order_service).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, status
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import CurrentUser
from app.models import Order, OrderItem
from app.schemas.order import OrderDetail, OrderItemRead, OrderPage, OrderSummary
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["orders"])

SessionDep = Annotated[Session, Depends(get_session)]


def _to_detail(order: Order, items: list[OrderItem]) -> OrderDetail:
    # Funcion privada compartida por checkout y get_order: ambas devuelven
    # la MISMA forma de respuesta (orden completa + sus items), asi que la
    # conversion vive en un solo lugar.
    return OrderDetail(
        order_code=order.order_code,
        status=order.status,
        subtotal=order.subtotal,
        discount_total=order.discount_total,
        total=order.total,
        created_at=order.created_at,
        paid_at=order.paid_at,
        receipt_sent_at=order.receipt_sent_at,
        items=[OrderItemRead.model_validate(item) for item in items],
    )


# POST /orders/checkout — confirma la compra del carrito del usuario
# logueado. Idempotency-Key es OBLIGATORIO (ver el plan: "Idempotencia de
# checkout"): FastAPI ya responde 422 solo si falta, porque el parametro no
# tiene default. La generacion de la boleta PDF y el correo de confirmacion
# corren DESPUES de responder (BackgroundTasks), sin bloquear al cliente.
@router.post("/checkout", response_model=OrderDetail, status_code=status.HTTP_201_CREATED)
def checkout(
    session: SessionDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> OrderDetail:
    order, items = order_service.checkout(
        session, user=current_user, idempotency_key=idempotency_key
    )
    # background_tasks.add_task NO ejecuta la funcion ahora: FastAPI la
    # encola y la corre recien despues de que la respuesta ya salio al
    # cliente — por eso generate_and_send_receipt abre su PROPIA sesion en
    # vez de reusar `session` (que para entonces ya estaria cerrada).
    background_tasks.add_task(order_service.generate_and_send_receipt, order.id)
    return _to_detail(order, items)


# GET /orders — historial paginado del usuario logueado.
@router.get("", response_model=OrderPage)
def list_orders(
    session: SessionDep,
    current_user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> OrderPage:
    rows, total, pages = order_service.list_orders(
        session, current_user=current_user, page=page, size=size
    )
    return OrderPage(
        items=[OrderSummary.model_validate(order) for order in rows],
        page=page,
        size=size,
        total=total,
        pages=pages,
    )


# GET /orders/{order_code} — detalle de una orden puntual, con sus items.
# Pedir la orden de OTRO usuario responde 404 (ver
# order_service.get_order_detail -> ensure_owner_or_admin).
@router.get("/{order_code}", response_model=OrderDetail)
def get_order(order_code: str, session: SessionDep, current_user: CurrentUser) -> OrderDetail:
    order, items = order_service.get_order_detail(
        session, current_user=current_user, order_code=order_code
    )
    return _to_detail(order, items)


# GET /orders/{order_code}/receipt — descarga la boleta en PDF. Puede
# responder 404 "todavia no esta disponible" si el BackgroundTask del
# checkout aun no termino de generarla (ver order_service.get_receipt_path).
@router.get(
    "/{order_code}/receipt",
    # response_class=FileResponse: sin esto FastAPI documenta el 200 como
    # JSON (el tipo por defecto). FileResponse no fija un media_type, asi
    # que el 200 se describe solo con el bloque `responses` de abajo.
    response_class=FileResponse,
    responses={
        200: {
            "description": "Boleta en PDF (archivo adjunto).",
            # El contenido NO es JSON: es un archivo binario.
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
            "headers": {
                "Content-Disposition": {
                    "description": 'Nombre del archivo, formato: attachment; filename="GV-YYYYMMDD-XXXXXXXX.pdf" (el codigo de la orden).',
                    "schema": {"type": "string"},
                }
            },
        },
        401: {"description": "Falta el token, es invalido o la sesion fue cerrada."},
        403: {"description": "La cuenta esta suspendida."},
        404: {
            "description": (
                "La orden no existe, es de otro usuario, o la boleta todavia se esta "
                "generando en segundo plano."
            )
        },
    },
)
def get_receipt(order_code: str, session: SessionDep, current_user: CurrentUser) -> FileResponse:
    # get_receipt_path ya valida dueño/admin y que el archivo exista antes
    # de devolver la ruta — aca solo queda envolverla en una FileResponse.
    path = order_service.get_receipt_path(session, current_user=current_user, order_code=order_code)
    return FileResponse(path, media_type="application/pdf", filename=f"{order_code}.pdf")
