"""Identity endpoints: registration, email verification, login, logout.

Every route here is decorated with the shared `limiter` (per the plan's
"Limitacion de Tasa" requirement — brute force and abuse mitigation on
auth specifically, not the whole API). Routers only translate HTTP <->
Python: every actual rule lives in app.services.auth_service.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlmodel import Session

from app.core.config import settings
from app.core.database import get_session
from app.core.dependencies import BearerToken, CurrentUser
from app.core.rate_limit import limiter
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MessageResponse,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    VerifyRequest,
)
from app.schemas.errors import errors
from app.schemas.user import UserRead
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(get_session)]

# Texto comun a los 4 endpoints con limite de tasa: se agrega a su descripcion
# para que quien prueba desde /docs sepa por que puede recibir un 429.
_RATE_LIMIT_NOTE = (
    "\n\n**Limite de tasa:** 5 peticiones por minuto por IP **en este endpoint**; "
    "el exceso responde `429` con `Retry-After: 60`."
)


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una cuenta nueva",
    description=(
        "Crea la cuenta (sin verificar) y envia un codigo de verificacion al correo.\n\n"
        "La respuesta es **siempre la misma** exista o no ya una cuenta con ese correo "
        "(asi este endpoint no sirve para averiguar quien tiene cuenta). El correo se envia "
        "en segundo plano.\n\n"
        "**En modo dev** (sin credenciales de Resend) el correo no sale: el codigo queda en "
        "un archivo dentro de `./outbox/`.\n\n"
        "La contrasena necesita 8 caracteres o mas, con letras **y** numeros (maximo 72 bytes)."
        + _RATE_LIMIT_NOTE
    ),
    responses=errors(422, 429),
)
@limiter.limit(settings.rate_limit_auth)
def register(
    request: Request,
    payload: RegisterRequest,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> RegisterResponse:
    pending_email = auth_service.register(
        session, email=payload.email, password=payload.password, full_name=payload.full_name
    )
    # El correo sale DESPUES de responder (BackgroundTasks): la respuesta no
    # espera al proveedor, asi que tarda lo mismo con un correo nuevo o repetido.
    if pending_email is not None:
        background_tasks.add_task(auth_service.deliver_verification_email, pending_email)
    # Mensaje fijo: es el mismo exista o no ya una cuenta con ese correo.
    return RegisterResponse(
        message="Si el correo puede registrarse, te enviamos un codigo para verificar la cuenta."
    )


@router.post(
    "/verify",
    response_model=MessageResponse,
    summary="Verificar la cuenta con el codigo del correo",
    description=(
        "Activa la cuenta con el codigo de 6 digitos que llego por correo (o que esta en "
        "`./outbox/` en modo dev). El codigo vence a los 15 minutos y sirve una sola vez.\n\n"
        "Un codigo incorrecto, vencido o de una cuenta ya verificada responde el mismo `401` "
        "generico. Tras **5 intentos fallidos** la **cuenta** se bloquea 30 minutos: los intentos "
        "siguientes responden `429` con `Retry-After` (los segundos que faltan para el "
        "desbloqueo). Ese bloqueo es distinto del limite por IP." + _RATE_LIMIT_NOTE
    ),
    responses=errors(
        (
            401,
            "Codigo incorrecto, vencido, o cuenta inexistente / ya verificada (mensaje generico).",
        ),
        422,
        (
            429,
            "Limite por IP excedido (`Retry-After: 60`) o cuenta bloqueada por demasiados "
            "codigos incorrectos (`Retry-After` = segundos hasta el desbloqueo).",
        ),
    ),
)
@limiter.limit(settings.rate_limit_auth)
def verify(request: Request, payload: VerifyRequest, session: SessionDep) -> MessageResponse:
    auth_service.verify_account(session, email=payload.email, code=payload.code)
    return MessageResponse(message="Cuenta verificada correctamente.")


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    summary="Pedir un nuevo codigo de verificacion",
    description=(
        "Emite un codigo nuevo (el anterior deja de servir) para una cuenta pendiente de "
        "verificar. Responde el mismo `200` exista o no la cuenta, o aunque este en espera: "
        "hay que esperar 60 segundos entre un reenvio y el siguiente." + _RATE_LIMIT_NOTE
    ),
    responses=errors(422, 429),
)
@limiter.limit(settings.rate_limit_auth)
def resend_verification(
    request: Request,
    payload: ResendVerificationRequest,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> MessageResponse:
    pending_email = auth_service.resend_verification(session, email=payload.email)
    if pending_email is not None:
        background_tasks.add_task(auth_service.deliver_verification_email, pending_email)
    return MessageResponse(
        message=(
            "Si la cuenta existe y esta pendiente de verificacion, se envio un nuevo codigo. "
            "Si no llega, espera un minuto antes de pedirlo otra vez."
        )
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Iniciar sesion",
    description=(
        "Devuelve el `access_token` (JWT, dura 60 minutos). Copialo y pegalo en el boton "
        "**Authorize** de esta pagina para probar los endpoints protegidos.\n\n"
        "Si tenias un carrito de invitado, llama despues a `POST /cart/merge` con tu "
        "`X-Cart-Token` para pasarlo a tu cuenta." + _RATE_LIMIT_NOTE
    ),
    responses=errors(
        (401, "Credenciales invalidas, o la cuenta todavia no esta verificada."),
        (403, "La cuenta esta suspendida."),
        422,
        429,
    ),
)
@limiter.limit(settings.rate_limit_auth)
def login(request: Request, payload: LoginRequest, session: SessionDep) -> LoginResponse:
    user, token = auth_service.login(session, email=payload.email, password=payload.password)
    return LoginResponse(access_token=token, user=UserRead.model_validate(user))


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Cerrar sesion",
    description=(
        "Revoca el token actual (queda en la lista negra): ya no sirve para ningun endpoint. "
        "Es idempotente: repetirlo con el mismo token tambien responde `200`." + _RATE_LIMIT_NOTE
    ),
    responses=errors((401, "No se envio el encabezado `Authorization: Bearer <token>`."), 429),
)
@limiter.limit(settings.rate_limit_auth)
def logout(request: Request, session: SessionDep, token: BearerToken) -> MessageResponse:
    # Deliberately not CurrentUser: logout must stay idempotent even for a
    # token that's already revoked, expired, or otherwise unusable to
    # authenticate — see the docstring on auth_service.logout for why.
    auth_service.logout(session, token=token)
    return MessageResponse(message="Sesion cerrada.")


@router.get(
    "/me",
    response_model=UserRead,
    summary="Ver mi perfil",
    description="Devuelve los datos de la cuenta duena del token.",
    responses=errors(401, 403),
)
def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)
