"""FastAPI dependencies for authentication and authorization.

Three levels (see the plan's "Modelo de autorizacion"):
  1. Public — no dependency at all.
  2. Authenticated — `CurrentUser` / `get_current_user`.
  3. Admin — `AdminUser` / `require_admin`.

Plus `ensure_owner_or_admin`, a per-resource check services call directly
(it can't be a plain FastAPI dependency — which resource is being checked
is only known once the router has parsed the path).

`get_current_user` re-reads the user row from the database on every
request. That is what makes a suspension take effect on a token issued
before it, and what lets the blacklist reject a token revoked by logout —
neither is encoded in the JWT itself.
"""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.database import get_session
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decode_access_token
from app.models import User, UserRole
from app.repositories.token_blacklist_repository import TokenBlacklistRepository
from app.repositories.user_repository import UserRepository

_bearer_scheme = HTTPBearer(auto_error=False)


def get_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> str:
    """The raw JWT string from the `Authorization: Bearer <token>` header."""
    if credentials is None:
        raise UnauthorizedError("Se requiere autenticacion.")
    return credentials.credentials


BearerToken = Annotated[str, Depends(get_bearer_token)]


def get_current_user(token: BearerToken, session: Annotated[Session, Depends(get_session)]) -> User:
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Token invalido o expirado.") from exc

    blacklist = TokenBlacklistRepository(session)
    if blacklist.is_revoked(payload["jti"]):
        raise UnauthorizedError("La sesion fue cerrada. Inicia sesion nuevamente.")

    users = UserRepository(session)
    user = users.get(int(payload["sub"]))
    if user is None:
        raise UnauthorizedError("Usuario no encontrado.")
    if not user.is_verified:
        raise UnauthorizedError("Debes verificar tu cuenta antes de continuar.")
    if user.is_suspended:
        raise ForbiddenError("Tu cuenta ha sido suspendida.")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != UserRole.ADMIN:
        raise ForbiddenError("Se requiere rol de administrador.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def ensure_owner_or_admin(resource_user_id: int, current_user: User) -> None:
    """Raise NotFoundError unless `current_user` owns the resource or is an
    admin.

    404, not 403: a 403 would confirm to a stranger that a resource
    belonging to someone else exists at that id/code (see orders, reviews
    in Fase 5/6).
    """
    if current_user.role == UserRole.ADMIN:
        return
    if current_user.id != resource_user_id:
        raise NotFoundError("Recurso no encontrado.")
