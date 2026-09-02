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
    admin_password: str = "ChangeMe123!"
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

        if missing:
            raise ValueError(
                "ENVIRONMENT=production requiere credenciales reales. "
                f"Faltan o son de ejemplo: {'; '.join(missing)}"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached Settings instance — the environment is read once per process."""
    return Settings()


settings = get_settings()
