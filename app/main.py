"""GameVault UCN — FastAPI application entrypoint.

Routers, the centralized exception handlers and the APScheduler jobs are
wired in as later phases land (see the project plan). The lifespan below
already carries the seeder — Fase 7 extends this same function to also
start the scheduler, rather than adding a second one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings


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


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Liveness check. Extended in later phases with integration status."""
    return {"status": "ok", "environment": settings.environment}
