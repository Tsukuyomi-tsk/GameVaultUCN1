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
from app.services import admin_user_service

router = APIRouter(prefix="/admin/users", tags=["admin-users"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=UserPage)
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


@router.patch("/{user_id}/suspend", response_model=AdminUserRead)
def suspend_user(
    user_id: int, payload: SuspendUserRequest, session: SessionDep, admin: AdminUser
) -> AdminUserRead:
    user = admin_user_service.suspend_user(
        session, admin_id=admin.id, user_id=user_id, reason=payload.reason
    )
    return AdminUserRead.model_validate(user)


@router.patch("/{user_id}/reactivate", response_model=AdminUserRead)
def reactivate_user(user_id: int, session: SessionDep, _admin: AdminUser) -> AdminUserRead:
    user = admin_user_service.reactivate_user(session, user_id=user_id)
    return AdminUserRead.model_validate(user)
