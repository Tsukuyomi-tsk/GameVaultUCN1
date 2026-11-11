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


# Texto (Markdown) que Swagger UI muestra en la cabecera de /docs. Es la "guia
# de uso" para probar la API a mano, asi que reune lo que un alumno necesita
# saber ANTES de tocar un endpoint.
_API_DESCRIPTION = """
API REST de **GameVault UCN**, una plataforma de distribucion digital de videojuegos.
Todo se puede probar desde esta pagina con el boton **Try it out** de cada endpoint.

### Como autenticarte
1. Crea una cuenta con `POST /auth/register` y verifica el correo con `POST /auth/verify`
   (en modo dev el codigo no llega por correo: esta en un archivo dentro de `./outbox/`).
   O usa un usuario ya sembrado (ver el README).
2. Haz `POST /auth/login` y copia el `access_token` de la respuesta.
3. Pulsa **Authorize** (arriba a la derecha) y pega ese token. Swagger agrega
   `Authorization: Bearer <token>` a todas las peticiones.
4. Para probar como **invitado** (por ejemplo el carrito), pulsa **Authorize** y luego
   **Logout** dentro del dialogo: Swagger deja de mandar el token.

### Convenciones de la API
- **Errores:** todos tienen la misma forma, `{"error": {"code", "message", "details"}, "request_id"}`.
- **Fechas y horas:** siempre en **UTC**, sin sufijo `Z` en las respuestas. Si envias una fecha
  con zona (`Z` o `-03:00`) se convierte a UTC.
- **Paginacion:** `page` (desde 1) y `size` (maximo 100); la respuesta trae `total` y `pages`.
- **Limite de tasa:** los endpoints `/auth/*` aceptan 5 peticiones por minuto **por IP y por
  endpoint**; el exceso responde `429` con `Retry-After`. Es distinto del bloqueo por **cuenta**
  tras 5 codigos de verificacion incorrectos (tambien `429`, con su propio `Retry-After`).
- **Cabecera `X-Request-ID`:** cada respuesta la trae; sirve para encontrar la peticion en los logs.
"""

# Una entrada por tag: Swagger UI muestra este texto bajo el nombre de cada
# grupo de endpoints. El orden de la lista es el orden en la pagina.
_TAGS_METADATA = [
    {
        "name": "auth",
        "description": "Registro, verificacion del correo, inicio y cierre de sesion.",
    },
    {
        "name": "catalog",
        "description": "Catalogo **publico**: busqueda, detalle de juegos y categorias.",
    },
    {
        "name": "cart",
        "description": "Carrito. Funciona como invitado (`X-Cart-Token`) o con sesion.",
    },
    {"name": "orders", "description": "Checkout idempotente, historial y boleta en PDF."},
    {"name": "library", "description": "Los juegos que el usuario ya compro."},
    {"name": "reviews", "description": "Resenas: solo de juegos que el usuario posee."},
    {"name": "wishlist", "description": "Lista de deseados del usuario."},
    {"name": "admin-games", "description": "Backoffice: juegos e imagenes. **Solo admin.**"},
    {"name": "admin-categories", "description": "Backoffice: categorias. **Solo admin.**"},
    {"name": "admin-offers", "description": "Backoffice: ofertas con vigencia. **Solo admin.**"},
    {
        "name": "admin-users",
        "description": "Backoffice: listar, suspender y reactivar. **Solo admin.**",
    },
    {
        "name": "admin-stats",
        "description": "Backoffice: juegos mas deseados y mas comprados. **Solo admin.**",
    },
    {"name": "health", "description": "Estado del servidor y modo de las integraciones."},
]

app = FastAPI(
    title=settings.app_name,
    description=_API_DESCRIPTION,
    version="0.1.0",
    openapi_tags=_TAGS_METADATA,
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


@app.get(
    "/health",
    tags=["health"],
    summary="Estado del servidor",
    description=(
        "Responde `ok` si el servidor esta vivo e indica en que modo corre cada integracion: "
        "`email` es `resend` o `dev-outbox` (los correos se guardan en `./outbox/`) y `media` "
        "es `cloudinary` o `dev-local` (las imagenes se guardan en `./media/`)."
    ),
)
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
