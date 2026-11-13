"""Review endpoints (Fase 6). Listing a game's reviews is public (level 1 of
the plan's "Modelo de autorizacion"); creating, editing and deleting need
CurrentUser. Like every router, this one only translates HTTP <-> Python:
every rule (ownership of the game, one review per title, author-or-admin)
lives in app.services.review_service.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import CurrentUser
from app.models import Review
from app.schemas.errors import errors
from app.schemas.review import ReviewCreate, ReviewPage, ReviewRead, ReviewUpdate
from app.services import review_service

router = APIRouter(tags=["reviews"])

SessionDep = Annotated[Session, Depends(get_session)]


def _to_read(review: Review, author_name: str) -> ReviewRead:
    # Funcion privada compartida por todos los endpoints de esta pagina: la
    # conversion Review -> ReviewRead vive en un solo lugar. author_name
    # viene aparte porque el modelo Review solo guarda el user_id.
    return ReviewRead(
        id=review.id,
        game_id=review.game_id,
        author_name=author_name,
        rating=review.rating,
        comment=review.comment,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


# POST /games/{game_id}/reviews — resenar un juego que el usuario posee.
# Responde 403 si no lo posee y 409 si ya lo resena (ver review_service).
@router.post(
    "/games/{game_id}/reviews",
    response_model=ReviewRead,
    status_code=status.HTTP_201_CREATED,
    summary="Resenar un juego",
    description=(
        "Publica tu resena (puntaje 1 a 5 y comentario opcional). Solo puedes resenar juegos "
        "que **posees** en tu biblioteca, y una resena por juego. Si borraste tu resena antes, "
        "esta llamada la reactiva."
    ),
    responses=errors(
        401,
        (
            403,
            "La cuenta esta suspendida, o no posees el juego (cometelo primero con el checkout).",
        ),
        (404, "El juego no existe o no esta a la venta."),
        (409, "Ya resenaste este juego: edita tu resena existente con PATCH."),
        422,
    ),
)
def create_review(
    game_id: int, payload: ReviewCreate, session: SessionDep, current_user: CurrentUser
) -> ReviewRead:
    review = review_service.create_review(
        session, user=current_user, game_id=game_id, payload=payload
    )
    # Aca el autor es siempre el usuario logueado, asi que su nombre ya se
    # tiene a mano.
    return _to_read(review, current_user.full_name)


# GET /games/{slug}/reviews — publico y paginado, las mas nuevas primero.
@router.get(
    "/games/{slug}/reviews",
    response_model=ReviewPage,
    summary="Listar las resenas de un juego",
    description="**Publico.** Resenas paginadas de un juego (por su `slug`), las mas nuevas primero.",
    responses=errors((404, "No existe un juego con ese slug."), 422),
)
def list_reviews(
    slug: str,
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ReviewPage:
    rows, total, pages = review_service.list_reviews(session, slug=slug, page=page, size=size)
    return ReviewPage(
        items=[_to_read(review, author_name) for review, author_name in rows],
        page=page,
        size=size,
        total=total,
        pages=pages,
    )


# PATCH /reviews/{review_id} — actualizacion parcial, solo del autor o un
# admin. La resena de otro usuario responde 404 (no 403).
@router.patch(
    "/reviews/{review_id}",
    response_model=ReviewRead,
    summary="Editar una resena",
    description=(
        "Cambia el puntaje y/o el comentario (manda solo lo que quieras cambiar). "
        "`comment: null` borra el comentario; `rating` no puede ser `null`. Solo la puede "
        "editar su autor o un admin; la resena de otro usuario responde `404`."
    ),
    responses=errors(
        401,
        403,
        (404, "La resena no existe o es de otro usuario."),
        (422, "Body invalido, vacio (hay que enviar al menos un campo) o `rating: null`."),
    ),
)
def update_review(
    review_id: int, payload: ReviewUpdate, session: SessionDep, current_user: CurrentUser
) -> ReviewRead:
    review, author_name = review_service.update_review(
        session, current_user=current_user, review_id=review_id, payload=payload
    )
    return _to_read(review, author_name)


# DELETE /reviews/{review_id} — soft delete, solo del autor o un admin.
@router.delete(
    "/reviews/{review_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar una resena",
    description=(
        "Borrado **logico** (la resena deja de mostrarse). Solo su autor o un admin; "
        "la de otro usuario responde `404`."
    ),
    responses=errors(401, 403, (404, "La resena no existe o es de otro usuario."), 422),
)
def delete_review(review_id: int, session: SessionDep, current_user: CurrentUser) -> None:
    review_service.soft_delete_review(session, current_user=current_user, review_id=review_id)
