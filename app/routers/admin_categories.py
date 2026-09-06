"""Admin category backoffice: CRUD + soft delete/restore.

Every route requires AdminUser. Only translates HTTP <-> Python — the
rules live in app.services.admin_category_service.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import AdminUser
from app.schemas.admin_category import CategoryAdminRead, CategoryCreate, CategoryUpdate
from app.services import admin_category_service

router = APIRouter(prefix="/admin/categories", tags=["admin-categories"])

SessionDep = Annotated[Session, Depends(get_session)]


# GET /admin/categories — listado completo (sin paginar: son pocas
# categorias, a diferencia de los juegos).
@router.get("", response_model=list[CategoryAdminRead])
def list_categories(session: SessionDep, _admin: AdminUser) -> list[CategoryAdminRead]:
    categories = admin_category_service.list_categories(session)
    # Convierte cada Category del ORM a su schema de respuesta.
    return [CategoryAdminRead.model_validate(c) for c in categories]


# POST /admin/categories — crear una categoria nueva.
@router.post("", response_model=CategoryAdminRead, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate, session: SessionDep, _admin: AdminUser
) -> CategoryAdminRead:
    category = admin_category_service.create_category(session, payload=payload)
    return CategoryAdminRead.model_validate(category)


# PATCH /admin/categories/{category_id} — actualizacion parcial.
@router.patch("/{category_id}", response_model=CategoryAdminRead)
def update_category(
    category_id: int, payload: CategoryUpdate, session: SessionDep, _admin: AdminUser
) -> CategoryAdminRead:
    category = admin_category_service.update_category(
        session, category_id=category_id, payload=payload
    )
    return CategoryAdminRead.model_validate(category)


# DELETE /admin/categories/{category_id} — soft delete (idempotente).
@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, session: SessionDep, _admin: AdminUser) -> None:
    admin_category_service.soft_delete_category(session, category_id=category_id)


# POST /admin/categories/{category_id}/restore — deshace el soft delete.
@router.post("/{category_id}/restore", response_model=CategoryAdminRead)
def restore_category(category_id: int, session: SessionDep, _admin: AdminUser) -> CategoryAdminRead:
    category = admin_category_service.restore_category(session, category_id=category_id)
    return CategoryAdminRead.model_validate(category)
