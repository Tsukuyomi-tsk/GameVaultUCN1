"""Application-level exception hierarchy.

Pulled forward from Fase 7 (where the plan formally schedules "Excepciones
y manejo de errores") because Fase 2 is the first phase with services that
need to reject a request for a business reason — email already registered,
bad credentials, a suspended account. Services raise these from day one so
nothing has to be retrofitted later; Fase 7 only adds the structured
logging and request-id propagation around app.core.handlers, not a new
taxonomy.

Routers never catch these — app.core.handlers.register_exception_handlers
turns every one of them into the same JSON envelope.
"""

from __future__ import annotations


class AppError(Exception):
    """Base for every deliberately-raised business/auth error.

    Subclasses fix `status_code` and `code`; only the human-readable
    `message` (and optional `details`) varies per call site.
    """

    status_code: int = 400
    code: str = "app_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        self.message = message
        self.details = details
        super().__init__(message)


class ValidationError(AppError):
    """A request violates a business rule Pydantic can't express on its
    own (Pydantic's own 422s are handled separately by FastAPI).
    """

    status_code = 422
    code = "validation_error"


class UnauthorizedError(AppError):
    """Missing, invalid, expired or revoked credentials."""

    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    """Authenticated, but not allowed to perform this action."""

    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    """The resource doesn't exist — or, for ownership checks, doesn't
    exist *for this caller* (see app.core.dependencies.ensure_owner_or_admin:
    a 404 here is often deliberate, not accidental, to avoid confirming
    that a resource belonging to someone else exists).
    """

    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    """The request is well-formed but clashes with the current state
    (duplicate email, a review that already exists, etc.).
    """

    status_code = 409
    code = "conflict"


class RateLimitError(AppError):
    """Too many requests. Normally raised by slowapi itself, not by
    application code — kept here so its response shares the same envelope.
    """

    status_code = 429
    code = "rate_limited"
