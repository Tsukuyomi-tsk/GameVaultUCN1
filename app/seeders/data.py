"""Static seed data — declarative, no DB or business logic here.

Kept separate from run.py so the actual seeding orchestration (and its
idempotency checks) stays readable. Offer windows are expressed as day
offsets from "now" (resolved by run.py at seed time), not fixed dates, so
"vigente / expirada / futura" stays true no matter when the seeder runs.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

# Shared password for every seeded test account (not the admin — see
# ADMIN_PASSWORD in .env). Documented in the README for manual testing.
SEED_USER_PASSWORD = "Password123!"

CATEGORIES: list[dict] = [
    {"name": "Accion", "slug": "accion", "description": "Combate, reflejos y adrenalina."},
    {"name": "Aventura", "slug": "aventura", "description": "Exploracion y narrativa."},
    {"name": "RPG", "slug": "rpg", "description": "Progresion de personaje y decisiones."},
    {
        "name": "Estrategia",
        "slug": "estrategia",
        "description": "Planificacion y gestion de recursos.",
    },
    {"name": "Deportes", "slug": "deportes", "description": "Simuladores deportivos."},
    {"name": "Carreras", "slug": "carreras", "description": "Velocidad y competicion."},
    {
        "name": "Simulacion",
        "slug": "simulacion",
        "description": "Sistemas realistas de gestion.",
    },
    {"name": "Terror", "slug": "terror", "description": "Suspenso y sobrevivencia."},
    {"name": "Plataformas", "slug": "plataformas", "description": "Saltos y precision."},
    {
        "name": "Mundo Abierto",
        "slug": "mundo-abierto",
        "description": "Exploracion libre a gran escala.",
    },
]

GAMES: list[dict] = [
    {
        "title": "Crimson Vanguard",
        "slug": "crimson-vanguard",
        "description": "Shooter tactico cooperativo ambientado en una guerra futurista.",
        "developer": "Nightshade Studios",
        "publisher": "Vanguard Interactive",
        "platform": "PC",
        "release_date": date(2023, 6, 14),
        "base_price": Decimal("29990"),
        "categories": ["accion", "estrategia"],
    },
    {
        "title": "Silver Horizon",
        "slug": "silver-horizon",
        "description": "Aventura de exploracion en un archipielago a la deriva.",
        "developer": "Driftwood Games",
        "publisher": "Horizon Media",
        "platform": "PlayStation 5",
        "release_date": date(2022, 11, 3),
        "base_price": Decimal("39990"),
        "categories": ["aventura", "mundo-abierto"],
    },
    {
        "title": "Glass Kingdom",
        "slug": "glass-kingdom",
        "description": "RPG por turnos en un reino fracturado de cristal.",
        "developer": "Prism Forge",
        "publisher": "Prism Forge",
        "platform": "Nintendo Switch",
        "release_date": date(2024, 2, 20),
        "base_price": Decimal("34990"),
        "categories": ["rpg", "aventura"],
    },
    {
        "title": "Frostwood Tales",
        "slug": "frostwood-tales",
        "description": "RPG de supervivencia en un bosque eternamente nevado.",
        "developer": "Pale Lantern",
        "publisher": "Pale Lantern",
        "platform": "PC",
        "release_date": date(2021, 10, 12),
        "base_price": Decimal("24990"),
        "categories": ["rpg", "terror"],
    },
    {
        "title": "Iron Circuit",
        "slug": "iron-circuit",
        "description": "Carreras arcade con vehiculos modificables.",
        "developer": "Redline Works",
        "publisher": "Vanguard Interactive",
        "platform": "Xbox Series X",
        "release_date": date(2023, 8, 1),
        "base_price": Decimal("27990"),
        "categories": ["carreras"],
    },
    {
        "title": "Nightfall Drift",
        "slug": "nightfall-drift",
        "description": "Terror episodico en un pueblo costero abandonado.",
        "developer": "Pale Lantern",
        "publisher": "Horizon Media",
        "platform": "PC",
        "release_date": date(2022, 9, 30),
        "base_price": Decimal("19990"),
        "categories": ["terror", "aventura"],
    },
    {
        "title": "Solar Reign",
        "slug": "solar-reign",
        "description": "Estrategia por turnos de conquista interplanetaria.",
        "developer": "Ecliptic Studio",
        "publisher": "Ecliptic Studio",
        "platform": "PlayStation 5",
        "release_date": date(2023, 3, 17),
        "base_price": Decimal("44990"),
        "categories": ["estrategia"],
    },
    {
        "title": "Emberlight Saga",
        "slug": "emberlight-saga",
        "description": "RPG tactico con un elenco de heroes elementales.",
        "developer": "Prism Forge",
        "publisher": "Prism Forge",
        "platform": "Nintendo Switch",
        "release_date": date(2021, 5, 6),
        "base_price": Decimal("32990"),
        "categories": ["rpg"],
    },
    {
        "title": "Velocity Nexus",
        "slug": "velocity-nexus",
        "description": "Carreras futuristas de gran velocidad con combate.",
        "developer": "Redline Works",
        "publisher": "Redline Works",
        "platform": "PC",
        "release_date": date(2024, 1, 9),
        "base_price": Decimal("29990"),
        "categories": ["carreras", "accion"],
    },
    {
        "title": "Shattered Aegis",
        "slug": "shattered-aegis",
        "description": "Accion RPG de mazmorras generadas proceduralmente.",
        "developer": "Nightshade Studios",
        "publisher": "Vanguard Interactive",
        "platform": "Xbox Series X",
        "release_date": date(2022, 7, 22),
        "base_price": Decimal("37990"),
        "categories": ["accion", "rpg"],
    },
    {
        "title": "Moonlit Harbor",
        "slug": "moonlit-harbor",
        "description": "Simulador de vida en un pueblo pesquero costero.",
        "developer": "Driftwood Games",
        "publisher": "Horizon Media",
        "platform": "PC",
        "release_date": date(2023, 12, 5),
        "base_price": Decimal("22990"),
        "categories": ["aventura", "simulacion"],
    },
    {
        "title": "Copper Skies",
        "slug": "copper-skies",
        "description": "Plataformas de precision con mecanicas de vuelo.",
        "developer": "Featherline",
        "publisher": "Featherline",
        "platform": "PlayStation 5",
        "release_date": date(2022, 4, 14),
        "base_price": Decimal("17990"),
        "categories": ["plataformas"],
    },
    {
        "title": "Wraithbound",
        "slug": "wraithbound",
        "description": "Terror psicologico en primera persona.",
        "developer": "Pale Lantern",
        "publisher": "Pale Lantern",
        "platform": "PC",
        "release_date": date(2021, 10, 29),
        "base_price": Decimal("21990"),
        "categories": ["terror"],
    },
    {
        "title": "Sundial Chronicles",
        "slug": "sundial-chronicles",
        "description": "RPG de mundo abierto ambientado en un imperio desertico.",
        "developer": "Ecliptic Studio",
        "publisher": "Ecliptic Studio",
        "platform": "Nintendo Switch",
        "release_date": date(2024, 5, 3),
        "base_price": Decimal("42990"),
        "categories": ["rpg", "mundo-abierto"],
    },
    {
        "title": "Granite Frontier",
        "slug": "granite-frontier",
        "description": "Gestion de colonias en un planeta hostil.",
        "developer": "Ecliptic Studio",
        "publisher": "Horizon Media",
        "platform": "PC",
        "release_date": date(2022, 2, 11),
        "base_price": Decimal("31990"),
        "categories": ["estrategia", "simulacion"],
    },
    {
        "title": "Echo Valley",
        "slug": "echo-valley",
        "description": "Aventura narrativa sobre una expedicion de rescate.",
        "developer": "Driftwood Games",
        "publisher": "Driftwood Games",
        "platform": "Xbox Series X",
        "release_date": date(2023, 9, 19),
        "base_price": Decimal("26990"),
        "categories": ["aventura"],
    },
    {
        "title": "Neon Vertex",
        "slug": "neon-vertex",
        "description": "Accion frenetica en una ciudad ciberpunk vertical.",
        "developer": "Nightshade Studios",
        "publisher": "Nightshade Studios",
        "platform": "PC",
        "release_date": date(2023, 11, 28),
        "base_price": Decimal("28990"),
        "categories": ["accion"],
    },
    {
        "title": "Timberland Rally",
        "slug": "timberland-rally",
        "description": "Rally todoterreno con circuitos dinamicos por clima.",
        "developer": "Redline Works",
        "publisher": "Redline Works",
        "platform": "PlayStation 5",
        "release_date": date(2022, 6, 8),
        "base_price": Decimal("25990"),
        "categories": ["deportes", "carreras"],
    },
    {
        "title": "Obsidian Court",
        "slug": "obsidian-court",
        "description": "RPG de intriga politica en una corte de sombras.",
        "developer": "Prism Forge",
        "publisher": "Vanguard Interactive",
        "platform": "PC",
        "release_date": date(2021, 3, 2),
        "base_price": Decimal("33990"),
        "categories": ["rpg"],
    },
    {
        "title": "Pixel Meadow",
        "slug": "pixel-meadow",
        "description": "Plataformas cooperativo en un valle de pixel art.",
        "developer": "Featherline",
        "publisher": "Featherline",
        "platform": "Nintendo Switch",
        "release_date": date(2024, 4, 16),
        "base_price": Decimal("14990"),
        "categories": ["plataformas", "aventura"],
    },
]

# Offer windows as (game_slug, discount_percent, starts_offset_days, ends_offset_days),
# resolved against "now" at seed time so the three states below are always true
# regardless of when the seeder runs — used directly in the demo/defense.
OFFERS: list[dict] = [
    {
        "game_slug": "crimson-vanguard",
        "discount_percent": 20,
        "starts_offset_days": -1,
        "ends_offset_days": 7,
    },  # vigente
    {
        "game_slug": "silver-horizon",
        "discount_percent": 15,
        "starts_offset_days": -30,
        "ends_offset_days": -15,
    },  # expirada
    {
        "game_slug": "glass-kingdom",
        "discount_percent": 30,
        "starts_offset_days": 10,
        "ends_offset_days": 20,
    },  # futura
]

TEST_USERS: list[dict] = [
    {"email": "maria.torres@example.com", "full_name": "Maria Torres"},
    {"email": "juan.perez@example.com", "full_name": "Juan Perez"},
    {"email": "camila.rojas@example.com", "full_name": "Camila Rojas"},
    {"email": "diego.soto@example.com", "full_name": "Diego Soto"},
]

# Each entry becomes one simulated historical checkout (Order + OrderItem +
# LibraryItem), priced at the game's current base_price with no discount —
# purchase history is frozen at the price paid, so it's intentionally not
# tied to whatever offer happens to be active today.
SEED_ORDERS: list[dict] = [
    {
        "user_email": "maria.torres@example.com",
        "game_slugs": ["crimson-vanguard", "glass-kingdom"],
    },
    {
        "user_email": "juan.perez@example.com",
        "game_slugs": ["crimson-vanguard", "frostwood-tales"],
    },
    {"user_email": "camila.rojas@example.com", "game_slugs": ["crimson-vanguard"]},
]

SEED_WISHLISTS: list[dict] = [
    {
        "user_email": "diego.soto@example.com",
        "game_slugs": ["silver-horizon", "iron-circuit", "nightfall-drift"],
    },
    {
        "user_email": "camila.rojas@example.com",
        "game_slugs": ["crimson-vanguard", "silver-horizon"],
    },
]

# Every (user_email, game_slug) pair here must also appear in that user's
# SEED_ORDERS game_slugs — reviews require ownership even in seed data.
SEED_REVIEWS: list[dict] = [
    {
        "user_email": "maria.torres@example.com",
        "game_slug": "crimson-vanguard",
        "rating": 5,
        "comment": "Excelente cooperativo, muy recomendado.",
    },
    {
        "user_email": "maria.torres@example.com",
        "game_slug": "glass-kingdom",
        "rating": 4,
        "comment": "Buena historia, algo corto.",
    },
    {
        "user_email": "juan.perez@example.com",
        "game_slug": "crimson-vanguard",
        "rating": 3,
        "comment": "Divertido pero con problemas de conexion.",
    },
]
