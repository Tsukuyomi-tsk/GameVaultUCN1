"""Admin user management: paginated listing, suspend/reactivate.

Every route requires AdminUser. The self-suspend guard and the actual
suspension fields live in app.services.admin_user_service.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import AdminUser
from app.models.enums import UserRole
from app.schemas.admin_user import AdminUserRead, SuspendUserRequest, UserPage
from app.schemas.errors import ADMIN_RESPONSES, errors
from app.services import admin_user_service

router = APIRouter(prefix="/admin/users", tags=["admin-users"], responses=ADMIN_RESPONSES)

SessionDep = Annotated[Session, Depends(get_session)]


# GET /admin/users — listado paginado, con filtros opcionales de rol y
# estado de suspension.
@router.get(
    "",
    response_model=UserPage,
    summary="Listar usuarios",
    description="Listado paginado de usuarios, con filtros opcionales por `role` y `is_suspended`.",
    responses=errors(422),
)
def list_users(
    session: SessionDep,
    _admin: AdminUser,
    role: UserRole | None = None,
    is_suspended: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> UserPage:
    items, total, pages = admin_user_service.list_users(
        session, role=role, is_suspended=is_suspended, page=page, size=size
    )
    return UserPage(
        items=[AdminUserRead.model_validate(u) for u in items],
        page=page,
        size=size,
        total=total,
        pages=pages,
    )


# PATCH /admin/users/{user_id}/suspend — suspende una cuenta.
@router.patch(
    "/{user_id}/suspend",
    response_model=AdminUserRead,
    summary="Suspender una cuenta",
    description=(
        "Suspende la cuenta con un motivo. Tiene efecto inmediato, tambien sobre tokens "
        "ya emitidos (reciben `403`). Un admin no puede suspenderse a si mismo."
    ),
    responses=errors(
        (404, "El usuario no existe."),
        (409, "Intentaste suspender tu propia cuenta."),
        (422, "Falta el motivo o esta vacio."),
    ),
)
def suspend_user(
    user_id: int,
    payload: SuspendUserRequest,
    session: SessionDep,
    # Aca el parametro se llama "admin" (sin guion bajo), a diferencia del
    # resto de las rutas: esta ruta SI necesita usar el objeto — para
    # sacarle el id y pasarselo al servicio (que valida que un admin no se
    # pueda suspender a si mismo).
    admin: AdminUser,
) -> AdminUserRead:
    user = admin_user_service.suspend_user(
        session, admin_id=admin.id, user_id=user_id, reason=payload.reason
    )
    return AdminUserRead.model_validate(user)


# PATCH /admin/users/{user_id}/reactivate — revierte una suspension.
@router.patch(
    "/{user_id}/reactivate",
    response_model=AdminUserRead,
    summary="Reactivar una cuenta",
    description="Levanta la suspension de la cuenta.",
    responses=errors((404, "El usuario no existe."), 422),
)
def reactivate_user(user_id: int, session: SessionDep, _admin: AdminUser) -> AdminUserRead:
    user = admin_user_service.reactivate_user(session, user_id=user_id)
    return AdminUserRead.model_validate(user)
