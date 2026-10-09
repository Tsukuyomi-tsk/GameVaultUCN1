"""Housekeeping rules behind the scheduled jobs (Fase 7).

The jobs (app/jobs) are only the trigger: they open a session and call
these functions. The rules — what counts as stale, how old is old enough —
live here, in the service layer, so they follow the same layering as any
request-driven operation (service owns the transaction, repositories own
the queries) and can be called and checked without a scheduler running.
"""

from __future__ import annotations

# timedelta representa una duracion (48 horas, 30 dias) que se puede restar
# a una fecha para obtener "la fecha limite".
from datetime import timedelta

from sqlmodel import Session

from app.core.config import settings
from app.core.time import utcnow
from app.repositories.cart_repository import CartRepository
from app.repositories.token_blacklist_repository import TokenBlacklistRepository
from app.repositories.user_repository import UserRepository


def purge_unverified_accounts(session: Session) -> int:
    """Delete accounts never verified within UNVERIFIED_ACCOUNT_TTL_HOURS.

    Returns how many were deleted. Accounts with orders are never deleted
    (see UserRepository.delete_stale_unverified).
    """
    # Fecha limite: "ahora" menos el plazo de vida permitido (por defecto
    # 48 horas). Toda cuenta creada ANTES de este instante ya vencio.
    cutoff = utcnow() - timedelta(hours=settings.unverified_account_ttl_hours)
    # El servicio NO escribe la consulta: se la pide al repositorio, que
    # devuelve cuantas filas borro.
    deleted = UserRepository(session).delete_stale_unverified(created_before=cutoff)
    # El servicio es dueno de la transaccion: el repositorio solo ejecuto
    # el DELETE, aqui se confirma de forma definitiva.
    session.commit()
    # Se devuelve la cantidad para que el job la registre en el log.
    return deleted


def purge_expired_blacklist(session: Session) -> int:
    """Delete blacklist rows of tokens that have expired anyway."""
    # Aqui no hay plazo configurable: un token expirado es el que ya paso
    # su propia fecha de expiracion, o sea "antes de ahora".
    deleted = TokenBlacklistRepository(session).delete_expired(utcnow())
    # Confirma el borrado.
    session.commit()
    return deleted


def purge_abandoned_guest_carts(session: Session) -> int:
    """Delete guest carts untouched for more than GUEST_CART_TTL_DAYS."""
    # Fecha limite: "ahora" menos los dias de inactividad tolerados
    # (por defecto 30). Un carrito sin cambios desde antes de esa fecha se
    # considera abandonado.
    cutoff = utcnow() - timedelta(days=settings.guest_cart_ttl_days)
    deleted = CartRepository(session).delete_abandoned_guest_carts(updated_before=cutoff)
    # Confirma el borrado (sus CartItem se fueron en cascada).
    session.commit()
    return deleted
