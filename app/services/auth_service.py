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

Register, resend and verify give the same generic response whether the
account exists, is already verified, or the code was wrong — never enough to
let a caller enumerate registered emails or brute-force distinguish failure
modes. Login also hides which emails exist, in its message AND its timing
(a dummy bcrypt check runs when the email is unknown). The one deliberate
exception is `verify` turning away a BLOCKED account with 429: it needs
five wrong attempts first, and the rate limit caps those per IP.
"""

from __future__ import annotations

import logging
import math
import secrets
from datetime import datetime, timedelta

import jwt
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlmodel import Session

from app.core.config import settings
from app.core.exceptions import ForbiddenError, RateLimitError, UnauthorizedError
from app.core.logging import log_event
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

logger = logging.getLogger(__name__)

_GENERIC_VERIFICATION_ERROR = "Codigo invalido o expirado."
_GENERIC_BLOCKED_ERROR = "Demasiados intentos. Solicita un nuevo codigo mas tarde."

# Hash de una contrasena que nadie usa. Cuando el login recibe un correo que
# no existe se compara contra este hash para gastar el mismo tiempo de bcrypt
# que con un correo real; sin eso, la diferencia de tiempo delata que cuentas
# existen. Se calcula una vez al importar (mismo costo que los hashes reales).
_DUMMY_PASSWORD_HASH = hash_password("contrasena-que-nadie-usa-1")


def _generate_numeric_code() -> str:
    """A cryptographically random, zero-padded numeric code."""
    upper_bound = 10**settings.verification_code_length
    return str(secrets.randbelow(upper_bound)).zfill(settings.verification_code_length)


def _hash_code(code: str) -> str:
    # Reuses the password hasher: a short numeric code deserves the same
    # "never store in plain text" treatment as a password.
    return hash_password(code)


def _reset_expired_block(session: Session, user: User, now) -> bool:
    """Clear a suspension window that has already elapsed, and reset the
    attempt counter with it — see the module docstring for why both must
    move together. Done as one conditional UPDATE (not by mutating `user`)
    so a stale read can't overwrite attempts claimed by a concurrent
    request; `user` is refreshed afterwards so callers see the result.
    Returns False if the account vanished meanwhile (deleted by the
    stale-account job between the caller's lookup and this refresh).
    """
    if UserRepository(session).reset_expired_verification_block(user.id, now):
        session.commit()
        try:
            session.refresh(user)
        except InvalidRequestError:
            # refresh() de una fila que ya no existe: la cuenta fue borrada.
            return False
    return True


def _blocked_error(blocked_until: datetime | None, now: datetime) -> RateLimitError:
    """429 for an account whose verification is blocked, with Retry-After.

    `blocked_until` is None when the block was detected by the atomic claim
    (which doesn't return the date): the full block window is the upper bound.
    """
    if blocked_until is not None:
        seconds = max(1, math.ceil((blocked_until - now).total_seconds()))
    else:
        seconds = settings.verification_block_minutes * 60
    return RateLimitError(_GENERIC_BLOCKED_ERROR, headers={"Retry-After": str(seconds)})


def _log_verification_blocked(user_id: int, *, stage: str, reason: str) -> None:
    """Security event: verification is (or just became) blocked for this
    account. `stage` says which endpoint saw it ("verify" / "resend") and
    `reason` why: "max_attempts_reached" is the transition into the block
    (the attempt that spent the last try failed); "block_active" is a later
    request being turned away while the block lasts.
    """
    # Recibe el id (no el objeto User) a proposito: tras un commit/rollback
    # el objeto queda "expirado" y leer user.id dispararia una consulta, que
    # falla con ObjectDeletedError si el job de limpieza borro la cuenta.
    # WARNING: es senal de posible fuerza bruta sobre el codigo. Nunca se
    # incluye el codigo que se intento.
    log_event(
        logger,
        "verification_blocked",
        level=logging.WARNING,
        user_id=user_id,
        stage=stage,
        reason=reason,
    )


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


def register(session: Session, *, email: str, password: str, full_name: str) -> None:
    """Create the account and send its first verification code.

    The caller gets the SAME answer whether the email was new or already
    registered (nothing is returned; the router sends a fixed message), so
    this endpoint can't be used to find out who has an account. For an
    existing email nothing is created or sent, and the same amount of bcrypt
    work is spent so response time doesn't give it away either.
    """
    users = UserRepository(session)
    existing = users.get_by_email(email)
    if existing is not None:
        _ignore_duplicate_registration(password, user_id=existing.id)
        return

    try:
        user = users.add(
            User(email=email, password_hash=hash_password(password), full_name=full_name)
        )
    except IntegrityError:
        # Two requests with the same email both passed the check above; the
        # UNIQUE index on users.email arbitrated and this one lost. Same
        # answer as the sequential duplicate, not a 500 nor a 409.
        session.rollback()
        _ignore_duplicate_registration(password, user_id=None)
        return
    _issue_verification_code(session, user)
    session.commit()
    session.refresh(user)
    log_event(logger, "user_registered", user_id=user.id, email=user.email)


def _ignore_duplicate_registration(password: str, *, user_id: int | None) -> None:
    """Spend the bcrypt work a real registration would (password hash + code
    hash) and log the attempt; creates and sends nothing.
    """
    hash_password(password)
    _hash_code(_generate_numeric_code())
    # INFO: un correo repetido es normal (alguien que olvido que ya tenia
    # cuenta); lo que importa para detectar abuso es el volumen de estos
    # eventos. No se registra la contrasena.
    log_event(logger, "register_duplicate_ignored", user_id=user_id)


def resend_verification(session: Session, *, email: str) -> None:
    users = UserRepository(session)
    user = users.get_by_email(email)
    if user is None or user.is_verified:
        return  # generic no-op — see module docstring

    now = utcnow()
    user_id = user.id
    if not _reset_expired_block(session, user, now):
        return  # la cuenta fue borrada mientras tanto: mismo no-op generico
    if user.verification_blocked_until is not None:
        _log_verification_blocked(user_id, stage="resend", reason="block_active")
        # Respuesta generica, igual que para una cuenta inexistente: un 429
        # solo para cuentas reales delataria que el correo esta registrado.
        return

    codes = VerificationCodeRepository(session)
    latest = codes.get_latest_for_user(user_id)
    if latest is not None:
        cooldown_ends = latest.created_at + timedelta(
            seconds=settings.verification_resend_cooldown_seconds
        )
        if now < cooldown_ends:
            # Mismo criterio que el bloqueo: no se envia otro codigo, pero la
            # respuesta es la generica (un error aqui delataria la cuenta).
            log_event(
                logger,
                "verification_resend_skipped",
                level=logging.INFO,
                user_id=user_id,
                reason="cooldown",
            )
            return

    try:
        _issue_verification_code(session, user)
        session.commit()
    except IntegrityError:
        # La cuenta (no verificada y vencida) pudo ser borrada por el job de
        # limpieza justo entre leerla y insertarle el codigo nuevo: la FK del
        # codigo ya no encuentra a su usuario. Es el mismo caso "cuenta
        # inexistente" del inicio de esta funcion: se deshace y se responde
        # con el no-op generico, sin 500.
        session.rollback()


def verify_account(session: Session, *, email: str, code: str) -> None:
    users = UserRepository(session)
    user = users.get_by_email(email)
    if user is None:
        raise UnauthorizedError(_GENERIC_VERIFICATION_ERROR)
    if user.is_verified:
        return

    now = utcnow()
    # El id se copia a una variable local: despues de cada commit/rollback el
    # objeto `user` queda expirado, y si el job de limpieza borro la cuenta
    # entremedio, volver a leer `user.id` lanzaria ObjectDeletedError (500).
    user_id = user.id
    if not _reset_expired_block(session, user, now):
        raise UnauthorizedError(_GENERIC_VERIFICATION_ERROR)
    if user.verification_blocked_until is not None:
        _log_verification_blocked(user_id, stage="verify", reason="block_active")
        raise _blocked_error(user.verification_blocked_until, now)

    # The attempt is spent BEFORE the code is checked, atomically, and
    # committed right away (short transaction: bcrypt below is slow and
    # must not hold the database write lock). If the budget is already
    # gone — including to requests racing this one — the claim fails and
    # the code is never even compared. A correct code wipes the counter
    # below, so honest users are unaffected by the order.
    users = UserRepository(session)
    attempts_used = users.claim_verification_attempt(
        user_id,
        max_attempts=settings.verification_max_attempts,
        blocked_until=now + timedelta(minutes=settings.verification_block_minutes),
    )
    session.commit()
    if attempts_used is None:
        # Rechazado por el UPDATE atomico (otra request agoto el cupo antes,
        # o la cuenta ya no existe): mismo evento que el rechazo temprano.
        _log_verification_blocked(user_id, stage="verify", reason="block_active")
        raise _blocked_error(None, now)

    codes = VerificationCodeRepository(session)
    active = codes.get_active_for_user(user_id, now)
    if active is None or not verify_password(code, active.code_hash):
        # The block (if this was the last allowed attempt) was already set
        # by the claim itself — nothing left to persist.
        log_event(logger, "verification_failed", level=logging.WARNING, user_id=user_id)
        if attempts_used >= settings.verification_max_attempts:
            # Este fallo fue el que agoto el cupo: es la TRANSICION a
            # "bloqueada" (el UPDATE del claim ya fijo blocked_until).
            _log_verification_blocked(user_id, stage="verify", reason="max_attempts_reached")
        raise UnauthorizedError(_GENERIC_VERIFICATION_ERROR)

    # Codigo correcto. Se consume y se marca la cuenta con dos UPDATE
    # condicionales (no con "cargar el objeto, modificarlo y guardarlo"):
    # mientras bcrypt comparaba, el job de limpieza pudo borrar esta cuenta
    # (y su codigo) por vencida, o una request concurrente pudo gastar el
    # mismo codigo. En ambos casos el UPDATE no encuentra fila y devuelve
    # False; guardar un objeto cuya fila desaparecio lanzaria StaleDataError
    # (un 500).
    consumed = codes.consume(active.id, now)
    verified = consumed and users.mark_verified(user_id)
    if not verified:
        # Se deshace lo que haya alcanzado a escribirse (p. ej. el codigo
        # consumido si la cuenta no estaba) y se responde con el error
        # generico: la cuenta no queda "medio verificada" ni se recrea.
        session.rollback()
        log_event(
            logger,
            "verification_failed",
            level=logging.WARNING,
            user_id=user_id,
            reason="account_or_code_gone",
        )
        raise UnauthorizedError(_GENERIC_VERIFICATION_ERROR)
    session.commit()
    log_event(logger, "account_verified", user_id=user_id)


def login(session: Session, *, email: str, password: str) -> tuple[User, str]:
    users = UserRepository(session)
    user = users.get_by_email(email)
    # Siempre se ejecuta UNA comparacion bcrypt, exista o no el correo: asi el
    # tiempo de respuesta no distingue "correo inexistente" de "contrasena
    # incorrecta" (ver _DUMMY_PASSWORD_HASH).
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_ok = verify_password(password, password_hash)
    if user is None or not password_ok:
        # El cliente recibe siempre el mismo mensaje generico (para no
        # revelar que correos existen), pero el log SI distingue el motivo:
        # sirve para detectar fuerza bruta sobre una cuenta real frente a
        # simple ruido con correos inexistentes. Nunca se registra la
        # contrasena enviada.
        log_event(
            logger,
            "login_failed",
            level=logging.WARNING,
            email=email,
            reason="unknown_email" if user is None else "wrong_password",
        )
        raise UnauthorizedError("Credenciales invalidas.")
    if not user.is_verified:
        log_event(
            logger,
            "login_failed",
            level=logging.WARNING,
            email=email,
            user_id=user.id,
            reason="unverified",
        )
        raise UnauthorizedError("Debes verificar tu cuenta antes de iniciar sesion.")
    if user.is_suspended:
        log_event(
            logger,
            "login_failed",
            level=logging.WARNING,
            email=email,
            user_id=user.id,
            reason="suspended",
        )
        # 403, not 401: the credentials themselves are correct — matches
        # how app.core.dependencies.get_current_user treats suspension on
        # an already-authenticated request, so a client can rely on the
        # same status code meaning the same thing everywhere.
        raise ForbiddenError("Tu cuenta ha sido suspendida.")

    token = create_access_token(subject=str(user.id), role=user.role.value)
    log_event(logger, "login_success", user_id=user.id)
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

    try:
        blacklist.add(
            TokenBlacklist(
                jti=jti,
                user_id=int(payload["sub"]),
                expires_at=token_expiry_from_claims(payload),
            )
        )
        session.commit()
    except IntegrityError:
        # A concurrent logout with the same token revoked the jti first:
        # the goal (token revoked) is already met, so stay a silent no-op.
        session.rollback()
        return
    log_event(logger, "logout", user_id=int(payload["sub"]))
