"""Detect and rotate the public demo credentials left by the dev seeder.

A database that was seeded in development has an admin with the password
published in the repo (`ChangeMe123!`) and demo users with `Password123!`.
Changing ADMIN_PASSWORD afterwards does NOT touch the stored hash (the
seeder never updates an existing user), so deploying that database to
production would leave those logins open to anyone who read the repo.

This module closes that gap without overwriting anything silently:

- `check_production_credentials()` runs when the app starts in production and
  REFUSES to start while any active account still accepts a public password.
- `python -m app.seeders.credentials` is the explicit, one-off transition:
  it sets the admin's password from ADMIN_PASSWORD and suspends the demo
  users. Only accounts that still accept the public password are touched.

Run it from a shell with the production environment variables set.
"""

from __future__ import annotations

import logging

from sqlmodel import Session

from app.core.config import EXAMPLE_ADMIN_PASSWORD, settings
from app.core.database import engine
from app.core.logging import log_event
from app.core.security import hash_password, verify_password
from app.core.time import utcnow
from app.models import User
from app.repositories.user_repository import UserRepository
from app.seeders.data import SEED_USER_PASSWORD, TEST_USERS

logger = logging.getLogger(__name__)

_DEMO_SUSPENSION_REASON = "Cuenta de demostracion desactivada al pasar a produccion."


class PublicCredentialsError(RuntimeError):
    """An active account still accepts a password published in the repo."""


def _accounts_with_public_password(session: Session) -> tuple[User | None, list[User]]:
    """The admin (or None) and the demo users that still accept a public password.

    Suspended accounts are ignored: they cannot log in, so their password is
    not an open door.
    """
    users = UserRepository(session)

    admin = users.get_by_email(settings.admin_email)
    if (
        admin is None
        or admin.is_suspended
        or not verify_password(EXAMPLE_ADMIN_PASSWORD, admin.password_hash)
    ):
        admin = None

    demo_users: list[User] = []
    for data in TEST_USERS:
        user = users.get_by_email(data["email"])
        if (
            user is not None
            and not user.is_suspended
            and verify_password(SEED_USER_PASSWORD, user.password_hash)
        ):
            demo_users.append(user)
    return admin, demo_users


def assert_no_public_credentials(session: Session) -> None:
    """Raise PublicCredentialsError if any active account has a public password."""
    admin, demo_users = _accounts_with_public_password(session)
    exposed = ([admin.email] if admin else []) + [user.email for user in demo_users]
    if exposed:
        log_event(
            logger,
            "public_credentials_detected",
            level=logging.ERROR,
            accounts=exposed,
        )
        raise PublicCredentialsError(
            "ENVIRONMENT=production: estas cuentas todavia aceptan una contrasena publica "
            f"del repositorio: {', '.join(exposed)}. La base viene de un entorno de "
            "desarrollo. Despliega con una base nueva o ejecuta una vez, con las variables "
            "de produccion: python -m app.seeders.credentials"
        )


def check_production_credentials() -> None:
    """Startup guard: only meaningful (and only run) in production."""
    if settings.environment != "production":
        return
    with Session(engine) as session:
        assert_no_public_credentials(session)


def rotate_public_credentials(session: Session) -> tuple[bool, int]:
    """Replace the admin's public password with ADMIN_PASSWORD and suspend the
    demo users. Returns (admin_rotated, demo_users_suspended). Commits.
    """
    admin, demo_users = _accounts_with_public_password(session)

    if admin is not None:
        admin.password_hash = hash_password(settings.admin_password)
        session.add(admin)
        log_event(logger, "admin_password_rotated", user_id=admin.id)

    now = utcnow()
    for user in demo_users:
        user.is_suspended = True
        user.suspended_at = now
        user.suspension_reason = _DEMO_SUSPENSION_REASON
        session.add(user)
        log_event(logger, "demo_user_suspended", user_id=user.id)

    session.commit()
    return admin is not None, len(demo_users)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if settings.environment != "production":
        raise SystemExit(
            "Este comando es solo para la transicion a produccion "
            "(ENVIRONMENT=production). En desarrollo las credenciales de demo son esperadas."
        )
    with Session(engine) as db_session:
        rotated, suspended = rotate_public_credentials(db_session)
    print(
        f"Admin rotado: {'si' if rotated else 'no (ya tenia otra contrasena)'}. "
        f"Usuarios demo suspendidos: {suspended}."
    )
