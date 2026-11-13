"""Structured (JSON) logging, one line per record, stdlib only (Fase 7).

Why JSON: a log line that is a JSON object can be filtered and aggregated
by field (`event`, `user_id`, `request_id`) with any log tool, instead of
parsed back out of free text with regexes. No third-party dependency is
needed — `logging.Formatter` is already the extension point.

Why a ContextVar for `request_id`: the middleware sets it once per request
and every log call made while that request is being handled (routers,
services, repositories, BackgroundTasks) picks it up with no argument
passing. Each request runs in its own asyncio task / threadpool context, so
two concurrent requests never see each other's value.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings

# ContextVar: una "variable global" que en realidad guarda un valor distinto
# por cada request en curso. default=None => fuera de un request (por
# ejemplo, un job programado) simplemente no hay request_id.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Nombres de atributos que TODO LogRecord ya trae de fabrica. Se calculan
# creando un record vacio: lo que NO este en este conjunto lo agrego el
# programador via `extra=` y es justamente lo que queremos volcar al JSON.
# "color_message" lo agrega uvicorn a sus propios logs (el mismo texto con
# codigos de color ANSI): es ruido que no debe llegar al JSON.
_STANDARD_RECORD_ATTRS = frozenset(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
    "color_message",
}


class JSONFormatter(logging.Formatter):
    """Renders every LogRecord as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        # Campos que SIEMPRE aparecen. La fecha se arma en UTC a partir del
        # instante exacto en que se creo el record (no del momento en que
        # se formatea), con milisegundos.
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # El request_id puede venir explicito en `extra=` (lo hace el
        # handler de errores 500, que corre cuando el ContextVar ya fue
        # reseteado) o del ContextVar del request en curso.
        request_id = getattr(record, "request_id", None) or request_id_var.get()
        if request_id:
            payload["request_id"] = request_id

        # Vuelca al JSON cualquier campo extra (event, user_id, order_code...)
        # que el codigo haya agregado con `extra=`.
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_ATTRS and key != "request_id":
                payload[key] = value

        # Si el log trae una excepcion (logger.exception), se incluye el
        # traceback completo como un string dentro del mismo JSON.
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # default=str: si algun campo no es serializable a JSON (un Decimal,
        # un datetime), se convierte a texto en vez de reventar el logging.
        # ensure_ascii=False deja los acentos legibles. JSON escapa los
        # saltos de linea, asi que un dato con "\n" no puede falsificar una
        # linea de log distinta (log injection).
        return json.dumps(payload, ensure_ascii=False, default=str)


def log_event(
    logger: logging.Logger, event: str, *, level: int = logging.INFO, **fields: Any
) -> None:
    """Emit a named, structured business/security event.

    `event` is a stable snake_case name ("login_failed", "checkout_completed")
    that log tools can filter on; `fields` are the event's data. Never pass
    passwords, tokens or verification codes here. Field names must not clash
    with LogRecord attributes (`name`, `message`, `args`, ...).
    """
    # El nombre del evento tambien es el "message" visible, y ademas viaja
    # como campo `event` para poder filtrar por el con exactitud.
    logger.log(level, event, extra={"event": event, **fields})


def configure_logging() -> None:
    """Install the JSON handler on the root logger. Idempotent."""
    # Un unico handler que escribe a stdout (lo normal en contenedores y
    # servicios: el entorno recoge stdout y lo envia donde corresponda).
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    # El nivel TAMBIEN va en el handler. El nivel de un logger solo filtra
    # los registros que nacen en ese logger; un registro que un logger hijo
    # (uvicorn, apscheduler) ya acepto sube a los handlers del padre SIN
    # volver a comprobar el nivel del padre. El handler es el ultimo filtro:
    # con LOG_LEVEL=ERROR, nada por debajo de ERROR sale, venga de donde venga.
    handler.setLevel(settings.log_level)

    # Se reemplazan los handlers del logger raiz (en vez de agregar uno)
    # para que llamar esta funcion dos veces no duplique cada linea.
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)

    # Uvicorn instala sus propios handlers con formato de texto. Se los
    # quitan y se deja que sus mensajes (arranque, errores) suban al logger
    # raiz para salir tambien en JSON.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
        # NOTSET: uvicorn fija su propio nivel INFO; al quitarlo, hereda el
        # del logger raiz y LOG_LEVEL manda tambien sobre sus mensajes.
        uvicorn_logger.setLevel(logging.NOTSET)

    # El log de acceso de uvicorn se apaga: nuestro middleware ya registra
    # cada request (con request_id y duracion), y dejarlo duplicaria todo.
    logging.getLogger("uvicorn.access").disabled = True

    # Las sentencias SQL solo se muestran con LOG_LEVEL=DEBUG (antes las
    # activaba DEBUG=true del .env, que es "true" por defecto y llenaba la
    # consola de ruido).
    sql_level = logging.INFO if settings.log_level == "DEBUG" else logging.WARNING
    logging.getLogger("sqlalchemy.engine").setLevel(sql_level)

    # APScheduler loguea cada ejecucion de job en INFO; los jobs ya emiten
    # sus propios eventos (job_completed / job_failed), asi que solo se
    # dejan pasar sus avisos y errores propios.
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
