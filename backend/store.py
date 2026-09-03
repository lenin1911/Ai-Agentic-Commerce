"""
Cart and in-memory store management for Agent Storefront.
Tracks session-scoped carts, validates items against the catalog,
and calculates subtotal and item totals server-side.
"""

import uuid
from typing import Any, Dict, List, Optional
from backend.catalog import CatalogManager, get_catalog_manager


class CartError(Exception):
    """Base exception for cart errors."""

    def __init__(self, message: str, code: str = "CART_ERROR", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class CartItem:
    """Represents an item within a cart."""

    def __init__(self, sku: str, name: str, unit_price: int, quantity: int, currency: str = "INR"):
        self.sku = sku
        self.name = name
        self.unit_price = unit_price
        self.quantity = quantity
        self.currency = currency

    @property
    def total_price(self) -> int:
        return self.unit_price * self.quantity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sku": self.sku,
            "name": self.name,
            "unit_price": self.unit_price,
            "quantity": self.quantity,
            "total_price": self.total_price,
            "currency": self.currency,
        }


class Cart:
    """Represents a session cart."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.items: Dict[str, CartItem] = {}

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self.items.values())

    @property
    def subtotal(self) -> int:
        return sum(item.total_price for item in self.items.values())

    def to_dict(self) -> Dict[str, Any]:
        items_list = [item.to_dict() for item in self.items.values()]
        return {
            "session_id": self.session_id,
            "items": items_list,
            "item_count": self.item_count,
            "subtotal": self.subtotal,
            "currency": "INR",
        }


class Store:
    """In-memory store holding active session carts and performing validations."""

    def __init__(self, catalog_mgr: Optional[CatalogManager] = None):
        self.catalog_mgr = catalog_mgr or get_catalog_manager()
        self._carts: Dict[str, Cart] = {}

    def get_or_create_cart(self, session_id: Optional[str] = None) -> Cart:
        """Retrieves or creates a cart for the session."""
        if not session_id:
            session_id = f"session_{uuid.uuid4().hex[:12]}"
        if session_id not in self._carts:
            self._carts[session_id] = Cart(session_id)
        return self._carts[session_id]

    def add_item(self, session_id: str, sku: str, quantity: int = 1) -> Dict[str, Any]:
        """Adds quantity of an item to the cart after validating SKU and stock."""
        if not isinstance(quantity, int) or quantity <= 0:
            raise CartError(
                "Quantity must be a positive integer.",
                code="INVALID_QUANTITY",
                status_code=400,
            )

        product = self.catalog_mgr.get_product(sku)
        if not product:
            raise CartError(
                f"SKU '{sku}' does not exist in catalog.",
                code="INVALID_SKU",
                status_code=400,
            )

        if not product.get("agent_eligible", False):
            raise CartError(
                f"Product '{sku}' is not eligible for agent purchase.",
                code="SKU_NOT_ELIGIBLE",
                status_code=400,
            )

        cart = self.get_or_create_cart(session_id)
        current_qty = cart.items[sku].quantity if sku in cart.items else 0
        new_qty = current_qty + quantity

        available_stock = product.get("stock", 0)
        if new_qty > available_stock:
            raise CartError(
                f"Requested total quantity {new_qty} exceeds available stock ({available_stock}).",
                code="INSUFFICIENT_STOCK",
                status_code=400,
            )

        if sku in cart.items:
            cart.items[sku].quantity = new_qty
        else:
            cart.items[sku] = CartItem(
                sku=product["sku"],
                name=product["name"],
                unit_price=product["price"],
                quantity=new_qty,
                currency=product.get("currency", "INR"),
            )

        return cart.to_dict()

    def update_item(self, session_id: str, sku: str, quantity: int) -> Dict[str, Any]:
        """Updates item quantity. If quantity is 0, removes the item."""
        if not isinstance(quantity, int) or quantity < 0:
            raise CartError(
                "Quantity must be a non-negative integer.",
                code="INVALID_QUANTITY",
                status_code=400,
            )

        if quantity == 0:
            return self.remove_item(session_id, sku)

        cart = self.get_or_create_cart(session_id)
        product = self.catalog_mgr.get_product(sku)
        if not product:
            raise CartError(
                f"SKU '{sku}' does not exist in catalog.",
                code="INVALID_SKU",
                status_code=400,
            )

        available_stock = product.get("stock", 0)
        if quantity > available_stock:
            raise CartError(
                f"Requested quantity {quantity} exceeds available stock ({available_stock}).",
                code="INSUFFICIENT_STOCK",
                status_code=400,
            )

        if sku in cart.items:
            cart.items[sku].quantity = quantity
        else:
            if not product.get("agent_eligible", False):
                raise CartError(
                    f"Product '{sku}' is not eligible for agent purchase.",
                    code="SKU_NOT_ELIGIBLE",
                    status_code=400,
                )
            cart.items[sku] = CartItem(
                sku=product["sku"],
                name=product["name"],
                unit_price=product["price"],
                quantity=quantity,
                currency=product.get("currency", "INR"),
            )

        return cart.to_dict()

    def remove_item(self, session_id: str, sku: str) -> Dict[str, Any]:
        """Removes an item completely from the cart."""
        cart = self.get_or_create_cart(session_id)
        if sku in cart.items:
            del cart.items[sku]
        return cart.to_dict()

    def clear_cart(self, session_id: str) -> Dict[str, Any]:
        """Clears all items in the cart."""
        cart = self.get_or_create_cart(session_id)
        cart.items.clear()
        return cart.to_dict()

    def get_cart_dict(self, session_id: str) -> Dict[str, Any]:
        """Returns cart representation as dictionary."""
        cart = self.get_or_create_cart(session_id)
        return cart.to_dict()

    def reset_all(self) -> None:
        """Resets all store sessions (primarily for testing)."""
        self._carts.clear()


# Default singleton
_default_store: Optional[Store] = None


def get_store(catalog_mgr: Optional[CatalogManager] = None) -> Store:
    global _default_store
    if _default_store is None:
        _default_store = Store(catalog_mgr=catalog_mgr)
    return _default_store
