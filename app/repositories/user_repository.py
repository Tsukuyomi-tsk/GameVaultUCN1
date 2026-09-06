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
        statement = select(User)
        if role is not None:
            statement = statement.where(User.role == role)
        if is_suspended is not None:
            statement = statement.where(User.is_suspended == is_suspended)

        total = self.session.execute(statement.with_only_columns(func.count(User.id))).scalar_one()

        rows = self.session.exec(
            statement.order_by(User.created_at.desc()).offset(offset).limit(limit)
        ).all()
        return list(rows), int(total)
