"""Business logic for game reviews (Fase 6).

Two rules the database cannot express on its own (see Review's docstring):

- Eligibility: only someone who owns the game (a LibraryItem row) may
  review it. Failing that is a 403, not a 404 — the game is a public
  resource, so this is a business rule about an *action*, unlike
  ensure_owner_or_admin's 404, whose job is to hide that someone else's
  resource exists.
- One review per (user, game): a live duplicate is a 409. The
  UniqueConstraint also counts soft-deleted rows, so a user who deleted
  their review and writes a new one gets the old row revived (reset to the
  new rating/comment) instead of a second INSERT that would violate it.

Concurrent duplicates (two POSTs racing past the "already exists?" check)
are settled by that same UniqueConstraint: the loser's IntegrityError is
turned into the same 409 the sequential path raises.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.dependencies import ensure_owner_or_admin
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.time import utcnow
from app.models import Game, Review, User
from app.repositories.game_repository import GameRepository
from app.repositories.library_repository import LibraryRepository
from app.repositories.review_repository import ReviewRepository
from app.repositories.user_repository import UserRepository
from app.schemas.review import ReviewCreate, ReviewUpdate


def _get_public_game(game: Game | None) -> Game:
    # games.get() / get_by_slug() ya excluyen los juegos soft-deleted;
    # is_active se chequea aparte (igual que hace el carrito). Un juego
    # inexistente, borrado o inactivo se trata igual: 404.
    if game is None or not game.is_active:
        raise NotFoundError("Juego no encontrado.")
    return game


def create_review(session: Session, *, user: User, game_id: int, payload: ReviewCreate) -> Review:
    games = GameRepository(session)
    reviews = ReviewRepository(session)
    game = _get_public_game(games.get(game_id))

    # Regla de elegibilidad: hay que poseer el juego. Es un 403 (no un
    # 404): el juego es publico, no se oculta nada — simplemente esta
    # accion no esta permitida para quien no lo compro.
    if not LibraryRepository(session).owns(user_id=user.id, game_id=game.id):
        raise ForbiddenError("Solo puedes resenar juegos que posees en tu biblioteca.")

    # Se busca INCLUYENDO las resenas soft-deleted (ver el repositorio): el
    # UniqueConstraint tambien las cuenta.
    existing = reviews.get_by_user_and_game(user_id=user.id, game_id=game.id)
    if existing is not None and existing.deleted_at is None:
        raise ConflictError("Ya resenaste este juego. Edita tu resena existente.")

    # Todo el bloque de escritura va dentro del try: igual que en el
    # checkout, el IntegrityError de una carrera concurrente salta en el
    # flush() que hace reviews.add(), no recien en el commit().
    try:
        if existing is not None:
            # Existia pero estaba soft-deleted: se "revive" la misma fila
            # con los datos nuevos, como si fuera una resena recien creada.
            # revive() es un UPDATE condicional atomico (ver el
            # repositorio): devuelve False si otra request ya la revivio
            # justo antes, y en ese caso se responde el mismo 409.
            if not reviews.revive(
                existing.id, rating=payload.rating, comment=payload.comment, now=utcnow()
            ):
                raise ConflictError("Ya resenaste este juego. Edita tu resena existente.")
            review = existing
        else:
            review = reviews.add(
                Review(
                    user_id=user.id,
                    game_id=game.id,
                    rating=payload.rating,
                    comment=payload.comment,
                )
            )
        session.commit()
    except IntegrityError:
        # Otra request creo la resena de este (usuario, juego) justo antes:
        # se deshace todo y se responde el mismo 409 del camino secuencial.
        session.rollback()
        raise ConflictError("Ya resenaste este juego. Edita tu resena existente.") from None
    session.refresh(review)
    return review


def list_reviews(
    session: Session, *, slug: str, page: int, size: int
) -> tuple[list[tuple[Review, str]], int, int]:
    """Returns (rows, total, pages); each row is (Review, author_name)."""
    games = GameRepository(session)
    game = _get_public_game(games.get_by_slug(slug))
    offset = (page - 1) * size
    rows, total = ReviewRepository(session).list_for_game(game.id, offset=offset, limit=size)
    # Division hacia arriba: 41 resenas con size=20 son 3 paginas. Sin
    # resenas, pages es 0 (mismo criterio que el catalogo).
    pages = (total + size - 1) // size if total else 0
    return rows, total, pages


def _get_review_for_write(session: Session, *, current_user: User, review_id: int) -> Review:
    # reviews.get() oculta las resenas soft-deleted: borrar o editar una
    # resena ya borrada responde 404, igual que si nunca hubiera existido.
    review = ReviewRepository(session).get(review_id)
    if review is None:
        raise NotFoundError("Resena no encontrada.")
    # Solo el autor o un admin pueden tocarla; cualquier otro recibe 404
    # (no 403), para no confirmar que esa resena existe.
    ensure_owner_or_admin(review.user_id, current_user)
    return review


def update_review(
    session: Session, *, current_user: User, review_id: int, payload: ReviewUpdate
) -> tuple[Review, str]:
    """Returns (review, author_name) — the author may not be `current_user`
    when an admin edits someone else's review.
    """
    reviews = ReviewRepository(session)
    review = _get_review_for_write(session, current_user=current_user, review_id=review_id)

    # exclude_unset=True: solo entran al dict los campos que el cliente
    # realmente mando en el body (ver la explicacion detallada de este
    # patron en admin_game_service.update_game).
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise ValidationError("Debes enviar al menos un campo para actualizar.")
    # rating es obligatorio en la base de datos: se puede omitir, pero no
    # mandarlo explicitamente en null (el comentario si se puede vaciar).
    if "rating" in data and data["rating"] is None:
        raise ValidationError("El puntaje no puede ser null.")

    # Aplica cada campo presente en el body sobre la resena ya cargada.
    for field, value in data.items():
        setattr(review, field, value)
    review.updated_at = utcnow()

    reviews.add(review)
    session.commit()
    session.refresh(review)
    return review, _author_name(session, review)


def soft_delete_review(session: Session, *, current_user: User, review_id: int) -> None:
    reviews = ReviewRepository(session)
    review = _get_review_for_write(session, current_user=current_user, review_id=review_id)
    # Soft delete: la fila se conserva con deleted_at marcado (ver el
    # docstring del modelo) — desaparece de los listados y del promedio de
    # puntaje del catalogo, que ya filtran deleted_at IS NULL.
    review.deleted_at = utcnow()
    reviews.add(review)
    session.commit()


def _author_name(session: Session, review: Review) -> str:
    author = UserRepository(session).get(review.user_id)
    # El autor siempre existe: reviews.user_id es FK con ON DELETE CASCADE,
    # asi que una resena nunca sobrevive a su usuario.
    return author.full_name
