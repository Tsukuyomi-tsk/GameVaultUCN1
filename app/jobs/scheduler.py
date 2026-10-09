"""APScheduler setup (Fase 7).

A `BackgroundScheduler` (jobs run in a small thread pool) fits this app: the
jobs are plain synchronous functions using a sync SQLModel Session, so there
is no event loop to integrate with.

Duplicate-job caveat (from the plan): the scheduler is started from the
FastAPI lifespan, never at import time, and `SCHEDULER_ENABLED=false`
turns it off. Run it in exactly one process — several uvicorn workers would
each start their own scheduler and run every job N times. `uvicorn
--reload` is fine: only the reloaded server process runs the lifespan, and
the previous one is shut down with it.
"""

from __future__ import annotations

import logging
from datetime import UTC

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.core.logging import log_event
from app.jobs.tasks import (
    purge_abandoned_guest_carts_job,
    purge_expired_blacklist_job,
    purge_unverified_accounts_job,
)

logger = logging.getLogger(__name__)

# Cada cuanto corren los jobs que NO tienen variable de entorno propia: el
# plazo de vida de la cuenta/carrito (48 h, 30 dias) ya es lo que se
# configura; la frecuencia de barrido solo necesita ser mucho menor que ese
# plazo.
_UNVERIFIED_PURGE_EVERY_HOURS = 1
_GUEST_CART_PURGE_EVERY_HOURS = 24


def create_scheduler() -> BackgroundScheduler:
    """Build the scheduler with its three jobs registered (not started)."""
    # timezone=UTC: coherente con la convencion "todo en UTC" del proyecto.
    scheduler = BackgroundScheduler(timezone=UTC)

    # Opciones comunes a los tres jobs:
    #  - max_instances=1: si una corrida tarda mas que el intervalo, no se
    #    lanza otra encima.
    #  - coalesce=True: si se acumularon varias ejecuciones atrasadas (el
    #    equipo estuvo dormido), se ejecuta UNA sola, no todas seguidas.
    #  - misfire_grace_time: cuanto retraso se tolera antes de descartar
    #    una ejecucion.
    #  - replace_existing=True: registrar dos veces el mismo id no duplica.
    common = {
        "max_instances": 1,
        "coalesce": True,
        "misfire_grace_time": 300,
        "replace_existing": True,
    }
    scheduler.add_job(
        purge_unverified_accounts_job,
        IntervalTrigger(hours=_UNVERIFIED_PURGE_EVERY_HOURS),
        id="purge_unverified_accounts",
        **common,
    )
    scheduler.add_job(
        purge_expired_blacklist_job,
        IntervalTrigger(hours=settings.blacklist_purge_interval_hours),
        id="purge_expired_blacklist",
        **common,
    )
    scheduler.add_job(
        purge_abandoned_guest_carts_job,
        IntervalTrigger(hours=_GUEST_CART_PURGE_EVERY_HOURS),
        id="purge_abandoned_guest_carts",
        **common,
    )
    return scheduler


def start_scheduler() -> BackgroundScheduler | None:
    """Start the scheduler, or return None when SCHEDULER_ENABLED=false."""
    # Interruptor de apagado: con SCHEDULER_ENABLED=false no se crea nada.
    if not settings.scheduler_enabled:
        log_event(logger, "scheduler_disabled")
        return None

    # Se arma el scheduler con sus jobs...
    scheduler = create_scheduler()
    # ...y se inicia: a partir de aqui corre en sus propios hilos, sin
    # bloquear a FastAPI.
    scheduler.start()
    # Se deja constancia de que jobs quedaron programados.
    log_event(
        logger,
        "scheduler_started",
        jobs=[job.id for job in scheduler.get_jobs()],
    )
    return scheduler
