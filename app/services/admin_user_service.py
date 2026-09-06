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
    # Mismo calculo de offset/pages que en admin_game_service.list_games.
    offset = (page - 1) * size
    items, total = users.list_admin(role=role, is_suspended=is_suspended, offset=offset, limit=size)
    pages = (total + size - 1) // size if total else 0
    return items, total, pages


def suspend_user(session: Session, *, admin_id: int, user_id: int, reason: str) -> User:
    # Regla de negocio central de este endpoint: un admin nunca puede
    # suspender su PROPIA cuenta. Se compara el id del admin autenticado
    # (que llego como parametro, sacado del token JWT en el router) contra
    # el id del usuario que se quiere suspender.
    if admin_id == user_id:
        # 409 (conflicto), no 403 (prohibido): el admin SI tiene permiso
        # para suspender usuarios en general, el problema es especifico
        # de este caso (suspenderse a si mismo), no un problema de rol.
        raise ConflictError("No puedes suspender tu propia cuenta.")

    users = UserRepository(session)
    user = users.get(user_id)
    if user is None:
        raise NotFoundError("Usuario no encontrado.")

    # Se setean los 3 campos de suspension del modelo User de una sola vez.
    user.is_suspended = True
    user.suspended_at = utcnow()
    user.suspension_reason = reason
    users.add(user)
    session.commit()
    session.refresh(user)
    # IMPORTANTE (ver el docstring del modulo): esto NO invalida ningun
    # token JWT ya emitido de forma directa. Lo que hace que la suspension
    # tenga efecto inmediato es que get_current_user (core/dependencies.py)
    # vuelve a leer is_suspended desde la base de datos en CADA request
    # autenticado — asi que el proximo request del usuario suspendido,
    # aunque use un token todavia "valido" en terminos de firma/expiracion,
    # va a chocar con ese chequeo y recibir un 403.
    return user


def reactivate_user(session: Session, *, user_id: int) -> User:
    users = UserRepository(session)
    user = users.get(user_id)
    if user is None:
        raise NotFoundError("Usuario no encontrado.")

    # Reactivar es simplemente el proceso inverso a suspend_user: se
    # limpian los 3 campos de suspension.
    user.is_suspended = False
    user.suspended_at = None
    user.suspension_reason = None
    users.add(user)
    session.commit()
    session.refresh(user)
    return user
