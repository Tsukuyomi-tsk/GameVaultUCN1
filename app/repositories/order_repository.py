"""Data access for Order/OrderItem (Fase 5).

`get_by_idempotency` is what makes checkout idempotent on both the
sequential retry path (a plain re-query before doing any work) and the
concurrent retry path (re-queried again after an IntegrityError on the
(user_id, idempotency_key) UniqueConstraint) — see app.services.order_service
for both paths.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlmodel import select

from app.models import Order, OrderItem
from app.repositories.base import BaseRepository


class OrderRepository(BaseRepository[Order]):
    # Le indica a BaseRepository sobre que tabla trabajan get()/add()/
    # delete() heredados: "orders".
    model = Order

    def get_by_idempotency(self, *, user_id: int, idempotency_key: str) -> Order | None:
        # Busca una orden por la MISMA combinacion que protege el
        # UniqueConstraint del modelo Order (user_id + idempotency_key) —
        # es la consulta que hace que un reintento de checkout devuelva la
        # orden ya creada en vez de crear una segunda.
        statement = select(Order).where(
            Order.user_id == user_id, Order.idempotency_key == idempotency_key
        )
        return self.session.exec(statement).first()

    def get_by_code(self, order_code: str) -> Order | None:
        # order_code es el identificador PUBLICO de una orden (el que ve el
        # cliente en la URL /orders/{order_code}) — nunca se expone el id
        # interno de la fila.
        return self.session.exec(select(Order).where(Order.order_code == order_code)).first()

    def list_for_user(self, user_id: int, *, offset: int, limit: int) -> tuple[list[Order], int]:
        # Punto de partida: todas las ordenes de ESTE usuario.
        statement = select(Order).where(Order.user_id == user_id)
        # Cuenta cuantas ordenes en total cumplen el filtro (antes de
        # offset/limit) — es lo que el endpoint necesita para el campo
        # "total" de la respuesta paginada.
        total = self.session.execute(statement.with_only_columns(func.count(Order.id))).scalar_one()
        # Trae la pagina pedida: las ordenes mas nuevas primero.
        rows = self.session.exec(
            statement.order_by(Order.created_at.desc()).offset(offset).limit(limit)
        ).all()
        return list(rows), int(total)

    def list_items(self, order_id: int) -> list[OrderItem]:
        # Todos los items congelados de una orden, en el orden en que se
        # crearon (mismo orden en que estaban en el carrito al pagar).
        statement = (
            select(OrderItem).where(OrderItem.order_id == order_id).order_by(OrderItem.id.asc())
        )
        return list(self.session.exec(statement).all())

    def add_item(self, item: OrderItem) -> OrderItem:
        # Metodo auxiliar simple para insertar un OrderItem suelto — igual
        # que BaseRepository.add(), pero especifico por si en el futuro
        # OrderItem necesita un tratamiento distinto al generico.
        self.session.add(item)
        self.session.flush()
        self.session.refresh(item)
        return item
