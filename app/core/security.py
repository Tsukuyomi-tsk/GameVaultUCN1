"""Password hashing and JWT access tokens.

Uses the `bcrypt` package directly, not passlib: passlib 1.7.4 is
unmaintained and breaks under bcrypt >= 4.1, spamming logs with warnings.
Uses `PyJWT`, not `python-jose`: actively maintained, no open CVEs.

Only an access token exists — no refresh token — which keeps the
blacklist-on-logout story simple and easy to demonstrate (see
app/models/token_blacklist.py for what it does and doesn't cover).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import settings
from app.core.time import utcnow

_ENCODING = "utf-8"

# bcrypt only reads the first 72 BYTES of a password and, since 5.0, raises
# ValueError on anything longer instead of silently truncating. Bytes, not
# characters: "n" is 1 byte in UTF-8 but "ñ" is 2 and an emoji is 4.
BCRYPT_MAX_PASSWORD_BYTES = 72


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with bcrypt. Never store the plain value."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_password.encode(_ENCODING), salt)
    return hashed.decode(_ENCODING)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash.

    A password over bcrypt's 72-byte limit can never match a hash we
    created (registration rejects those), so it is simply "wrong" — False,
    not the ValueError bcrypt would raise, which surfaced as a 500 only for
    emails that exist and so also leaked which accounts are registered.
    """
    if len(plain_password.encode(_ENCODING)) > BCRYPT_MAX_PASSWORD_BYTES:
        return False
    return bcrypt.checkpw(plain_password.encode(_ENCODING), password_hash.encode(_ENCODING))


def create_access_token(*, subject: str, role: str) -> str:
    """Issue a signed JWT carrying `sub`, `role`, a unique `jti`, and `exp`.

    `jti` is what app/models/token_blacklist.py revokes on logout, and what
    app.core.dependencies.get_current_user checks on every request.
    """
    now = utcnow()
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "jti": str(uuid.uuid4()),
        # utcnow() is naive-by-convention (see app.core.time) — PyJWT calls
        # .timestamp() on datetime claims, which treats a naive value as
        # LOCAL time, not UTC. Marking it UTC-aware here (without changing
        # the instant it represents) is what keeps exp/iat correct
        # regardless of the server's timezone.
        "iat": now.replace(tzinfo=UTC),
        "exp": expires_at.replace(tzinfo=UTC),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify signature and expiry, and return the token's claims.

    Raises `jwt.PyJWTError` (or a subclass) on any invalid/expired token —
    callers (app.core.dependencies) translate that into an UnauthorizedError,
    since this module has no business raising an app-level HTTP error.
    """
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])


def token_expiry_from_claims(payload: dict[str, Any]) -> datetime:
    """Convert a decoded token's numeric `exp` claim back into this app's
    naive-UTC convention, so it can be stored directly on TokenBlacklist.
    """
    return datetime.fromtimestamp(payload["exp"], tz=UTC).replace(tzinfo=None)
