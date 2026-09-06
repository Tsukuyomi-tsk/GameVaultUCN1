"""Identity endpoints: registration, email verification, login, logout.

Every route here is decorated with the shared `limiter` (per the plan's
"Limitacion de Tasa" requirement — brute force and abuse mitigation on
auth specifically, not the whole API). Routers only translate HTTP <->
Python: every actual rule lives in app.services.auth_service.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
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
from app.schemas.user import UserRead
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_auth)
def register(request: Request, payload: RegisterRequest, session: SessionDep) -> RegisterResponse:
    user = auth_service.register(
        session, email=payload.email, password=payload.password, full_name=payload.full_name
    )
    return RegisterResponse(
        message="Cuenta creada. Revisa tu correo para verificarla.",
        user=UserRead.model_validate(user),
    )


@router.post("/verify", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_auth)
def verify(request: Request, payload: VerifyRequest, session: SessionDep) -> MessageResponse:
    auth_service.verify_account(session, email=payload.email, code=payload.code)
    return MessageResponse(message="Cuenta verificada correctamente.")


@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_auth)
def resend_verification(
    request: Request, payload: ResendVerificationRequest, session: SessionDep
) -> MessageResponse:
    auth_service.resend_verification(session, email=payload.email)
    return MessageResponse(message="Si la cuenta existe, se envio un nuevo codigo.")


@router.post("/login", response_model=LoginResponse)
@limiter.limit(settings.rate_limit_auth)
def login(request: Request, payload: LoginRequest, session: SessionDep) -> LoginResponse:
    user, token = auth_service.login(session, email=payload.email, password=payload.password)
    return LoginResponse(access_token=token, user=UserRead.model_validate(user))


@router.post("/logout", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_auth)
def logout(request: Request, session: SessionDep, token: BearerToken) -> MessageResponse:
    # Deliberately not CurrentUser: logout must stay idempotent even for a
    # token that's already revoked, expired, or otherwise unusable to
    # authenticate — see the docstring on auth_service.logout for why.
    auth_service.logout(session, token=token)
    return MessageResponse(message="Sesion cerrada.")


@router.get("/me", response_model=UserRead)
def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)
