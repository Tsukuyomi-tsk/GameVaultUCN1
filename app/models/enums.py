"""Shared enumerations used across models and schemas."""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Role-based access control level for a User."""

    USER = "user"
    ADMIN = "admin"


class OrderStatus(StrEnum):
    """Lifecycle status of an Order.

    Checkout is synchronous and simulated (no real payment gateway), so a
    successful checkout always lands directly on PAID. This is still an
    enum instead of a hardcoded literal so a future extension (e.g.
    cancellations, refunds) doesn't require a schema migration.
    """

    PAID = "paid"
