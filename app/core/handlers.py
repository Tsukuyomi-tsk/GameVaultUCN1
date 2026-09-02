"""Centralized exception handling.

Every AppError subclass, every slowapi rate-limit rejection, and any
genuinely unhandled exception are all turned into the same JSON envelope —
the API never leaks a raw traceback or returns an inconsistent error shape.
`request_id` is already part of that envelope (read from `request.state`)
even though nothing sets it yet: Fase 7's logging middleware populates it
without this module changing at all.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


def _error_response(
    status_code: int, code: str, message: str, request: Request, details: object = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {"code": code, "message": message, "details": details},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return _error_response(exc.status_code, exc.code, exc.message, request, exc.details)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI/Pydantic's own request-shape errors, wrapped in the same
    envelope instead of their default `{"detail": [...]}` shape.
    """
    return _error_response(
        422, "validation_error", "Datos de entrada invalidos.", request, exc.errors()
    )


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return _error_response(
        429, "rate_limited", "Demasiadas solicitudes. Intenta de nuevo mas tarde.", request
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return _error_response(500, "internal_error", "Ha ocurrido un error interno.", request)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
