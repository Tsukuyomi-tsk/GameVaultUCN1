"""Data access for Review (Fase 6) — the one place that queries the
`reviews` table.

Review is soft-deleted (`deleted_at`), but its UniqueConstraint on
(user_id, game_id) still counts soft-deleted rows. `get_by_user_and_game`
therefore deliberately does NOT hide them: the service needs to see a
soft-deleted row to revive it, since inserting a second row for the same
(user, game) pair would violate the constraint.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, update
from sqlmodel import select

from app.models import Review, User
from app.repositories.base import BaseRepository


class ReviewRepository(BaseRepository[Review]):
    # Le indica a BaseRepository sobre que tabla trabajan get()/add()/
    # delete() heredados: "reviews". Como Review tiene la columna
    # deleted_at, get() heredado ya oculta por defecto las resenas borradas.
    model = Review

    def get_by_user_and_game(self, *, user_id: int, game_id: int) -> Review | None:
        # Busca por la MISMA combinacion que protege el UniqueConstraint del
        # modelo (user_id + game_id). A proposito NO filtra deleted_at: una
        # resena borrada sigue "ocupando" ese par en la base de datos.
        statement = select(Review).where(Review.user_id == user_id, Review.game_id == game_id)
        return self.session.exec(statement).first()

    def revive(self, review_id: int, *, rating: int, comment: str | None, now: datetime) -> bool:
        """Atomically bring a soft-deleted review back to life with new content.

        A single conditional UPDATE (`WHERE deleted_at IS NOT NULL`) instead
        of "read it, check it, write it": reviving inserts no row, so the
        UniqueConstraint cannot arbitrate two concurrent attempts the way it
        does for a fresh INSERT. Here the database itself does — only the
        first UPDATE still finds the row deleted; every later one matches
        zero rows and returns False.
        """
        # El WHERE incluye deleted_at IS NOT NULL: solo "gana" quien
        # encuentre la resena todavia borrada.
        statement = (
            update(Review)
            .where(Review.id == review_id, Review.deleted_at.is_not(None))
            .values(rating=rating, comment=comment, deleted_at=None, created_at=now, updated_at=now)
        )
        result = self.session.execute(statement)
        # rowcount == 1: esta request revivio la fila. 0: otra request se
        # le adelanto (o la resena ya estaba viva).
        return result.rowcount == 1

    def list_for_game(
        self, game_id: int, *, offset: int, limit: int
    ) -> tuple[list[tuple[Review, str]], int]:
        """Live (non-deleted) reviews of one game, newest first, each paired
        with its author's display name so the router never has to look the
        user up separately.
        """
        # Condicion comun a la consulta de conteo y a la de la pagina: solo
        # resenas de ESTE juego que no esten soft-deleted.
        live = (Review.game_id == game_id) & Review.deleted_at.is_(None)
        # Cuenta cuantas resenas vivas hay en total (antes de offset/limit)
        # — es el dato que el endpoint necesita para el campo "total".
        total = self.session.execute(select(func.count(Review.id)).where(live)).scalar_one()
        # select(Review, User.full_name) trae la resena Y el nombre del
        # autor en una sola consulta (join), en vez de una consulta extra
        # por cada resena de la pagina.
        statement = (
            select(Review, User.full_name)
            .join(User, User.id == Review.user_id)
            .where(live)
            # Las mas nuevas primero; el id desempata resenas creadas en el
            # mismo instante para que el orden sea siempre determinista.
            .order_by(Review.created_at.desc(), Review.id.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = self.session.exec(statement).all()
        return [(review, author_name) for review, author_name in rows], int(total)
