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
    # Le dice a BaseRepository con que modelo/tabla trabaja esta clase —
    # get()/add()/delete() heredados ya saben operar sobre "game_images".
    model = GameImage

    def list_for_game(self, game_id: int) -> list[GameImage]:
        # select(GameImage) arma un SELECT * FROM game_images ...
        statement = (
            select(GameImage)
            # ...filtrado a las imagenes de UN solo juego...
            .where(GameImage.game_id == game_id)
            # ...ordenadas para que la portada (is_cover=True) salga
            # siempre primero, y dentro de eso, por el orden manual
            # (sort_order) que el admin haya definido.
            .order_by(GameImage.is_cover.desc(), GameImage.sort_order.asc())
        )
        # session.exec ejecuta la consulta contra la base de datos y
        # devuelve un iterador de resultados; list(...) lo materializa en
        # una lista normal de objetos GameImage.
        return list(self.session.exec(statement).all())

    def clear_cover(self, game_id: int) -> None:
        """Unsets `is_cover` on every image of a game — called before
        flagging a new one as cover, so at most one image is ever the
        cover at a time.
        """
        # Trae TODAS las imagenes del juego (reutiliza el metodo de arriba
        # en vez de escribir la misma query dos veces).
        images = self.list_for_game(game_id)
        for image in images:
            if image.is_cover:
                # Se apaga la bandera de portada en memoria...
                image.is_cover = False
                # ...y se marca el objeto para que SQLAlchemy lo incluya
                # en el proximo flush/commit (session.add sobre un objeto
                # que YA existe en la base de datos funciona como un
                # "guardar cambios", no como un "crear de nuevo").
                self.session.add(image)
        # flush() empuja los UPDATE a la base de datos dentro de la
        # transaccion actual, pero SIN hacer commit todavia — el commit
        # final es responsabilidad del servicio que llamo a este metodo.
        self.session.flush()
