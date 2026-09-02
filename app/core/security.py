"""Password hashing.

Only hashing lives here for now — this file grows JWT creation/decoding in
Fase 2 (Identidad y Seguridad). It's introduced a phase early because the
Fase 1 seeder needs to store real, verifiable password hashes for the admin
and test accounts (see app/seeders), not placeholder values that would have
to be redone once login exists.

Uses the `bcrypt` package directly, not passlib: passlib 1.7.4 is
unmaintained and breaks under bcrypt >= 4.1, spamming logs with warnings.
"""

from __future__ import annotations

import bcrypt

_ENCODING = "utf-8"


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with bcrypt. Never store the plain value."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_password.encode(_ENCODING), salt)
    return hashed.decode(_ENCODING)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode(_ENCODING), password_hash.encode(_ENCODING))
