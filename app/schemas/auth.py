"""Request/response schemas for the /auth endpoints.

Format/shape validation (length, character composition) belongs entirely
here, in Pydantic — the service layer only adds checks that genuinely need
database state (email uniqueness, code correctness), so the two never
duplicate the same rule.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator

from app.core.security import BCRYPT_MAX_PASSWORD_BYTES
from app.schemas.user import UserRead

# EmailStr solo pasa a minusculas el dominio ("Ana@X.com" -> "Ana@x.com"); la
# parte local se respeta. Sin normalizarla, "Ana@x.com" y "ana@x.com" serian
# dos cuentas distintas para la base de datos. Todo correo que entra por un
# schema de auth se guarda y se busca en minusculas.
NormalizedEmail = Annotated[EmailStr, AfterValidator(str.lower)]


class RegisterRequest(BaseModel):
    email: NormalizedEmail
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
    # Sin datos de usuario a proposito: la respuesta es identica exista o no
    # el correo, para que registrar no sirva para averiguar quien tiene cuenta.
    message: str


class VerifyRequest(BaseModel):
    email: NormalizedEmail
    code: str = Field(min_length=4, max_length=10)


class ResendVerificationRequest(BaseModel):
    email: NormalizedEmail


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class MessageResponse(BaseModel):
    message: str
