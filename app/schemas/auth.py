"""Request/response schemas for the /auth endpoints.

Format/shape validation (length, character composition) belongs entirely
here, in Pydantic — the service layer only adds checks that genuinely need
database state (email uniqueness, code correctness), so the two never
duplicate the same rule.
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import BCRYPT_MAX_PASSWORD_BYTES
from app.schemas.user import UserRead


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        # Se mide en BYTES, no en caracteres: max_length=128 de arriba
        # cuenta caracteres, pero bcrypt solo acepta 72 bytes y una "ñ" o
        # un emoji ocupan 2 y 4 bytes respectivamente.
        if len(value.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
            raise ValueError(
                f"La contrasena no puede superar {BCRYPT_MAX_PASSWORD_BYTES} bytes "
                "(los caracteres especiales o emojis ocupan mas de 1 byte)."
            )
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("La contrasena debe combinar letras y numeros.")
        return value


class RegisterResponse(BaseModel):
    message: str
    user: UserRead


class VerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=10)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class MessageResponse(BaseModel):
    message: str
