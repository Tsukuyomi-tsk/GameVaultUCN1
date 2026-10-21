"""Application configuration, loaded from environment variables / .env.

See .env.example for the full list of variables with explanations. Every
field has a safe development default so the app can start without a .env
file at all; ENVIRONMENT=production is the only mode that requires real
credentials (enforced by the validator below).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_EXAMPLE_SECRET_KEY = "change-this-secret-key-in-your-own-env-file"
EXAMPLE_ADMIN_PASSWORD = "ChangeMe123!"

# bcrypt solo lee los primeros 72 BYTES de una contrasena y desde la version 5
# lanza ValueError con mas (ver app/core/security.py, que reusa esta constante).
BCRYPT_MAX_PASSWORD_BYTES = 72
_ADMIN_PASSWORD_MIN_LENGTH = 8


class Settings(BaseSettings):
    """Central application settings, one field per .env variable."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "GameVault UCN"
    environment: Literal["development", "production"] = "development"
    debug: bool = True
    cors_origins: str = "*"
    # Nivel minimo de los logs JSON (Fase 7). Con DEBUG ademas se imprimen
    # las sentencias SQL (ver app/core/logging.py).
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # --- Database ---
    database_url: str = "sqlite:///./gamevault.db"

    # --- Security / JWT ---
    secret_key: str = _EXAMPLE_SECRET_KEY
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # --- Rate limiting (endpoints under /auth) ---
    rate_limit_auth: str = "5/minute"

    # --- Email verification (registration) ---
    verification_code_length: int = 6
    verification_code_ttl_minutes: int = 15
    verification_max_attempts: int = 5
    verification_block_minutes: int = 30
    verification_resend_cooldown_seconds: int = 60

    # --- Scheduled jobs (APScheduler) ---
    scheduler_enabled: bool = True
    unverified_account_ttl_hours: int = 48
    blacklist_purge_interval_hours: int = 6
    guest_cart_ttl_days: int = 30

    # --- Seeder ---
    seed_on_startup: bool = True
    admin_email: str = "admin@gamevault.ucn.cl"
    admin_password: str = EXAMPLE_ADMIN_PASSWORD
    admin_full_name: str = "Administrador GameVault"

    # --- Resend (transactional email) ---
    resend_api_key: str = ""
    resend_from_email: str = "GameVault UCN <no-reply@gamevault.ucn.cl>"

    # --- Cloudinary (catalog media) ---
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS_ORIGINS parsed into a list, e.g. "*" or "a,b,c"."""
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def email_mode(self) -> Literal["resend", "dev-outbox"]:
        """Which email backend is actually active, based on credentials.

        This is the single source of truth other modules must consult
        (integrations/resend_client.py, GET /health) — never re-derive it
        by checking resend_api_key directly elsewhere.
        """
        return "resend" if self.resend_api_key else "dev-outbox"

    @property
    def media_mode(self) -> Literal["cloudinary", "dev-local"]:
        """Which media backend is actually active, based on credentials."""
        has_cloudinary_credentials = bool(
            self.cloudinary_cloud_name and self.cloudinary_api_key and self.cloudinary_api_secret
        )
        return "cloudinary" if has_cloudinary_credentials else "dev-local"

    def _admin_password_problem(self) -> str | None:
        """Why ADMIN_PASSWORD can't be used in production, or None if it can."""
        password = self.admin_password
        if len(password) < _ADMIN_PASSWORD_MIN_LENGTH:
            return f"minimo {_ADMIN_PASSWORD_MIN_LENGTH} caracteres"
        if len(password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
            return f"maximo {BCRYPT_MAX_PASSWORD_BYTES} bytes"
        if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            return "debe combinar letras y numeros"
        return None

    @model_validator(mode="after")
    def _forbid_dev_fallback_in_production(self) -> Settings:
        """The dev fallback for Resend/Cloudinary never applies in production.

        A production deploy without real credentials must fail loudly at
        startup, not silently degrade to writing emails/images to disk.
        """
        if self.environment != "production":
            return self

        missing: list[str] = []
        if self.email_mode != "resend":
            missing.append("RESEND_API_KEY")
        if self.media_mode != "cloudinary":
            missing.append("CLOUDINARY_CLOUD_NAME / CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET")
        if self.secret_key == _EXAMPLE_SECRET_KEY:
            missing.append("SECRET_KEY (usando el valor de ejemplo)")
        # El seeder crea al admin con ADMIN_PASSWORD en cada arranque: con el
        # valor de ejemplo, cualquiera que lea el repo entra como admin.
        if self.admin_password == EXAMPLE_ADMIN_PASSWORD:
            missing.append("ADMIN_PASSWORD (usando el valor de ejemplo)")
        else:
            # Mismas reglas que el registro publico (schemas/auth.py): sin
            # esto, una variable vacia crearia un admin SIN contrasena y una
            # de mas de 72 bytes haria fallar el seeder con un ValueError.
            admin_password_problem = self._admin_password_problem()
            if admin_password_problem:
                missing.append(f"ADMIN_PASSWORD ({admin_password_problem})")
        # "*" permite que cualquier sitio web llame a la API desde un navegador.
        if "*" in self.cors_origins_list:
            missing.append("CORS_ORIGINS (no puede ser '*', lista los origenes permitidos)")
        if self.debug:
            missing.append("DEBUG (debe ser false)")
        # El seeder siembra datos de demo (incluidos usuarios con contrasena
        # publica): en produccion se ejecuta solo a mano, nunca al arrancar.
        if self.seed_on_startup:
            missing.append("SEED_ON_STARTUP (debe ser false)")

        if missing:
            raise ValueError(
                "ENVIRONMENT=production requiere una configuracion segura. "
                f"Faltan, son de ejemplo o no son validas: {'; '.join(missing)}"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached Settings instance — the environment is read once per process."""
    return Settings()


settings = get_settings()
