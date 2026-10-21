"""Centralized exception handling.

Every AppError subclass, every slowapi rate-limit rejection, and any
genuinely unhandled exception are all turned into the same JSON envelope —
the API never leaks a raw traceback or returns an inconsistent error shape.
`request_id` is part of that envelope (read from `request.state`):
app.core.middleware.RequestContextMiddleware (Fase 7) is what populates it.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import log_event

logger = logging.getLogger(__name__)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    request: Request,
    details: object = None,
    extra_headers: dict[str, str] | None = None,
) -> JSONResponse:
    # jsonable_encoder, not a raw dict straight into JSONResponse: Pydantic's
    # own ValidationError.errors() can embed the raw exception object in
    # ctx.error when a validator raises ValueError directly (every
    # @field_validator/@model_validator in this app does exactly that) —
    # plain json.dumps chokes on it ("Object of type ValueError is not JSON
    # serializable"), turning a legitimate 422 into an unhandled 500. This
    # is the same fix FastAPI's own default validation-error handler uses.
    #
    # NOTA (bug real encontrado durante el testing de Fase 4): antes, esta
    # funcion armaba el dict de la respuesta y lo pasaba DIRECTO a
    # JSONResponse(content=...). JSONResponse serializa ese dict con
    # json.dumps "a secas" — y json.dumps no sabe convertir un objeto
    # Python arbitrario (como una excepcion ValueError) a JSON. Cuando
    # `details` es exc.errors() de una RequestValidationError, Pydantic a
    # veces mete ahi adentro la excepcion original sin convertir, y todo
    # el response reventaba con un 500 en vez de devolver el 422 esperado.
    # jsonable_encoder() recorre la estructura entera y convierte
    # cualquier valor "raro" (excepciones incluidas) a algo serializable
    # ANTES de que JSONResponse intente convertirlo a texto JSON.
    request_id = getattr(request.state, "request_id", None)
    content = jsonable_encoder(
        {
            "error": {"code": code, "message": message, "details": details},
            "request_id": request_id,
        }
    )
    # El id tambien viaja en la cabecera. Para las respuestas normales ya lo
    # agrega el middleware, pero la respuesta del 500 la fabrica
    # ServerErrorMiddleware, que esta POR FUERA del middleware y no pasa por
    # el: sin esto, el 500 no llevaria la cabecera.
    headers = {"X-Request-ID": request_id} if request_id else {}
    # extra_headers: cabeceras adicionales que solo algunos llamadores
    # necesitan (hoy, CORS para el 500).
    headers.update(extra_headers or {})
    return JSONResponse(status_code=status_code, content=content, headers=headers or None)


def _cors_headers_for(request: Request) -> dict[str, str]:
    """CORS headers for the 500 response, which the CORS middleware never sees.

    `ServerErrorMiddleware` builds that response OUTSIDE every user
    middleware, CORSMiddleware included — so without these a browser app on
    another origin cannot read the error body nor the X-Request-ID (it
    would show an opaque network error). Mirrors the CORSMiddleware config
    in main.py (credentials stay off, so "*" is a valid answer).
    """
    # Solo hay cabeceras CORS si el navegador mando Origin (peticion cross-origin).
    origin = request.headers.get("origin")
    allowed = settings.cors_origins_list
    if not origin or not ("*" in allowed or origin in allowed):
        return {}
    return {
        # Con "*" se responde "*"; con una lista, el origen exacto que pidio.
        "Access-Control-Allow-Origin": "*" if "*" in allowed else origin,
        # Sin esto el navegador no deja a JavaScript leer X-Request-ID.
        "Access-Control-Expose-Headers": "X-Request-ID",
        # La respuesta cambia segun el Origin: los caches deben tenerlo en cuenta.
        "Vary": "Origin",
    }


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return _error_response(
        exc.status_code, exc.code, exc.message, request, exc.details, extra_headers=exc.headers
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI/Pydantic's own request-shape errors, wrapped in the same
    envelope instead of their default `{"detail": [...]}` shape.
    """
    return _error_response(
        422, "validation_error", "Datos de entrada invalidos.", request, exc.errors()
    )


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    # Evento de seguridad: muchas de estas desde una misma IP sobre /auth/*
    # es el rastro tipico de un intento de fuerza bruta.
    log_event(
        logger,
        "rate_limited",
        level=logging.WARNING,
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host if request.client else None,
    )
    return _error_response(
        429, "rate_limited", "Demasiadas solicitudes. Intenta de nuevo mas tarde.", request
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # extra: este handler corre FUERA del middleware (ServerErrorMiddleware
    # esta por encima), cuando el ContextVar del request ya fue reseteado;
    # por eso el request_id se pasa explicito desde request.state.
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
        extra={
            "event": "unhandled_exception",
            "request_id": getattr(request.state, "request_id", None),
        },
    )
    return _error_response(
        500,
        "internal_error",
        "Ha ocurrido un error interno.",
        request,
        extra_headers=_cors_headers_for(request),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
