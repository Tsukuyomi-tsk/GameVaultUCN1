"""Data access for TokenBlacklist.

Only covers explicitly revoked (logged-out) tokens — see the model's own
docstring for what this table cannot do (bulk-revoke a user's sessions).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete
from sqlmodel import select

from app.models.token_blacklist import TokenBlacklist
from app.repositories.base import BaseRepository


class TokenBlacklistRepository(BaseRepository[TokenBlacklist]):
    model = TokenBlacklist

    def is_revoked(self, jti: str) -> bool:
        statement = select(TokenBlacklist).where(TokenBlacklist.jti == jti)
        return self.session.exec(statement).first() is not None

    def delete_expired(self, now: datetime) -> int:
        """Remove blacklist rows whose token has expired. Returns how many.

        Safe by construction: an expired JWT is already rejected by its own
        `exp` claim (decode_access_token), so its blacklist row no longer
        protects anything and would only make the table grow forever.
        """
        # DELETE FROM token_blacklist WHERE expires_at < <ahora>: borra de
        # una sola vez todos los tokens revocados que ya vencieron.
        result = self.session.execute(
            delete(TokenBlacklist).where(TokenBlacklist.expires_at < now),
            # Borrado masivo: no hay objetos cargados que sincronizar.
            execution_options={"synchronize_session": False},
        )
        # Cuantas filas se borraron (para el log del job).
        return result.rowcount
