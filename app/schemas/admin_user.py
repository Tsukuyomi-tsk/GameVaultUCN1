"""Request/response schemas for the admin user management endpoints
(Fase 4). Separate from schemas/user.py's UserRead (the public /auth/me
shape), which deliberately omits suspension fields a shopper never needs.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole


class AdminUserRead(BaseModel):
    # Permite construir esta clase directamente desde un objeto User del
    # ORM (AdminUserRead.model_validate(user)), leyendo sus atributos.
    model_config = ConfigDict(from_attributes=True)

    id: int
    # EmailStr valida que el string tenga formato de correo electronico
    # valido — aunque aca no se recibe del usuario (es solo de salida),
    # se usa el mismo tipo por consistencia con el resto de los schemas.
    email: EmailStr
    full_name: str
    role: UserRole
    is_verified: bool
    # Estos 3 campos son los que UserRead (la version publica de /auth/me)
    # NO expone — son informacion de gestion interna que solo le importa
    # a un admin, no al propio usuario ni a terceros.
    is_suspended: bool
    suspended_at: datetime | None
    suspension_reason: str | None
    created_at: datetime


class UserPage(BaseModel):
    # Mismo patron de paginacion que GameAdminPage/GamePage: la lista de
    # usuarios de esta pagina, mas los metadatos para dibujar la
    # paginacion en el frontend.
    items: list[AdminUserRead]
    page: int
    size: int
    total: int
    pages: int


class SuspendUserRequest(BaseModel):
    # Ejemplo precargado en Swagger.
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"reason": "Incumplimiento de las normas de la comunidad."}]
        }
    )

    # Cuerpo que el admin manda al suspender una cuenta: un motivo
    # obligatorio (min_length=1 impide mandar un string vacio) que se
    # guarda en User.suspension_reason, para que quede registro de POR QUE
    # se suspendio a alguien.
    reason: str = Field(min_length=1, max_length=500)
