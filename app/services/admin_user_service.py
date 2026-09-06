"""Business logic for the admin user management endpoints (Fase 4).

Suspension does not touch TokenBlacklist and never will (see
app/models/user.py and app/core/dependencies.py): `get_current_user`
re-reads `is_suspended` from this same row on every request, which is what
actually makes a suspension take effect on tokens issued before it.
"""

from __future__ import annotations

from sqlmodel import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.time import utcnow
from app.models import User
from app.models.enums import UserRole
from app.repositories.user_repository import UserRepository


def list_users(
    session: Session,
    *,
    role: UserRole | None,
    is_suspended: bool | None,
    page: int,
    size: int,
) -> tuple[list[User], int, int]:
    users = UserRepository(session)
    offset = (page - 1) * size
    items, total = users.list_admin(role=role, is_suspended=is_suspended, offset=offset, limit=size)
    pages = (total + size - 1) // size if total else 0
    return items, total, pages


def suspend_user(session: Session, *, admin_id: int, user_id: int, reason: str) -> User:
    if admin_id == user_id:
        raise ConflictError("No puedes suspender tu propia cuenta.")

    users = UserRepository(session)
    user = users.get(user_id)
    if user is None:
        raise NotFoundError("Usuario no encontrado.")

    user.is_suspended = True
    user.suspended_at = utcnow()
    user.suspension_reason = reason
    users.add(user)
    session.commit()
    session.refresh(user)
    return user


def reactivate_user(session: Session, *, user_id: int) -> User:
    users = UserRepository(session)
    user = users.get(user_id)
    if user is None:
        raise NotFoundError("Usuario no encontrado.")

    user.is_suspended = False
    user.suspended_at = None
    user.suspension_reason = None
    users.add(user)
    session.commit()
    session.refresh(user)
    return user
