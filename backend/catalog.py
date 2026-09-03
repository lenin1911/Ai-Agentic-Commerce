"""
Catalog management for Agent Storefront.
Loads, validates, and exposes machine-readable catalog data for AI agents.
"""

import json
import os
from typing import Any, Dict, List, Optional

DEFAULT_CATALOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "catalog_seed.json",
)


class CatalogValidationError(Exception):
    """Raised when catalog data fails schema or validation checks."""
    pass


class CatalogManager:
    """Manages loading, validation, and querying of the product catalog."""

    def __init__(self, catalog_path: Optional[str] = None):
        self.catalog_path = catalog_path or os.environ.get(
            "CATALOG_PATH", DEFAULT_CATALOG_PATH
        )
        self._raw_data: Dict[str, Any] = {}
        self._products_by_sku: Dict[str, Dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        """Reloads and re-validates the catalog from disk."""
        if not os.path.exists(self.catalog_path):
            raise FileNotFoundError(f"Catalog file not found: {self.catalog_path}")

        try:
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise CatalogValidationError(f"Invalid JSON in catalog: {exc}") from exc

        self._validate_catalog(data)
        self._raw_data = data
        self._products_by_sku = {p["sku"]: p for p in data.get("products", [])}

    def _validate_catalog(self, data: Dict[str, Any]) -> None:
        """Validates catalog schema."""
        if not isinstance(data, dict):
            raise CatalogValidationError("Root catalog must be a JSON object.")

        store = data.get("store")
        if not store or not isinstance(store, dict):
            raise CatalogValidationError("Catalog missing valid 'store' section.")

        if "name" not in store or "currency" not in store:
            raise CatalogValidationError("Store missing required 'name' or 'currency'.")

        products = data.get("products")
        if not isinstance(products, list):
            raise CatalogValidationError("Catalog missing 'products' list.")

        required_product_fields = [
            "sku",
            "name",
            "description",
            "price",
            "currency",
            "stock",
            "category",
            "agent_eligible",
        ]

        skus_seen = set()
        for idx, prod in enumerate(products):
            if not isinstance(prod, dict):
                raise CatalogValidationError(f"Product at index {idx} must be an object.")

            for field in required_product_fields:
                if field not in prod:
                    raise CatalogValidationError(
                        f"Product {prod.get('sku', idx)} missing required field '{field}'."
                    )

            if prod["price"] < 0:
                raise CatalogValidationError(f"Product {prod['sku']} price cannot be negative.")

            if prod["stock"] < 0:
                raise CatalogValidationError(f"Product {prod['sku']} stock cannot be negative.")

            sku = prod["sku"]
            if sku in skus_seen:
                raise CatalogValidationError(f"Duplicate SKU found: '{sku}'.")
            skus_seen.add(sku)

    def get_raw_data(self) -> Dict[str, Any]:
        """Returns the full catalog data including internal configurations."""
        return self._raw_data

    def get_agent_catalog(self) -> Dict[str, Any]:
        """
        Returns clean, agent-readable catalog representation.
        Exposes store capabilities, policies, and agent-purchasable products.
        """
        store = self._raw_data.get("store", {})
        products = self._raw_data.get("products", [])

        # Format items clearly for machine consumption
        agent_items: List[Dict[str, Any]] = []
        for p in products:
            agent_items.append({
                "sku": p["sku"],
                "name": p["name"],
                "description": p["description"],
                "price": p["price"],
                "currency": p["currency"],
                "in_stock": p["stock"] > 0,
                "stock_quantity": p["stock"],
                "category": p["category"],
                "agent_eligible": p["agent_eligible"],
            })

        return {
            "catalog_version": store.get("version", "1.0.0"),
            "store": {
                "name": store.get("name"),
                "currency": store.get("currency", "INR"),
                "agent_protocol_version": "2026-03",
                "endpoints": {
                    "catalog": "/.well-known/agent-catalog.json",
                    "cart": "/agent/cart",
                    "discount": "/agent/discount",
                    "upsell": "/agent/upsell",
                    "checkout": "/agent/checkout",
                },
                "store_policies": store.get("policies", {}),
            },
            "products": agent_items,
        }

    def get_product(self, sku: str) -> Optional[Dict[str, Any]]:
        """Finds product by SKU."""
        return self._products_by_sku.get(sku)

    def get_allowed_skus(self) -> List[str]:
        """Returns SKUs that are agent-sale eligible."""
        return [
            p["sku"]
            for p in self._products_by_sku.values()
            if p.get("agent_eligible") is True
        ]

    def is_sku_allowed(self, sku: str) -> bool:
        """Returns whether a given SKU is agent eligible."""
        prod = self.get_product(sku)
        return prod is not None and prod.get("agent_eligible") is True

    def get_coupons(self) -> List[Dict[str, Any]]:
        """Returns all coupons defined in catalog seed."""
        return self._raw_data.get("coupons", [])

    def get_coupon(self, code: str) -> Optional[Dict[str, Any]]:
        """Finds coupon by case-insensitive code."""
        code_upper = code.strip().upper()
        for c in self.get_coupons():
            if c.get("code", "").upper() == code_upper:
                return c
        return None


# Global default catalog instance
_default_catalog_manager: Optional[CatalogManager] = None


def get_catalog_manager(catalog_path: Optional[str] = None) -> CatalogManager:
    """Returns or creates the default CatalogManager singleton."""
    global _default_catalog_manager
    if catalog_path is not None:
        return CatalogManager(catalog_path=catalog_path)
    if _default_catalog_manager is None:
        _default_catalog_manager = CatalogManager()
    return _default_catalog_manager
