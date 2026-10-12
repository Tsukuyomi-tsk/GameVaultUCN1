"""The scheduled job bodies (Fase 7).

Each job is a thin wrapper: open its own Session (there is no request, so
no `get_session`), call one maintenance_service function, and log the
outcome as a structured event. A job must never let an exception escape —
APScheduler would only log it in its own format — so failures are caught
here and reported as a `job_failed` event instead.
"""

from __future__ import annotations

# time.perf_counter mide duraciones con alta precision (no es una fecha).
import logging
import time

# Callable describe "algo que se puede llamar como funcion": aqui, la regla
# de limpieza que recibe una sesion y devuelve cuantas filas borro.
from collections.abc import Callable

from sqlmodel import Session

from app.core.database import engine
from app.core.logging import log_event
from app.services import maintenance_service

logger = logging.getLogger(__name__)


def _run_job(name: str, action: Callable[[Session], int]) -> None:
    """Run `action` in its own session and log `job_completed`/`job_failed`."""
    # Se anota el instante de inicio para calcular cuanto tardo el job.
    started = time.perf_counter()
    try:
        # Sesion propia del job: se cierra sola al salir del `with`.
        with Session(engine) as session:
            deleted = action(session)
    except Exception:
        # Se captura TODO a proposito: un job que falla hoy debe volver a
        # intentarse en su proximo turno, sin tumbar el scheduler.
        # logger.exception registra el error CON su traceback completo.
        logger.exception("job_failed", extra={"event": "job_failed", "job": name})
        # Se sale sin relanzar: el job se intentara de nuevo en su proximo turno.
        return
    # Camino feliz: se registra que el job termino y cuantas filas borro.
    log_event(
        logger,
        "job_completed",
        job=name,
        deleted=deleted,
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )


# Las tres funciones siguientes son las que APScheduler llama de verdad.
# Cada una solo le pone nombre al job y le pasa la regla de negocio que debe
# ejecutar.
def purge_unverified_accounts_job() -> None:
    _run_job("purge_unverified_accounts", maintenance_service.purge_unverified_accounts)


def purge_expired_blacklist_job() -> None:
    _run_job("purge_expired_blacklist", maintenance_service.purge_expired_blacklist)


def purge_abandoned_guest_carts_job() -> None:
    _run_job("purge_abandoned_guest_carts", maintenance_service.purge_abandoned_guest_carts)
