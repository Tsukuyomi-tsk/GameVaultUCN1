"""GameVault UCN — FastAPI application entrypoint.

Kept minimal in Fase 0: only the app factory, CORS, and a liveness check.
Routers, the exception handlers, the scheduler and the seeder are wired in
as later phases land (see the project plan).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    description="API REST de GameVault UCN — plataforma de distribucion digital de videojuegos.",
    version="0.1.0",
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
