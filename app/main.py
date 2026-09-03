"""GameVault UCN — FastAPI application entrypoint.

Remaining routers and the APScheduler jobs are wired in as later phases
land (see the project plan). The lifespan already carries the seeder —
Fase 7 extends this same function to also start the scheduler, rather than
adding a second one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.core.handlers import register_exception_handlers
from app.core.rate_limit import limiter
from app.routers.auth import router as auth_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    if settings.seed_on_startup:
        # Imported here, not at module load, so `alembic env.py` (which
        # also imports app.core.config) never pulls in the seeder's models
        # before Alembic has decided what to do with the schema.
        from app.seeders.run import run_seeders

        run_seeders()
    yield


app = FastAPI(
    title=settings.app_name,
    description="API REST de GameVault UCN — plataforma de distribucion digital de videojuegos.",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
register_exception_handlers(app)

# allow_credentials stays False: this API authenticates with a Bearer JWT,
# never cookies, so there is no reason to pair it with a wildcard origin
# (browsers reject that combination anyway).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, object]:
    """Liveness check, plus which mode each third-party integration is
    actually running in — see the plan's "Contrato del fallback": this is
    what makes a dev-mode fallback impossible to mistake for the real
    thing.
    """
    return {
        "status": "ok",
        "environment": settings.environment,
        "integrations": {
            "email": settings.email_mode,
            "media": settings.media_mode,
        },
    }
