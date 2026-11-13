# GameVault UCN

Backend REST de **GameVault UCN**, una plataforma de distribución digital de videojuegos.
Es la **API REST** del curso *Introducción al Desarrollo Web y Móvil* (UCN).

> **Es un proyecto académico, pensado para aprender y probar en local.** No está endurecido para
> producción (ver [Límites conocidos](#límites-conocidos)).

La API se prueba completa desde **Swagger UI** (`http://localhost:8000/docs`): no hace falta Postman
ni ninguna otra herramienta.

## Qué incluye

- **Identidad y seguridad:** registro con verificación por correo, login con JWT, cierre de sesión con
  lista negra de tokens, límite de intentos y límite de tasa en `/auth/*`.
- **Catálogo público:** búsqueda, filtros, orden y paginación; detalle con oferta vigente y reseñas.
- **Backoffice (solo admin):** CRUD de juegos, categorías y ofertas con borrado lógico, subida de
  imágenes, gestión de usuarios (suspender/reactivar) y estadísticas de popularidad.
- **Carrito y pedidos:** carrito de invitado o con sesión, checkout **idempotente**, historial, boleta en
  PDF y biblioteca de juegos comprados.
- **Comunidad:** reseñas (solo de juegos que posees) y lista de deseados.
- **Calidad:** logging JSON con `request_id`, errores con un formato único y jobs programados de limpieza.

## Stack

| Pieza | Tecnología |
|---|---|
| Lenguaje | Python 3.12+ |
| Framework | FastAPI |
| Base de datos y ORM | SQLite + SQLModel (migraciones con Alembic) |
| Autenticación | JWT (PyJWT) con lista negra de tokens; contraseñas con bcrypt |
| Correos | Resend (con modo desarrollo sin cuenta) |
| Imágenes | Cloudinary (con modo desarrollo sin cuenta) |
| Jobs | APScheduler |
| PDF | fpdf2 |
| Calidad | Ruff, pre-commit |

Arquitectura por capas: **routers → servicios → repositorios → modelos**. Un router nunca toca la base
de datos, un servicio nunca escribe una consulta, y solo los repositorios usan `select()`.

## Instalación paso a paso

Necesitas **Python 3.12 o superior** y Git.

```bash
# 1. Clonar y entrar a la carpeta
git clone <url-del-repositorio>
cd GameVaultUCN

# 2. Crear y activar un entorno virtual
python -m venv .venv
.venv\Scripts\activate          # Windows (PowerShell / cmd)
# source .venv/bin/activate     # macOS / Linux

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Crear tu archivo de configuración (sin claves reales: corre en modo desarrollo)
copy .env.example .env          # Windows
# cp .env.example .env          # macOS / Linux

# 5. Crear las tablas de la base de datos
alembic upgrade head

# 6. Levantar el servidor
uvicorn app.main:app --reload
```

Con `SEED_ON_STARTUP=true` (el valor por defecto) el servidor siembra datos de demostración al
arrancar. Cuando veas el servidor corriendo abre:

- **Swagger UI:** <http://localhost:8000/docs>
- **Estado del servidor:** <http://localhost:8000/health>

Para contribuir (formato y commits) instala además las herramientas de desarrollo:

```bash
pip install -r requirements-dev.txt
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

## Variables de entorno (`.env`)

Todas tienen un valor por defecto para desarrollo; `.env.example` las lista con comentarios.

| Variable | Por defecto | Para qué sirve |
|---|---|---|
| `APP_NAME` | `GameVault UCN` | Nombre que muestra Swagger UI. |
| `ENVIRONMENT` | `development` | `development` o `production`. En `production` la app **no arranca** si faltan las credenciales reales de Resend, Cloudinary o `SECRET_KEY`. |
| `DEBUG` | `true` | Bandera de depuración. |
| `CORS_ORIGINS` | `*` | Orígenes permitidos para el front, separados por coma. |
| `LOG_LEVEL` | `INFO` | Nivel de los logs JSON (`DEBUG`, `INFO`, `WARNING`, `ERROR`). Con `DEBUG` también se imprime el SQL. |
| `DATABASE_URL` | `sqlite:///./gamevault.db` | Ubicación de la base de datos. |
| `SECRET_KEY` | valor de ejemplo | Clave con la que se firman los JWT. |
| `JWT_ALGORITHM` | `HS256` | Algoritmo de firma. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Duración del token de acceso. |
| `RATE_LIMIT_AUTH` | `5/minute` | Límite por IP y por endpoint en `/auth/*`. |
| `VERIFICATION_CODE_LENGTH` | `6` | Largo del código de verificación. |
| `VERIFICATION_CODE_TTL_MINUTES` | `15` | Vigencia del código. |
| `VERIFICATION_MAX_ATTEMPTS` | `5` | Intentos fallidos antes de bloquear la cuenta. |
| `VERIFICATION_BLOCK_MINUTES` | `30` | Duración del bloqueo de cuenta. |
| `VERIFICATION_RESEND_COOLDOWN_SECONDS` | `60` | Espera mínima entre dos reenvíos del código. |
| `SCHEDULER_ENABLED` | `true` | Enciende o apaga los jobs programados. |
| `UNVERIFIED_ACCOUNT_TTL_HOURS` | `48` | Horas antes de borrar una cuenta sin verificar. |
| `BLACKLIST_PURGE_INTERVAL_HOURS` | `6` | Cada cuánto se purgan los tokens revocados vencidos. |
| `GUEST_CART_TTL_DAYS` | `30` | Días sin actividad antes de borrar un carrito de invitado. |
| `SEED_ON_STARTUP` | `true` | Siembra la demo al arrancar. |
| `ADMIN_EMAIL` | `admin@gamevault.ucn.cl` | Correo del administrador sembrado. |
| `ADMIN_PASSWORD` | `ChangeMe123!` | Contraseña del administrador sembrado. |
| `ADMIN_FULL_NAME` | `Administrador GameVault` | Nombre del administrador. |
| `RESEND_API_KEY` | vacío | Vacío = modo desarrollo de correos. |
| `RESEND_FROM_EMAIL` | `GameVault UCN <no-reply@gamevault.ucn.cl>` | Remitente de los correos. |
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | vacío | Si falta cualquiera, modo desarrollo de imágenes. |

## Migraciones

Las tablas se crean con Alembic. Los comandos que vas a usar:

```bash
alembic upgrade head                              # aplicar todas las migraciones
alembic current                                   # ver en qué versión está tu base
alembic revision --autogenerate -m "descripcion"  # generar una migración tras cambiar un modelo
alembic check                                     # verificar que los modelos y las migraciones coinciden
```

> Si actualizas el repositorio y aparecen migraciones nuevas, vuelve a correr `alembic upgrade head`.
> Para empezar de cero, borra `gamevault.db` y repite los pasos 5 y 6.

## Datos y credenciales del seeder

El seeder es idempotente (puedes correrlo varias veces). También se puede ejecutar a mano:

```bash
python -m app.seeders.run
```

Crea 10 categorías, 20 juegos, ofertas, pedidos históricos, reseñas y estas cuentas:

| Cuenta | Correo | Contraseña | Qué tiene |
|---|---|---|---|
| Administrador | `admin@gamevault.ucn.cl` | `ChangeMe123!` (o tu `ADMIN_PASSWORD`) | Acceso a `/admin/*`. |
| María Torres | `maria.torres@example.com` | `Password123!` | Posee `crimson-vanguard` y `glass-kingdom`; tiene reseñas. |
| Juan Pérez | `juan.perez@example.com` | `Password123!` | Posee `crimson-vanguard` y `frostwood-tales`. |
| Camila Rojas | `camila.rojas@example.com` | `Password123!` | Posee `crimson-vanguard`. |
| Diego Soto | `diego.soto@example.com` | `Password123!` | **No posee ningún juego** (útil para probar errores). |

> Estas credenciales son **públicas a propósito** (están en el repositorio) para que cualquiera pueda
> probar la API sin preparar nada.

## Modo desarrollo: correos e imágenes sin cuentas externas

Resend y Cloudinary son servicios de terceros. Para no exigir cuentas, la app **cae sola a un modo
desarrollo** cuando faltan sus credenciales (nunca por una bandera, y nunca esconde un fallo real):

| Integración | Sin credenciales | Dónde mirar |
|---|---|---|
| **Correos (Resend)** | El correo **no se envía**: se guarda como `.html` en `./outbox/`. | Abre el archivo más reciente: ahí está el **código de verificación**. |
| **Imágenes (Cloudinary)** | La imagen **no se sube**: se guarda en `./media/` y se sirve en `/media/<archivo>`. | La carpeta `./media/`. |

Para saber en qué modo está corriendo cada integración, mira `GET /health`
(`email: dev-outbox | resend`, `media: dev-local | cloudinary`). Al arrancar y en cada envío simulado
la app escribe un aviso `[MODO DEV]` en el log. Con credenciales reales de Resend/Cloudinary en el
`.env`, todo funciona de verdad sin cambiar nada más.

Los archivos de `./outbox/` se llaman `<fecha>_<correo>.html`; el del registro contiene una línea con el
código de 6 dígitos.

## Cómo probar la API desde `/docs`

Swagger UI agrupa los endpoints por tema. En cada uno: **Try it out → Execute**. El cuerpo de ejemplo
ya viene precargado y funciona tal cual.

**Autenticarte:** haz `POST /auth/login`, copia el `access_token`, pulsa **Authorize** (arriba a la
derecha) y pégalo (sin escribir `Bearer`). Para volver a probar **como invitado**, pulsa Authorize y luego
**Logout** dentro del diálogo.

> **Ojo con el límite de tasa:** `/auth/*` acepta **5 peticiones por minuto por IP en cada endpoint**.
> Si pruebas muy rápido recibirás `429` con `Retry-After`; espera un minuto y sigue.

### Flujo 1 — Registro y primer login

1. `POST /auth/register` con el ejemplo (cambia el correo si quieres). Responde `201` siempre lo mismo.
2. Abre el archivo más reciente de `./outbox/` y copia el código de 6 dígitos.
3. `POST /auth/verify` con tu correo y ese código → `200`.
4. `POST /auth/login` → copia el `access_token` y pulsa **Authorize**.
5. `GET /auth/me` → ves tu perfil.

### Flujo 2 — Compra completa

1. Sin sesión (invitado): `GET /games` y elige un juego. `POST /cart/items` con `{"game_id": N}`: la
   respuesta trae un `cart_token`; **guárdalo**.
2. Con el token en `X-Cart-Token`, `GET /cart` muestra el carrito con precios y ofertas.
3. Haz login (Flujo 1) y pulsa Authorize. `POST /cart/merge` con el mismo `X-Cart-Token` pasa el carrito
   a tu cuenta.
4. `POST /orders/checkout` con una `Idempotency-Key` inventada (por ejemplo `compra-001`) → `201` con la
   orden.
5. **Repite el mismo checkout con la misma clave** → devuelve **la misma orden**, sin cobrar dos veces.
6. `GET /orders/{order_code}/receipt` descarga la boleta PDF. Se genera en segundo plano: si da `404`,
   espera unos segundos y reintenta. También llega un correo de confirmación a `./outbox/`.
7. `GET /me/library` muestra el juego comprado y `POST /games/{game_id}/reviews` te deja reseñarlo.

### Flujo 3 — Backoffice (admin)

1. Login con `admin@gamevault.ucn.cl` y pulsa Authorize con ese token.
2. `POST /admin/categories` y `POST /admin/games` con los ejemplos precargados.
3. `POST /admin/games/{id}/images` sube una imagen (se guarda en `./media/` en modo desarrollo).
4. `POST /admin/offers` crea una oferta; `GET /games` muestra el juego con su precio rebajado.
5. `DELETE /admin/games/{id}` lo oculta del catálogo (borrado lógico); `POST /admin/games/{id}/restore` lo
   devuelve.
6. `GET /admin/stats/popularity` muestra los juegos más deseados y más comprados.

### Flujos de error (¡pruébalos!)

| Qué probar | Cómo | Resultado esperado |
|---|---|---|
| **Reseñar sin poseer el juego** | Login como `diego.soto@example.com` y `POST /games/1/reviews`. | `403` |
| **Usar un endpoint admin como cliente** | Con el token de María, `GET /admin/games`. | `403` |
| **Usar un token ya cerrado** | `POST /auth/logout` y luego `GET /auth/me` con el mismo token. | `401` |
| **Exceder los intentos de verificación** | Registra una cuenta y manda `POST /auth/verify` con códigos incorrectos 5 veces. Espera un minuto (para no chocar con el límite por IP) y repite. | `401` las 5 primeras; después `429` con `Retry-After` de unos 30 minutos (bloqueo de la **cuenta**) |
| **Límite por IP** | Más de 5 `POST /auth/login` en un minuto. | `429` con `Retry-After: 60` |
| **Reenviar la confirmación de una cuenta ya verificada** | Verifica una cuenta y luego `POST /auth/resend-verification` con su correo. | `200` genérico y **no** aparece un archivo nuevo en `./outbox/` |
| **Ver el pedido o la boleta de otro usuario** | Con el token de María, `GET /orders` y copia un `order_code`. Haz login como Juan y pídelo con `GET /orders/{order_code}`. | `404` (no `403`: un `403` confirmaría que existe) |
| **Editar la reseña de otro usuario** | Con el token de otro usuario, `PATCH /reviews/{id}` sobre la reseña de María. | `404` |
| **Token de un usuario suspendido** | Como admin, `PATCH /admin/users/{id}/suspend`; luego usa el token de ese usuario en `GET /auth/me`. | `403` |
| **Comprar un juego que ya tienes** | Como María, agrega `crimson-vanguard` al carrito y haz checkout. | `409` |
| **Checkout sin `Idempotency-Key`** | `POST /orders/checkout` sin esa cabecera. | `422` |
| **Oferta solapada** | Crea dos ofertas con fechas que se cruzan para el mismo juego. | `409` |

### Cómo son los errores

Todos los errores de la API tienen la misma forma, para que el front los trate igual:

```json
{
  "error": {
    "code": "not_found",
    "message": "Juego no encontrado.",
    "details": null
  },
  "request_id": "3f9c1d27b45a4e6f"
}
```

`code` es estable (úsalo en el front); `message` es el texto en español; `details` trae la lista de
campos inválidos en un `422`. El `request_id` también viaja en la cabecera `X-Request-ID` y aparece en los
logs del servidor, para encontrar exactamente esa petición.

### Fechas

Todas las fechas se devuelven en **UTC, sin sufijo `Z`** (por ejemplo `2030-01-01T00:00:00`). Si envías una
fecha con zona (`Z` o `-03:00`) se convierte a UTC antes de guardarse. Si tu front muestra la hora
local, interpreta estos valores como UTC.

## Estructura del proyecto

```text
app/
├── main.py            # app FastAPI, middlewares, handlers y routers
├── core/              # configuración, base de datos, seguridad (JWT), logging, errores
├── models/            # tablas (SQLModel)
├── schemas/           # contratos de entrada/salida (Pydantic)
├── routers/           # endpoints: solo traducen HTTP a llamadas a servicios
├── services/          # reglas de negocio y transacciones
├── repositories/      # único lugar con consultas a la base de datos
├── integrations/      # Resend, Cloudinary y PDF
├── jobs/              # tareas programadas (APScheduler)
└── seeders/           # datos de demostración
migrations/            # migraciones de Alembic
```

## Calidad del código

```bash
ruff check app migrations
ruff format --check app migrations
alembic check
```

Los commits siguen [Conventional Commits](https://www.conventionalcommits.org/es/) y el flujo de ramas
es GitFlow (`main` → solo entregable, `develop` → integración, `feature/*` y `fix/*` → una por tarea).

## Límites conocidos

Decisiones tomadas a propósito porque este proyecto es un taller, no un servicio en producción:

- **Credenciales públicas del seeder.** El admin (`ChangeMe123!`) y los usuarios de prueba
  (`Password123!`) están en el repositorio, y `CORS_ORIGINS=*`, `DEBUG=true` y `SEED_ON_STARTUP=true` son
  los valores por defecto. `ENVIRONMENT=production` solo exige credenciales reales de Resend, Cloudinary y
  una `SECRET_KEY` propia: **no** comprueba la contraseña del admin ni el resto. Si alguna vez despliegas
  esto de verdad, cambia `ADMIN_PASSWORD`, define `SEED_ON_STARTUP=false` y no siembres la demo.
- **Límite de tasa en memoria y por IP.** Funciona solo con **un proceso** (un worker de uvicorn): con
  varios, cada uno llevaría su propia cuenta. Detrás de un proxy la IP que ve la app sería la del
  proxy. Los jobs programados tampoco soportan varios workers (correrían duplicados).
- **Correo de "mejor esfuerzo".** Los correos (verificación y boleta) salen **en segundo plano**, después
  de responder. Si el proveedor falla, la cuenta o la orden ya quedaron creadas y el error solo queda en los
  logs (`email_failed`); tampoco hay cola ni reintentos, así que un correo puede perderse o llegar
  desordenado respecto a otro.
- **Correos con caracteres Unicode.** Los correos se guardan en minúsculas, pero no se normalizan
  formas Unicode equivalentes ni dominios internacionalizados (IDNA): dos escrituras distintas del mismo
  correo podrían tratarse como cuentas diferentes.
- **Boleta duplicada en checkouts simultáneos.** Si el mismo checkout se envía muchas veces **a la vez**
  con la misma `Idempotency-Key`, la orden es única, pero el correo de la boleta puede enviarse más de una
  vez.
- **SQLite.** Una sola base de datos en un archivo, sin réplicas; suficiente para el taller.
- **Sin refresh token.** El token de acceso dura 60 minutos; al vencer hay que volver a iniciar sesión.
