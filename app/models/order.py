"""A completed, atomic purchase.

Line items are frozen at OrderItem, never looked up live from Game — see
order_item.py for why.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.time import utcnow
from app.models.enums import OrderStatus
from app.models.sa_enum import str_enum_column


class Order(SQLModel, table=True):
    """One purchase.

    `idempotency_key` + `user_id` are jointly unique so a retried checkout
    with the same key can never create a second order (Fase 5): the
    service re-reads the existing row on a unique-constraint violation
    instead of failing, which is what makes concurrent retries safe too.

    `user_id` is ON DELETE RESTRICT: purchase history must never be lost,
    so hard-deleting a user with orders is refused at the database level,
    not just by application logic.
    """

    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)

    id: int | None = Field(default=None, primary_key=True)
    order_code: str = Field(unique=True, index=True, max_length=30)
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    )
    status: OrderStatus = Field(
        default=OrderStatus.PAID,
        sa_column=Column(str_enum_column(OrderStatus), nullable=False),
    )
    subtotal: Decimal = Field(max_digits=10, decimal_places=2)
    discount_total: Decimal = Field(max_digits=10, decimal_places=2)
    total: Decimal = Field(max_digits=10, decimal_places=2)
    idempotency_key: str = Field(max_length=100)
    created_at: datetime = Field(default_factory=utcnow)
    paid_at: datetime = Field(default_factory=utcnow)
    receipt_path: str | None = Field(default=None, max_length=500)
    receipt_sent_at: datetime | None = Field(default=None)
