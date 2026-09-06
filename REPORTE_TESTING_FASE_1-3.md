# Reporte de testing — Fases 1, 2 y 3

**Rama:** `test/verificacion-fases-1-3` (base: `feature/catalogo-publico`)
**Fecha:** 2026-09-03
**Alcance:** Fase 1 (modelo de datos, migraciones, seeder), Fase 2 (identidad
y seguridad), Fase 3 (catálogo público y búsqueda). No cubre Fases 4-8
(no construidas todavía).

**Metodología:** sin dependencias nuevas ni suite automatizada — pase manual
contra la app real: `alembic upgrade head` sobre una BD nueva, el seeder
corrido dos veces, `uvicorn` real golpeado con `curl`, y pruebas de
constraints de FK directamente con `sqlite3` sobre copias descartables de
la base (nunca sobre `gamevault.db` en uso, salvo el flujo de auth de
Fase 2, cuyos usuarios de prueba se limpiaron al terminar). `ruff check` y
`ruff format --check` corridos al final.

---

## Fase 1 — Modelo de datos, migraciones y seeder

| Verificación | Resultado |
|---|---|
| `alembic upgrade head` desde una BD SQLite vacía | ✅ Corre limpio, crea 16 tablas (15 de negocio + `alembic_version`) |
| Seeder corrido dos veces sobre la misma BD | ✅ Idempotente — conteos idénticos en ambas corridas (10 categorías, 20 juegos, 3 ofertas, 5 usuarios, 3 órdenes, 5 order_items, 5 library_items, 5 wishlist_items, 3 reviews, 20 game_images) |
| `ON DELETE RESTRICT` — `orders.user_id` | ✅ Borrar un usuario con órdenes falla con `IntegrityError` (bloqueado correctamente) |
| `ON DELETE RESTRICT` — `library_items.game_id` | ✅ Borrar un juego que está en alguna biblioteca falla — confirmado con `crimson-vanguard` (3 dueños) |
| `ON DELETE SET NULL` — `order_items.game_id` | ✅ Aislado el caso (limpiando primero los `library_items` que lo bloqueaban): el juego se borra, `order_items.game_id` queda `NULL`, `title_snapshot`/`unit_price`/etc. intactos |
| `ON DELETE CASCADE` — `users.id` → `token_blacklist`, `verification_codes`, `wishlist_items` | ✅ Borrar el usuario limpia las tres tablas hijas automáticamente |
| `requirements.txt` vs venv real | ✅ `pip freeze` del venv activo solo difiere en las herramientas ya clasificadas en `requirements-dev.txt` (ruff, pre-commit, virtualenv, etc.) — sin paquetes runtime sueltos sin congelar |

**Hallazgo (no bloqueante, documentado):** `library_items.game_id` es
`RESTRICT` y `order_items.game_id` es `SET NULL` sobre la misma tabla
(`games`). En la práctica, cualquier juego con `order_items` casi siempre
tiene también un `library_item` (el checkout crea ambos atómicamente), y
SQLite evalúa **todas** las FK antes de ejecutar el `DELETE` — así que el
`RESTRICT` de `library_items` bloquea el borrado *antes* de que el
`SET NULL` de `order_items` pueda actuar. El comentario de
`order_item.py` ("si el juego es borrado, el detalle congelado sobrevive")
solo se cumple hoy si el juego nunca entró a ninguna biblioteca — un caso
borde, no el flujo normal de compra. No es un bug: `RESTRICT` ganando es
el resultado más seguro (protege más una biblioteca comprada que un
detalle histórico), y el mecanismo de retiro real de un juego es el soft
delete (`Game.deleted_at`), no el hard delete. Vale la pena que quede
anotado por si en Fase 4/7 se construye alguna herramienta de limpieza que
sí dependa de ese `SET NULL`.

---

## Fase 2 — Identidad y seguridad

| Verificación | Resultado |
|---|---|
| `POST /auth/register` → outbox | ✅ 201, código de 6 dígitos en `outbox/*.html` |
| `POST /auth/login` antes de verificar | ✅ 401 "Debes verificar tu cuenta..." |
| `POST /auth/register` con email duplicado | ✅ 409 |
| `POST /auth/verify` con código incorrecto (x2) | ✅ 401, `verification_attempts` sube a 2 en BD |
| `POST /auth/verify` con código correcto | ✅ 200, `is_verified=1`, `verification_attempts` vuelve a 0 |
| `POST /auth/verify` repetido tras ya verificado | ✅ 200 no-op (mensaje genérico, no revela estado) |
| `POST /auth/login` correcto | ✅ 200 + JWT |
| `GET /auth/me` con token válido | ✅ 200 |
| `POST /auth/logout` | ✅ 200, revoca el `jti` |
| `GET /auth/me` reusando token tras logout | ✅ 401 "La sesión fue cerrada..." |
| Token manipulado / ausente | ✅ 401 en ambos casos |
| Rate limiting `/auth/login` (5/minute) | ✅ Confirmado exactamente: 5 requests permitidas, la 6ª → 429 |
| Bloqueo por intentos máximos (`verification_max_attempts=5`), probado vía `auth_service` directo para no chocar con el rate limiter de `/auth/verify` (misma magnitud, 5/minuto) | ✅ Al 5º intento fallido se fija `verification_blocked_until` (+30 min); el 6º intento devuelve "Demasiados intentos" **sin volver a validar el código** |
| `resend-verification` mientras la cuenta está bloqueada | ✅ 401, mismo mensaje de bloqueo |
| Cooldown de resend (60s) | ✅ Un resend inmediato es rechazado; tras simular que pasó el cooldown, se acepta |
| "Un solo código vigente" | ✅ Al reenviar, el código anterior queda `invalidated_at != NULL`; verificar con el código viejo falla |

**Hallazgo (documentación vs. comportamiento real):** el docstring de
`auth_service.logout()` dice *"logging out twice with the same
(already-revoked) token is a no-op, not an error"*, y el código en efecto
tiene ese chequeo (`if blacklist.is_revoked(jti): return`). Pero en la
práctica, un segundo `POST /auth/logout` con el mismo token da **401**,
no 200 — porque el router exige `CurrentUser` (`get_current_user`) como
dependencia, y esa dependencia ya rechaza cualquier token con `jti` en
blacklist *antes* de que la petición llegue al servicio. El chequeo de
idempotencia en `auth_service.logout()` es código hoy inalcanzable desde
el endpoint HTTP tal como está cableado. Confirmado en vivo: logout →
200, segundo logout con el mismo token → 401 "La sesión fue cerrada...".
No es grave (401 en un token ya revocado es una respuesta razonable), pero
el comentario del código promete algo que el endpoint no cumple — vale la
pena que el equipo decida si ajustar el docstring o el wiring del router
cuando se retome esa área.

---

## Fase 3 — Catálogo público y búsqueda

| Verificación | Resultado |
|---|---|
| `GET /categories` | ✅ 10 categorías, ordenadas por nombre |
| `GET /games` paginación por defecto | ✅ `total=20`, `pages` correcto según `size` |
| Búsqueda `q` (título + descripción, case-insensitive) | ✅ `q=RPG` → 6 resultados vía coincidencia en descripción |
| Filtro `categories` (múltiples, combina con OR) | ✅ `categories=rpg&categories=terror` → 8 juegos (unión correcta) |
| Filtro `platform` (case-insensitive, match exacto) | ✅ `platform=pc` (minúscula) → mismo total que `PC` |
| Filtro `price_min`/`price_max` (sobre precio efectivo) | ✅ Rango 30000-45000 → 8 juegos, todos dentro del rango mostrado |
| Filtro `on_offer=true` | ✅ Solo `crimson-vanguard` (única oferta vigente sembrada) |
| Filtro `min_rating` | ✅ `min_rating=4` → solo los 2 juegos con promedio ≥ 4.0 |
| `sort` — las 8 variantes (`title_*`, `price_*`, `release_date_*`, `popularity_*`) | ✅ `price_desc` y `popularity_desc` verificados explícitamente contra el orden esperado; el resto usa la misma expresión de `ORDER BY`, sin lógica condicional adicional por variante |
| `GET /games/{slug}` detalle | ✅ Precio efectivo, imágenes, categorías, `rating_average`/`rating_count` correctos (`crimson-vanguard`: 4.0 sobre 2 reseñas) |
| `GET /games/{slug}` inexistente | ✅ 404 con el envelope de error estándar |
| Soft-delete / `is_active` | ✅ Juego marcado `is_active=0`: desaparece del listado y de la búsqueda por texto, y el detalle da 404 — revertido después de la prueba |
| Validación de query params | ✅ `page=0` → 422, `size=500` → 422, `sort` inválido → 422 (detalle claro del campo), `min_rating=0` → 422 |
| Página más allá del total | ✅ 200, `items=[]`, `total`/`pages` correctos (no 404 ni error) |
| Categoría / búsqueda sin coincidencias | ✅ 200, `total=0`, `pages=0` |
| Precio efectivo = `active_offer_clause` + `compute_effective_price` | ✅ `crimson-vanguard` con 20% off: `29990.00 → 23992.00`, coincide exacto con el cálculo canónico de `offer_repository.py` |

**Sin hallazgos.** Todo el comportamiento coincide con lo especificado en
el plan (paginación, filtros combinables, precio efectivo vía la fuente
única de verdad, soft delete respetado, errores de validación claros).

---

## Regresión general

- `GET /health` sigue reportando `email: dev-outbox`, `media: dev-local`
  sin cambios.
- `ruff check .` y `ruff format --check .`: sin hallazgos, 56 archivos.
- BD de desarrollo (`gamevault.db`) devuelta a su estado sembrado original
  al terminar (20 juegos, 5 usuarios) — los usuarios de prueba creados
  durante el pase (`test.qa@`, `qa.blocklock@`, `qa.invalidate@...`) se
  eliminaron manualmente al cierre.

## Resumen

Fases 1, 2 y 3 pasan la verificación completa. Dos hallazgos menores
documentados arriba (interacción `RESTRICT`/`SET NULL` en el hard-delete
de un juego, e idempotencia de `logout()` inalcanzable vía HTTP) — ninguno
bloquea avanzar a la Fase 4; quedan para que el equipo decida si ajustar
comentarios/código cuando se retome esa área.
