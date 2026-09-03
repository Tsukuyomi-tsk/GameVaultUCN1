"""Data access for TokenBlacklist.

Only covers explicitly revoked (logged-out) tokens — see the model's own
docstring for what this table cannot do (bulk-revoke a user's sessions).
"""

from __future__ import annotations

from sqlmodel import select

from app.models.token_blacklist import TokenBlacklist
from app.repositories.base import BaseRepository


class TokenBlacklistRepository(BaseRepository[TokenBlacklist]):
    model = TokenBlacklist

    def is_revoked(self, jti: str) -> bool:
        statement = select(TokenBlacklist).where(TokenBlacklist.jti == jti)
        return self.session.exec(statement).first() is not None
