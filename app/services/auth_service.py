"""Business logic for registration, login, logout and email verification.

The "one live code at a time" invariant lives entirely here (see
"Ciclo de vida del codigo de verificacion" in the plan):

- Issuing a code invalidates every previous unconsumed code for that user,
  in the same transaction, before the new one is inserted.
- The failed-attempt counter lives on User, not on VerificationCode — if it
  lived on the code, requesting a new one would reset it and the max-
  attempts limit would be trivial to bypass.
- Once `verification_blocked_until` has passed, the very next attempt or
  resend clears it AND resets the counter to zero — without that reset the
  counter would stay pinned at the maximum forever, and the first attempt
  after the block expired would immediately re-trigger it.

Resend and verify give the same generic response whether the account
exists, is already verified, or the code was wrong — never enough to let a
caller enumerate registered emails or brute-force distinguish failure modes.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

import jwt
from sqlmodel import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    token_expiry_from_claims,
    verify_password,
)
from app.core.time import utcnow
from app.integrations.resend_client import send_verification_email
from app.models import TokenBlacklist, User, VerificationCode
from app.repositories.token_blacklist_repository import TokenBlacklistRepository
from app.repositories.user_repository import UserRepository
from app.repositories.verification_code_repository import VerificationCodeRepository

_GENERIC_VERIFICATION_ERROR = "Codigo invalido o expirado."
_GENERIC_BLOCKED_ERROR = "Demasiados intentos. Solicita un nuevo codigo mas tarde."


def _generate_numeric_code() -> str:
    """A cryptographically random, zero-padded numeric code."""
    upper_bound = 10**settings.verification_code_length
    return str(secrets.randbelow(upper_bound)).zfill(settings.verification_code_length)


def _hash_code(code: str) -> str:
    # Reuses the password hasher: a short numeric code deserves the same
    # "never store in plain text" treatment as a password.
    return hash_password(code)


def _reset_expired_block(user: User, now) -> None:
    """Clear a suspension window that has already elapsed, and reset the
    attempt counter with it — see the module docstring for why both must
    move together.
    """
    if user.verification_blocked_until is not None and user.verification_blocked_until <= now:
        user.verification_blocked_until = None
        user.verification_attempts = 0


def _issue_verification_code(session: Session, user: User) -> str:
    now = utcnow()
    codes = VerificationCodeRepository(session)
    codes.invalidate_all_unconsumed(user.id, now)

    plain_code = _generate_numeric_code()
    codes.add(
        VerificationCode(
            user_id=user.id,
            code_hash=_hash_code(plain_code),
            expires_at=now + timedelta(minutes=settings.verification_code_ttl_minutes),
        )
    )
    send_verification_email(to_email=user.email, code=plain_code)
    return plain_code


def register(session: Session, *, email: str, password: str, full_name: str) -> User:
    """Create the account and send its first verification code.

    Uniqueness is the only check that needs to live here rather than in
    the request schema — it needs a database read.
    """
    users = UserRepository(session)
    if users.get_by_email(email) is not None:
        raise ConflictError("Ya existe una cuenta con este correo.")

    user = users.add(User(email=email, password_hash=hash_password(password), full_name=full_name))
    _issue_verification_code(session, user)
    session.commit()
    session.refresh(user)
    return user


def resend_verification(session: Session, *, email: str) -> None:
    users = UserRepository(session)
    user = users.get_by_email(email)
    if user is None or user.is_verified:
        return  # generic no-op — see module docstring

    now = utcnow()
    _reset_expired_block(user, now)
    if user.verification_blocked_until is not None:
        raise UnauthorizedError(_GENERIC_BLOCKED_ERROR)

    codes = VerificationCodeRepository(session)
    latest = codes.get_latest_for_user(user.id)
    if latest is not None:
        cooldown_ends = latest.created_at + timedelta(
            seconds=settings.verification_resend_cooldown_seconds
        )
        if now < cooldown_ends:
            raise UnauthorizedError("Espera antes de solicitar otro codigo.")

    _issue_verification_code(session, user)
    session.commit()


def verify_account(session: Session, *, email: str, code: str) -> None:
    users = UserRepository(session)
    user = users.get_by_email(email)
    if user is None:
        raise UnauthorizedError(_GENERIC_VERIFICATION_ERROR)
    if user.is_verified:
        return

    now = utcnow()
    _reset_expired_block(user, now)
    if user.verification_blocked_until is not None:
        raise UnauthorizedError(_GENERIC_BLOCKED_ERROR)

    codes = VerificationCodeRepository(session)
    active = codes.get_active_for_user(user.id, now)
    if active is None or not verify_password(code, active.code_hash):
        user.verification_attempts += 1
        if user.verification_attempts >= settings.verification_max_attempts:
            user.verification_blocked_until = now + timedelta(
                minutes=settings.verification_block_minutes
            )
        session.add(user)
        session.commit()
        raise UnauthorizedError(_GENERIC_VERIFICATION_ERROR)

    active.consumed_at = now
    user.is_verified = True
    user.verification_attempts = 0
    session.add(active)
    session.add(user)
    session.commit()


def login(session: Session, *, email: str, password: str) -> tuple[User, str]:
    users = UserRepository(session)
    user = users.get_by_email(email)
    if user is None or not verify_password(password, user.password_hash):
        raise UnauthorizedError("Credenciales invalidas.")
    if not user.is_verified:
        raise UnauthorizedError("Debes verificar tu cuenta antes de iniciar sesion.")
    if user.is_suspended:
        # 403, not 401: the credentials themselves are correct — matches
        # how app.core.dependencies.get_current_user treats suspension on
        # an already-authenticated request, so a client can rely on the
        # same status code meaning the same thing everywhere.
        raise ForbiddenError("Tu cuenta ha sido suspendida.")

    token = create_access_token(subject=str(user.id), role=user.role.value)
    return user, token


def logout(session: Session, *, token: str) -> None:
    """Blacklist the current access token's `jti`.

    Genuinely idempotent, on purpose: logging out twice with the same
    token — even one already revoked, expired, or otherwise malformed — is
    a no-op, never an error. That's why the router hands this the raw
    bearer token instead of a full CurrentUser: requiring the token to
    still be currently valid would reject the exact case this exists to
    handle (a client retrying logout, or calling it on a token that's
    already dead). A token that can't even be decoded has nothing to
    revoke, so it's treated the same as an already-blacklisted one.
    """
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        return
    jti = payload["jti"]

    blacklist = TokenBlacklistRepository(session)
    if blacklist.is_revoked(jti):
        return

    blacklist.add(
        TokenBlacklist(
            jti=jti,
            user_id=int(payload["sub"]),
            expires_at=token_expiry_from_claims(payload),
        )
    )
    session.commit()
