"""correos en minusculas

Revision ID: a3f9c1d27b45
Revises: e1996fd4aa7c
Create Date: 2026-10-12 12:00:00.000000

Migracion de DATOS (no cambia el esquema): lleva users.email a la forma
canonica que usan ahora los schemas, el seeder y UserRepository.get_by_email
(`str.lower()` de Python). Antes "Ana@x.com" y "ana@x.com" podian ser dos
cuentas distintas; desde ahora son la misma identidad.

Si dos cuentas coinciden al pasar a minusculas, la migracion ABORTA sin
tocar nada y lista los ids: decidir cual conservar implica mover pedidos,
biblioteca y resenas, y eso no se hace automaticamente.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f9c1d27b45"
down_revision: str | Sequence[str] | None = "e1996fd4aa7c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Lowercase every stored email, refusing to run if that would merge accounts."""
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, email FROM users")).all()

    # Se agrupa con str.lower() de Python (no con lower() de SQLite, que solo
    # convierte ASCII): es la misma regla que aplicara la aplicacion.
    groups: dict[str, list[tuple[int, str]]] = {}
    for user_id, email in rows:
        groups.setdefault(email.lower(), []).append((user_id, email))

    collisions = {key: members for key, members in groups.items() if len(members) > 1}
    if collisions:
        detail = "; ".join(
            f"{key}: " + ", ".join(f"id={uid} ({email})" for uid, email in members)
            for key, members in collisions.items()
        )
        raise RuntimeError(
            "No se puede normalizar users.email: hay cuentas que difieren solo en "
            "mayusculas y quedarian duplicadas. Resuelvelas a mano (conservar una y "
            f"mover sus pedidos/biblioteca/resenas) y vuelve a migrar. Colisiones: {detail}"
        )

    for user_id, email in rows:
        if email != email.lower():
            connection.execute(
                sa.text("UPDATE users SET email = :email WHERE id = :id"),
                {"email": email.lower(), "id": user_id},
            )


def downgrade() -> None:
    """No-op: the original capitalization can't be recovered (and was never meaningful)."""
