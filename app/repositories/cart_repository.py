"""Data access for the shopping cart (Fase 5).

A cart belongs to exactly one owner — a `user_id` o un `session_token`,
nunca ambos, nunca ninguno (lo impone el propio CheckConstraint de Cart) —
asi que cada busqueda aca se hace por uno u otro. Volver a agregar un juego
ya presente es un no-op en esta capa (ver el docstring de CartItem): el
chequeo-antes-de-insertar de abajo sigue el mismo estilo ya usado en otras
partes de este codigo (ej. admin_offer_service._check_no_overlap),
respaldado por el UniqueConstraint de (cart_id, game_id) como ultima
garantia si algo se escapa del chequeo.
"""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import select

from app.core.time import utcnow
from app.models import Cart, CartItem, Game
from app.repositories.base import BaseRepository


class CartRepository(BaseRepository[Cart]):
    # Le indica a BaseRepository sobre que tabla trabajan get()/add()/
    # delete() heredados: "carts".
    model = Cart

    def get_by_user(self, user_id: int) -> Cart | None:
        # Cart.user_id es unique=True: a lo sumo un carrito por usuario, asi
        # que .first() nunca puede devolver el carrito "equivocado".
        return self.session.exec(select(Cart).where(Cart.user_id == user_id)).first()

    def get_by_session_token(self, session_token: str) -> Cart | None:
        # Mismo razonamiento que get_by_user, pero para el carrito de un
        # invitado: session_token tambien es unique=True.
        return self.session.exec(select(Cart).where(Cart.session_token == session_token)).first()

    def list_items_with_games(self, cart_id: int) -> list[tuple[CartItem, Game]]:
        """Every item in the cart, joined to its Game — the join is safe
        without an is_active/deleted_at filter because CartItem.game_id is
        ON DELETE CASCADE (see cart_item.py): a hard-deleted game can never
        leave a dangling cart item. An inactive/soft-deleted game is still
        shown here; checkout is what actually rejects it.
        """
        # select(CartItem, Game) trae AMBAS tablas en cada fila (una tupla
        # (CartItem, Game) por resultado) en una sola consulta, en vez de
        # traer los CartItem y despues consultar cada Game por separado
        # (evita el problema N+1).
        statement = (
            select(CartItem, Game)
            .join(Game, Game.id == CartItem.game_id)
            .where(CartItem.cart_id == cart_id)
            # Orden estable por id de insercion: los items siempre aparecen
            # en el mismo orden en que se agregaron al carrito.
            .order_by(CartItem.id.asc())
        )
        return list(self.session.exec(statement).all())

    def add_item(self, *, cart_id: int, game_id: int) -> None:
        # Un solo INSERT ... ON CONFLICT DO NOTHING: si el juego YA esta en
        # el carrito (UniqueConstraint cart_id + game_id) la base de datos
        # simplemente ignora el INSERT — agregar el mismo juego dos veces
        # es un no-op, no un error (ver el docstring de CartItem). Se hace
        # en UN statement en vez de "buscar y despues insertar" porque con
        # dos pasos, dos requests simultaneas pasaban la busqueda a la vez
        # y la segunda reventaba con IntegrityError (500).
        result = self.session.execute(
            sqlite_insert(CartItem)
            .values(cart_id=cart_id, game_id=game_id)
            .on_conflict_do_nothing(index_elements=["cart_id", "game_id"])
        )
        if result.rowcount == 0:
            # El juego ya estaba: nada cambio, no hace falta tocar el carrito.
            return
        # Actualiza el updated_at del carrito, ya que su contenido cambio.
        self._touch(cart_id)
        # flush() manda los cambios pendientes a la base de datos dentro de
        # la transaccion actual, sin confirmarla todavia (eso lo decide el
        # servicio que llama).
        self.session.flush()

    def remove_item(self, *, cart_id: int, game_id: int) -> bool:
        # Busca la fila exacta a borrar (un carrito + un juego puntual).
        item = self.session.exec(
            select(CartItem).where(CartItem.cart_id == cart_id, CartItem.game_id == game_id)
        ).first()
        if item is None:
            # Si el juego no estaba en el carrito, no hay nada que borrar —
            # se informa al llamador con False en vez de lanzar un error.
            return False
        self.session.delete(item)
        self._touch(cart_id)
        self.session.flush()
        return True

    def clear(self, cart_id: int) -> None:
        # delete(CartItem)... arma un DELETE FROM cart_items WHERE
        # cart_id = ... de una sola vez — mucho mas simple y eficiente que
        # traer cada item y borrarlo uno por uno. Se ejecuta con
        # session.execute() (no session.exec()) porque es una sentencia
        # DELETE, no un SELECT.
        self.session.execute(delete(CartItem).where(CartItem.cart_id == cart_id))
        self._touch(cart_id)
        self.session.flush()

    def merge_into(self, *, source_cart_id: int, target_cart_id: int) -> None:
        """Moves every item from the guest cart into the user's cart,
        skipping any game the user's cart already has (no duplicates), then
        empties the source. The caller is responsible for hard-deleting the
        now-empty source Cart row afterwards.
        """
        # Primero averigua que juegos YA tiene el carrito destino (el del
        # usuario logueado) — un set() para que la busqueda "esta este
        # game_id adentro" sea O(1) en el for de abajo.
        target_game_ids = set(
            self.session.exec(
                select(CartItem.game_id).where(CartItem.cart_id == target_cart_id)
            ).all()
        )
        # Trae TODOS los items del carrito origen (el de invitado).
        source_items = self.session.exec(
            select(CartItem).where(CartItem.cart_id == source_cart_id)
        ).all()
        for item in source_items:
            # Solo se copia al carrito destino si ese juego todavia NO
            # estaba ahi — evita violar el UniqueConstraint (cart_id,
            # game_id) y evita duplicados logicos.
            if item.game_id not in target_game_ids:
                self.session.add(CartItem(cart_id=target_cart_id, game_id=item.game_id))
            # El item de origen se borra SIEMPRE, este o no duplicado — el
            # carrito de invitado queda vacio al terminar el merge.
            self.session.delete(item)
        self._touch(target_cart_id)
        self.session.flush()

    def _touch(self, cart_id: int) -> None:
        """Bumps updated_at on the cart itself whenever its items change —
        same convention as Game/Category on an admin edit.
        """
        # Metodo privado (el guion bajo al inicio es la convencion de
        # Python para "uso interno de esta clase, no para el resto de la
        # app"): actualiza la marca de tiempo del carrito cada vez que su
        # contenido cambia.
        cart = self.session.get(Cart, cart_id)
        if cart is not None:
            cart.updated_at = utcnow()
            self.session.add(cart)
