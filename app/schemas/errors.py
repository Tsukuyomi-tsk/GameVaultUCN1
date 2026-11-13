"""The API's real error envelope, as Pydantic schemas, plus the helper that
documents it in OpenAPI (Fase 8, R2-B03).

FastAPI documents a 422 as `HTTPValidationError` (`{"detail": [...]}`) by
default, but app.core.handlers answers EVERY error with
`{"error": {...}, "request_id": ...}`. These schemas describe what is really
sent, and `errors()` attaches them (with an example each) to the
`responses=` of each operation so /docs shows the true contract.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    # Codigo corto y estable para que el frontend decida QUE hacer (el texto
    # de "message" puede cambiar; el "code" no).
    code: str = Field(description="Codigo de error estable, p. ej. `not_found`.")
    # Texto en espanol pensado para mostrarse al usuario.
    message: str = Field(description="Explicacion legible del error.")
    # Solo algunos errores traen detalle (el 422 trae la lista de campos malos).
    details: Any | None = Field(
        default=None, description="Informacion extra; en un 422, la lista de campos invalidos."
    )


class ErrorResponse(BaseModel):
    """Cuerpo de TODA respuesta de error de la API."""

    error: ErrorBody
    # Mismo valor que la cabecera X-Request-ID: sirve para encontrar la
    # peticion en los logs del servidor.
    request_id: str | None = Field(
        default=None, description="Identificador de la peticion (cabecera `X-Request-ID`)."
    )


# Para cada codigo HTTP: su descripcion en /docs y un ejemplo del cuerpo real.
# Cada ejemplo repite el "code" que usa app/core/exceptions.py (o handlers.py).
_ERRORS: dict[int, dict[str, Any]] = {
    401: {
        "description": (
            "No autenticado: falta el token JWT, es invalido, expiro o la sesion "
            "fue cerrada con `/auth/logout`."
        ),
        "code": "unauthorized",
        "message": "Se requiere autenticacion.",
    },
    403: {
        "description": "Sin permiso: la cuenta esta suspendida o la accion exige rol admin.",
        "code": "forbidden",
        "message": "No tienes permiso para realizar esta accion.",
    },
    404: {
        "description": "El recurso no existe (o pertenece a otro usuario).",
        "code": "not_found",
        "message": "Recurso no encontrado.",
    },
    409: {
        "description": "Conflicto con el estado actual (duplicado, rango solapado, etc.).",
        "code": "conflict",
        "message": "La operacion choca con el estado actual del recurso.",
    },
    422: {
        "description": "Datos de entrada invalidos (formato, rango o regla de negocio).",
        "code": "validation_error",
        "message": "Datos de entrada invalidos.",
        "details": [
            {
                "type": "string_too_short",
                "loc": ["body", "password"],
                "msg": "String should have at least 8 characters",
                "input": "abc",
                "ctx": {"min_length": 8},
            }
        ],
    },
    429: {
        "description": (
            "Demasiadas solicitudes. Mira la cabecera `Retry-After` (segundos de espera)."
        ),
        "code": "rate_limited",
        "message": "Demasiadas solicitudes. Intenta de nuevo mas tarde.",
    },
}


def errors(*items: int | tuple[int, str]) -> dict[int | str, dict[str, Any]]:
    """Build the `responses=` dict for an operation.

    Each item is a status code (default description) or `(status, text)` to
    say what that error means in THIS endpoint. Example:
    `errors(401, 403, (404, "El juego no existe."), 422)`.
    """
    responses: dict[int | str, dict[str, Any]] = {}
    for item in items:
        # Un item es solo el codigo, o una pareja (codigo, descripcion propia).
        status, description = item if isinstance(item, tuple) else (item, None)
        spec = _ERRORS[status]
        response: dict[str, Any] = {
            "model": ErrorResponse,
            "description": description or spec["description"],
            # El ejemplo es el cuerpo REAL que arma app/core/handlers.py.
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": spec["code"],
                            "message": spec["message"],
                            "details": spec.get("details"),
                        },
                        "request_id": "3f9c1d27b45a4e6f",
                    }
                }
            },
        }
        if status == 429:
            # Cabecera que acompana al 429 (ver rate_limit_handler y el
            # bloqueo por cuenta de /auth/verify).
            response["headers"] = {
                "Retry-After": {
                    "description": "Segundos que hay que esperar antes de reintentar.",
                    "schema": {"type": "integer", "example": 60},
                }
            }
        responses[status] = response
    return responses


# Errores comunes a TODO endpoint del backoffice: se pasan al APIRouter con
# `responses=ADMIN_RESPONSES` y se aplican a cada una de sus rutas.
ADMIN_RESPONSES = errors(401, (403, "La cuenta esta suspendida o no tiene rol de administrador."))
