"""Data access for VerificationCode — see the "one live code at a time"
invariant in app/services/auth_service.py, which this class supports but
does not itself enforce (enforcement is business logic, not a query).
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import select

from app.models.verification_code import VerificationCode
from app.repositories.base import BaseRepository


class VerificationCodeRepository(BaseRepository[VerificationCode]):
    model = VerificationCode

    def get_active_for_user(self, user_id: int, now: datetime) -> VerificationCode | None:
        """The single unconsumed, non-invalidated, unexpired code for a
        user, if any.
        """
        statement = select(VerificationCode).where(
            VerificationCode.user_id == user_id,
            VerificationCode.consumed_at.is_(None),
            VerificationCode.invalidated_at.is_(None),
            VerificationCode.expires_at > now,
        )
        return self.session.exec(statement).first()

    def get_latest_for_user(self, user_id: int) -> VerificationCode | None:
        """The most recently issued code for a user, regardless of its
        state — used only to compute the resend cooldown window.
        """
        statement = (
            select(VerificationCode)
            .where(VerificationCode.user_id == user_id)
            .order_by(VerificationCode.created_at.desc())
        )
        return self.session.exec(statement).first()

    def invalidate_all_unconsumed(self, user_id: int, now: datetime) -> None:
        """Close out every still-open code for a user.

        Called before issuing a new one, in the same transaction, so at
        most one code is ever valid at a time — see
        app/services/auth_service.py.
        """
        statement = select(VerificationCode).where(
            VerificationCode.user_id == user_id,
            VerificationCode.consumed_at.is_(None),
            VerificationCode.invalidated_at.is_(None),
        )
        for code in self.session.exec(statement).all():
            code.invalidated_at = now
            self.session.add(code)
        self.session.flush()
