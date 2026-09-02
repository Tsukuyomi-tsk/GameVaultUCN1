"""Import every SQLModel table so SQLModel.metadata is fully populated —
Alembic's autogenerate and any `SQLModel.metadata.create_all()` call both
rely on every model having been imported at least once before they run.
"""

from __future__ import annotations

# Side effect: sets SQLModel.metadata.naming_convention before any table's
# constraint names get resolved. Must stay the first import in this module.
import app.core.database  # noqa: F401
from app.models.cart import Cart
from app.models.cart_item import CartItem
from app.models.category import Category
from app.models.enums import OrderStatus, UserRole
from app.models.game import Game
from app.models.game_category_link import GameCategoryLink
from app.models.game_image import GameImage
from app.models.library_item import LibraryItem
from app.models.offer import Offer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.review import Review
from app.models.token_blacklist import TokenBlacklist
from app.models.user import User
from app.models.verification_code import VerificationCode
from app.models.wishlist_item import WishlistItem

__all__ = [
    "Cart",
    "CartItem",
    "Category",
    "Game",
    "GameCategoryLink",
    "GameImage",
    "LibraryItem",
    "Offer",
    "Order",
    "OrderItem",
    "OrderStatus",
    "Review",
    "TokenBlacklist",
    "User",
    "UserRole",
    "VerificationCode",
    "WishlistItem",
]
