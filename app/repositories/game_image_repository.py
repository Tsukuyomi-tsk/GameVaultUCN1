"""Data access for GameImage — the admin-only write side of catalog media.
Reads for the public catalog stay in game_repository.py (they're joined
into the same query as the rest of a game's detail); this repository is
only for the admin CRUD in admin_game_service.py.
"""

from __future__ import annotations

from sqlmodel import select

from app.models import GameImage
from app.repositories.base import BaseRepository


class GameImageRepository(BaseRepository[GameImage]):
    model = GameImage

    def list_for_game(self, game_id: int) -> list[GameImage]:
        statement = (
            select(GameImage)
            .where(GameImage.game_id == game_id)
            .order_by(GameImage.is_cover.desc(), GameImage.sort_order.asc())
        )
        return list(self.session.exec(statement).all())

    def clear_cover(self, game_id: int) -> None:
        """Unsets `is_cover` on every image of a game — called before
        flagging a new one as cover, so at most one image is ever the
        cover at a time.
        """
        images = self.list_for_game(game_id)
        for image in images:
            if image.is_cover:
                image.is_cover = False
                self.session.add(image)
        self.session.flush()
