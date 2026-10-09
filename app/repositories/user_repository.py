"""Data access for User — no query outside this class touches the users
table directly.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, delete, exists, func, update
from sqlmodel import select

from app.models import Order, User
from app.models.enums import UserRole
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_email(self, email: str) -> User | None:
        return self.session.exec(select(User).where(User.email == email)).first()

    # Los tres metodos siguientes tocan los campos de verificacion con un
    # UPDATE atomico (la base hace la aritmetica y la comprobacion), nunca
    # con "leer el objeto, cambiar el atributo, guardar". Con lo segundo,
    # N requests simultaneas leen el mismo valor viejo y se pisan entre si
    # (lost update): 12 codigos incorrectos en paralelo dejaban el contador
    # en 1 y la cuenta nunca se bloqueaba.
    # synchronize_session=False: el objeto User que el servicio ya tenga
    # cargado queda desactualizado a proposito; el servicio hace commit
    # (que expira todo) antes de volver a mirarlo.

    def delete_stale_unverified(self, *, created_before: datetime) -> int:
        """Hard-delete accounts that never verified and never bought anything.
        Returns how many were deleted.

        One DELETE statement, so the checks and the delete are atomic: an
        account that verifies (or places an order) a millisecond earlier
        simply no longer matches. The `NOT EXISTS orders` filter is
        redundant with `orders.user_id ON DELETE RESTRICT` on purpose — the
        database would refuse to delete a buyer anyway; this makes the job
        skip them quietly instead of aborting the whole statement. Dependent
        rows (verification codes, blacklist entries, carts, wishlist,
        reviews) go with the user through their ON DELETE CASCADE.
        """
        # Subconsulta EXISTS: "existe al menos una orden de este usuario".
        # Con el `~` de mas abajo se invierte: solo cuentas SIN ordenes.
        has_orders = exists().where(Order.user_id == User.id)
        result = self.session.execute(
            # DELETE FROM users WHERE <todas las condiciones a la vez>.
            delete(User).where(
                # Solo cuentas que nunca se verificaron...
                User.is_verified.is_(False),
                # ...nunca un admin, aunque por algun motivo estuviera sin verificar...
                User.role == UserRole.USER,
                # ...creadas antes de la fecha limite (ya vencidas)...
                User.created_at < created_before,
                # ...y que no hayan comprado nada.
                ~has_orders,
            ),
            # Un DELETE masivo no carga objetos en la sesion, asi que no hay
            # nada que sincronizar (y se evita trabajo extra).
            execution_options={"synchronize_session": False},
        )
        # rowcount = cuantas filas borro la base de datos.
        return result.rowcount

    def reset_expired_verification_block(self, user_id: int, now: datetime) -> bool:
        """Clear a verification block whose window already elapsed, and
        reset the counter with it. Conditional on the block really being
        over, so a stale caller can never wipe attempts claimed meanwhile.
        True if a block was cleared.
        """
        result = self.session.execute(
            update(User)
            .where(
                User.id == user_id,
                User.verification_blocked_until.is_not(None),
                User.verification_blocked_until <= now,
            )
            .values(verification_attempts=0, verification_blocked_until=None),
            execution_options={"synchronize_session": False},
        )
        return result.rowcount == 1

    def claim_verification_attempt(
        self, user_id: int, *, max_attempts: int, blocked_until: datetime
    ) -> bool:
        """Atomically spend one verification attempt BEFORE the code is
        checked. The WHERE clause is the gate: once the account is blocked
        or the budget is spent, the UPDATE matches no row and the caller is
        refused — so no number of simultaneous requests can ever get more
        than `max_attempts` guesses. The attempt that spends the last one
        also sets `blocked_until` in the same statement.
        True if the attempt was granted.
        """
        result = self.session.execute(
            update(User)
            .where(
                User.id == user_id,
                User.verification_blocked_until.is_(None),
                User.verification_attempts < max_attempts,
            )
            .values(
                verification_attempts=User.verification_attempts + 1,
                # CASE: bloquea solo si este intento agota el cupo.
                verification_blocked_until=case(
                    (User.verification_attempts + 1 >= max_attempts, blocked_until),
                    else_=None,
                ),
            ),
            execution_options={"synchronize_session": False},
        )
        return result.rowcount == 1

    def mark_verified(self, user_id: int) -> None:
        """Flag the account verified and clear every attempt/block trace
        (including the block the last claimed attempt may have just set).
        """
        self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(is_verified=True, verification_attempts=0, verification_blocked_until=None),
            execution_options={"synchronize_session": False},
        )

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
