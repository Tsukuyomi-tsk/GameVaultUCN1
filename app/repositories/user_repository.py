"""Data access for User — no query outside this class touches the users
table directly.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlmodel import select

from app.models import User
from app.models.enums import UserRole
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_email(self, email: str) -> User | None:
        return self.session.exec(select(User).where(User.email == email)).first()

    def list_admin(
        self,
        *,
        role: UserRole | None,
        is_suspended: bool | None,
        offset: int,
        limit: int,
    ) -> tuple[list[User], int]:
        """Paginated account listing for the admin backoffice — `User` has
        no `deleted_at`, so this always sees every account.
        """
        # Punto de partida: "todos los usuarios", sin ningun filtro todavia.
        statement = select(User)
        # Cada filtro es OPCIONAL — si el parametro llego como None, no se
        # agrega ninguna condicion WHERE para el (se listan todos los roles
        # o todos los estados de suspension, segun corresponda).
        if role is not None:
            statement = statement.where(User.role == role)
        if is_suspended is not None:
            statement = statement.where(User.is_suspended == is_suspended)

        # Antes de paginar, se calcula cuantos usuarios en TOTAL cumplen
        # estos mismos filtros (sin el offset/limit) — es lo que el
        # endpoint necesita para armar el campo "total" de la respuesta
        # paginada. with_only_columns cambia el SELECT de "traer usuarios
        # completos" a "traer solo un COUNT(id)", reutilizando el mismo
        # WHERE que ya se armo arriba.
        total = self.session.execute(statement.with_only_columns(func.count(User.id))).scalar_one()

        # Ahora si se trae la pagina real de resultados: se ordena del mas
        # nuevo al mas viejo, se salta `offset` filas (las paginas
        # anteriores) y se limita a `limit` filas (el tamaño de pagina).
        rows = self.session.exec(
            statement.order_by(User.created_at.desc()).offset(offset).limit(limit)
        ).all()
        # Devuelve tanto la pagina de usuarios como el total global, para
        # que el servicio pueda calcular cuantas paginas hay en total.
        return list(rows), int(total)
