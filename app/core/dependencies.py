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

import logging
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.database import get_session
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.logging import log_event
from app.core.security import decode_access_token
from app.models import User, UserRole
from app.repositories.token_blacklist_repository import TokenBlacklistRepository
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# description/bearerFormat: es lo que muestra el dialogo "Authorize" de /docs.
_bearer_scheme = HTTPBearer(
    auto_error=False,
    bearerFormat="JWT",
    description=(
        "Pega aqui el `access_token` que devuelve `POST /auth/login` "
        "(solo el token, sin escribir la palabra `Bearer`)."
    ),
)


def _log_denied(reason: str, **fields: object) -> None:
    """Security event: a request was refused. One event name for every
    denial, with `reason` saying why — so "who is being turned away, and
    from what" is a single filter (`event=access_denied`) in the logs.
    """
    # Un unico nombre de evento para todos los rechazos; `reason` dice el
    # motivo. WARNING porque es trafico anomalo que conviene revisar.
    log_event(logger, "access_denied", level=logging.WARNING, reason=reason, **fields)


def get_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> str:
    """The raw JWT string from the `Authorization: Bearer <token>` header."""
    if credentials is None:
        _log_denied("missing_token")
        raise UnauthorizedError("Se requiere autenticacion.")
    return credentials.credentials


BearerToken = Annotated[str, Depends(get_bearer_token)]


def get_current_user(token: BearerToken, session: Annotated[Session, Depends(get_session)]) -> User:
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as exc:
        _log_denied("invalid_token")
        raise UnauthorizedError("Token invalido o expirado.") from exc

    blacklist = TokenBlacklistRepository(session)
    if blacklist.is_revoked(payload["jti"]):
        # Alguien presento un token que ya cerro sesion: puede ser un
        # cliente con estado viejo, o un token robado reutilizado.
        _log_denied("token_revoked", user_id=int(payload["sub"]))
        raise UnauthorizedError("La sesion fue cerrada. Inicia sesion nuevamente.")

    users = UserRepository(session)
    user = users.get(int(payload["sub"]))
    if user is None:
        _log_denied("user_not_found", user_id=int(payload["sub"]))
        raise UnauthorizedError("Usuario no encontrado.")
    if not user.is_verified:
        _log_denied("account_unverified", user_id=user.id)
        raise UnauthorizedError("Debes verificar tu cuenta antes de continuar.")
    if user.is_suspended:
        _log_denied("account_suspended", user_id=user.id)
        raise ForbiddenError("Tu cuenta ha sido suspendida.")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_optional_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> str | None:
    """Like get_bearer_token, but returns None instead of raising when no
    Authorization header is present at all — used by endpoints that work
    for both guests and authenticated users (the cart, Fase 5).
    """
    # Unica diferencia con get_bearer_token: si NO vino header, se
    # devuelve None en vez de lanzar UnauthorizedError — el resto del
    # comportamiento (extraer el token crudo del "Bearer <token>") es
    # identico.
    if credentials is None:
        return None
    return credentials.credentials


OptionalBearerToken = Annotated[str | None, Depends(get_optional_bearer_token)]


def get_optional_current_user(
    token: OptionalBearerToken, session: Annotated[Session, Depends(get_session)]
) -> User | None:
    """None for a genuinely anonymous request. When a token IS present, it
    goes through the exact same checks as get_current_user (blacklist,
    verified, not suspended) — a bad token still fails loudly here, it just
    doesn't fail for a request that sent no token at all.
    """
    if token is None:
        # Nadie mando Authorization: esto es un invitado genuino, no un
        # error.
        return None
    # Si SI vino un token, se reusa get_current_user tal cual — un token
    # invalido/expirado/de un usuario suspendido sigue fallando con la
    # misma excepcion que en cualquier ruta protegida normal.
    return get_current_user(token, session)


OptionalCurrentUser = Annotated[User | None, Depends(get_optional_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != UserRole.ADMIN:
        _log_denied("admin_required", user_id=user.id)
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
        # Al cliente se le responde 404 (no confirmar que existe), pero en
        # el log queda constancia de que intento tocar un recurso ajeno.
        _log_denied(
            "not_resource_owner", user_id=current_user.id, resource_user_id=resource_user_id
        )
        raise NotFoundError("Recurso no encontrado.")
