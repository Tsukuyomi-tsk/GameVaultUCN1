"""Request context middleware (Fase 7): correlation id + access log.

Written as a pure ASGI middleware, not with `BaseHTTPMiddleware`: the
latter runs the app in a separate task, which breaks ContextVar
propagation and interferes with BackgroundTasks. Pure ASGI keeps the whole
request — including the background task that sends the receipt email — in
the same context, so `request_id` reaches every log line.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import log_event, request_id_var

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

# Un request_id entrante solo se acepta si es "razonable": 8-64 caracteres
# alfanumericos, punto, guion o guion bajo. Asi un cliente no puede colar
# saltos de linea, comillas o textos enormes en nuestros logs ni en la
# cabecera de respuesta.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestContextMiddleware:
    """Assigns every HTTP request an id and logs one `http_request` event."""

    def __init__(self, app: ASGIApp) -> None:
        # `app` es el siguiente eslabon de la cadena (otro middleware o,
        # al final, la aplicacion FastAPI).
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Este middleware solo trata requests HTTP; lifespan y websockets
        # pasan de largo sin tocarse.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Si el cliente (o un proxy) ya mando un X-Request-ID valido se
        # reutiliza, para poder seguir un mismo request a traves de varios
        # sistemas; si no, se genera uno nuevo aleatorio.
        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER)
        request_id = (
            incoming if incoming and _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        )

        # Se guarda en scope["state"], que es lo que FastAPI expone como
        # `request.state`: asi app.core.handlers lo lee para ponerlo en el
        # sobre de error ("request_id") sin cambiar nada de ese modulo.
        scope.setdefault("state", {})["request_id"] = request_id
        # Y en el ContextVar, para que cada log del request lo incluya solo.
        token = request_id_var.set(request_id)

        started = time.perf_counter()
        # 500 por defecto: si la app lanza una excepcion antes de responder,
        # el cliente recibira un 500 (lo fabrica el handler de excepciones).
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            # Solo el mensaje de inicio de respuesta lleva status y cabeceras
            # (el cuerpo viaja en mensajes "http.response.body" posteriores).
            if message["type"] == "http.response.start":
                status_code = message["status"]
                # Devuelve el id al cliente: quien reporte un error puede
                # citarlo y se encuentra su rastro exacto en los logs.
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            # finally: se registra el request haya terminado bien o con una
            # excepcion sin manejar.
            client = scope.get("client")
            log_event(
                logger,
                "http_request",
                # Un 5xx es un fallo nuestro (ERROR); todo lo demas es trafico
                # normal (los rechazos de seguridad tienen sus propios eventos).
                level=logging.ERROR if status_code >= 500 else logging.INFO,
                method=scope["method"],
                path=scope["path"],
                status_code=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                client_ip=client[0] if client else None,
            )
            # Se restaura el valor anterior del ContextVar.
            request_id_var.reset(token)
