"""GameVault UCN — FastAPI application entrypoint.

The lifespan carries both start-up tasks: the seeder and (Fase 7) the
APScheduler jobs, in this same function rather than a second one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.core.logging import configure_logging

# Debe correr antes de importar el resto de la app (por eso el E402 esta
# permitido para este archivo en pyproject.toml): instala el formato JSON en
# el logger raiz (ver app/core/logging.py), de modo que hasta los avisos que
# los modulos emiten AL IMPORTARSE salgan ya en JSON.
configure_logging()

from app.core.handlers import register_exception_handlers
from app.core.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from app.core.rate_limit import limiter
from app.jobs.scheduler import start_scheduler
from app.routers.admin_categories import router as admin_categories_router
from app.routers.admin_games import router as admin_games_router
from app.routers.admin_offers import router as admin_offers_router
from app.routers.admin_stats import router as admin_stats_router
from app.routers.admin_users import router as admin_users_router
from app.routers.auth import router as auth_router
from app.routers.cart import router as cart_router
from app.routers.catalog import router as catalog_router
from app.routers.library import router as library_router
from app.routers.orders import router as orders_router
from app.routers.reviews import router as reviews_router
from app.routers.wishlist import router as wishlist_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    if settings.seed_on_startup:
        # Imported here, not at module load, so `alembic env.py` (which
        # also imports app.core.config) never pulls in the seeder's models
        # before Alembic has decided what to do with the schema.
        from app.seeders.run import run_seeders

        run_seeders()

    # El scheduler arranca AQUI (dentro del lifespan) y no al importar el
    # modulo: asi solo corre cuando la app realmente esta sirviendo, y
    # SCHEDULER_ENABLED=false lo apaga (necesario si se lanzan varios
    # workers, o jobs duplicados correrian N veces). Devuelve None si esta
    # apagado.
    scheduler = start_scheduler()
    try:
        yield
    finally:
        # Al apagar la app se detiene el scheduler; wait=False para no
        # bloquear el cierre esperando a un job en curso.
        if scheduler is not None:
            scheduler.shutdown(wait=False)


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
    # Un navegador solo deja leer a JavaScript las cabeceras de respuesta
    # "seguras"; X-Request-ID y Retry-After (la usa el 429 de /auth/verify
    # para decir cuanto esperar) hay que exponerlas explicitamente.
    expose_headers=[REQUEST_ID_HEADER, "Retry-After"],
)
# Se agrega ULTIMO a proposito: en Starlette el ultimo middleware agregado
# es el mas externo, asi que el request_id existe antes que cualquier otro
# middleware o ruta, y el log de acceso cubre tambien lo rechazado por CORS
# o por el rate limit.
app.add_middleware(RequestContextMiddleware)

app.include_router(auth_router)
app.include_router(catalog_router)
# Los 5 routers del backoffice de admin (Fase 4) — cada uno ya trae su
# propio prefix="/admin/..." definido en su archivo, asi que aca solo hay
# que registrarlos.
app.include_router(admin_games_router)
app.include_router(admin_categories_router)
app.include_router(admin_offers_router)
app.include_router(admin_users_router)
app.include_router(admin_stats_router)
# Carrito, checkout/pedidos y biblioteca (Fase 5).
app.include_router(cart_router)
app.include_router(orders_router)
app.include_router(library_router)
# Resenas y wishlist (Fase 6).
app.include_router(reviews_router)
app.include_router(wishlist_router)

# app.mount (a diferencia de include_router) no maneja rutas dinamicas de
# la API: sirve archivos ESTATICOS directamente desde una carpeta del
# disco. Esto es lo que hace que una imagen guardada en modo dev-local
# (ver cloudinary_client.py) sea accesible por HTTP en "/media/<archivo>".
# Serves ./media/ when Cloudinary credentials are absent (settings.media_mode
# == "dev-local") — see the plan's "Contrato del fallback". check_dir=False
# because the folder is only created lazily, on the first dev-mode upload.
app.mount("/media", StaticFiles(directory="media", check_dir=False), name="media")


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
