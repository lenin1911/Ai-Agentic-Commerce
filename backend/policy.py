"""
Policy engine for Agent Storefront.
Enforces merchant commerce guardrails, discount limits, spend ceilings,
human approval gates, upsell bounds, and SKU eligibility.
"""

from dataclasses import dataclass
from datetime import datetime, date
import os
from typing import Any, Dict, Optional
from backend.catalog import CatalogManager, get_catalog_manager

# Configurable policy constants with strict defaults
MAX_DISCOUNT_PCT: int = int(os.environ.get("MAX_DISCOUNT_PCT", 15))
MAX_UPSELLS_PER_SESSION: int = int(os.environ.get("MAX_UPSELLS_PER_SESSION", 1))
SESSION_SPEND_CEILING: int = int(os.environ.get("SESSION_SPEND_CEILING", 10000))
HUMAN_APPROVAL_THRESHOLD: int = int(os.environ.get("HUMAN_APPROVAL_THRESHOLD", 5000))


@dataclass(frozen=True)
class PolicyResult:
    """Structured result returned by all policy checks."""
    allowed: bool
    reason: str
    code: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "code": self.code,
        }


class PolicyEngine:
    """Server-side policy validation engine."""

    def __init__(
        self,
        catalog_mgr: Optional[CatalogManager] = None,
        max_discount_pct: int = MAX_DISCOUNT_PCT,
        max_upsells_per_session: int = MAX_UPSELLS_PER_SESSION,
        session_spend_ceiling: int = SESSION_SPEND_CEILING,
        human_approval_threshold: int = HUMAN_APPROVAL_THRESHOLD,
    ):
        self.catalog_mgr = catalog_mgr or get_catalog_manager()
        self.max_discount_pct = max_discount_pct
        self.max_upsells_per_session = max_upsells_per_session
        self.session_spend_ceiling = session_spend_ceiling
        self.human_approval_threshold = human_approval_threshold

    def validate_sku(self, sku: str) -> PolicyResult:
        """Validates that a SKU exists, is in stock, and is agent-eligible."""
        if not sku or not isinstance(sku, str):
            return PolicyResult(
                allowed=False,
                reason="SKU must be a non-empty string.",
                code="INVALID_SKU_INPUT",
            )

        product = self.catalog_mgr.get_product(sku)
        if not product:
            return PolicyResult(
                allowed=False,
                reason=f"SKU '{sku}' not found in merchant catalog.",
                code="SKU_NOT_FOUND",
            )

        if not product.get("agent_eligible", False):
            return PolicyResult(
                allowed=False,
                reason=f"Product '{sku}' is restricted from autonomous agent purchasing.",
                code="SKU_NOT_ELIGIBLE",
            )

        if product.get("stock", 0) <= 0:
            return PolicyResult(
                allowed=False,
                reason=f"Product '{sku}' is currently out of stock.",
                code="OUT_OF_STOCK",
            )

        return PolicyResult(
            allowed=True,
            reason=f"SKU '{sku}' is verified and eligible.",
            code="SKU_ALLOWED",
        )

    def validate_coupon(self, coupon_code: str, reference_date: Optional[date] = None) -> PolicyResult:
        """
        Validates coupon existence, active state, expiration date,
        and maximum discount percentage boundary (<= 15%).
        """
        if not coupon_code or not isinstance(coupon_code, str):
            return PolicyResult(
                allowed=False,
                reason="Coupon code must be a non-empty string.",
                code="INVALID_COUPON_INPUT",
            )

        clean_code = coupon_code.strip().upper()
        coupon = self.catalog_mgr.get_coupon(clean_code)

        if not coupon:
            return PolicyResult(
                allowed=False,
                reason=f"Coupon '{coupon_code}' does not exist.",
                code="COUPON_NOT_FOUND",
            )

        # Check expiration date first
        expires_at_str = coupon.get("expires_at")
        if expires_at_str:
            try:
                expires_at = datetime.strptime(expires_at_str, "%Y-%m-%d").date()
                today = reference_date or date.today()
                if today > expires_at:
                    return PolicyResult(
                        allowed=False,
                        reason=f"Coupon '{clean_code}' expired on {expires_at_str}.",
                        code="COUPON_EXPIRED",
                    )
            except ValueError:
                pass

        # Check explicit active flag
        if not coupon.get("active", True):
            reason = coupon.get("reason") or f"coupon {clean_code} is inactive"
            return PolicyResult(
                allowed=False,
                reason=reason,
                code="COUPON_INACTIVE",
            )

        # Check maximum discount percentage ceiling
        discount_pct = coupon.get("discount_pct", 0)
        if discount_pct > self.max_discount_pct:
            return PolicyResult(
                allowed=False,
                reason=f"Requested discount {discount_pct}% exceeds policy ceiling of {self.max_discount_pct}%.",
                code="DISCOUNT_EXCEEDS_POLICY_MAX",
            )

        if discount_pct <= 0:
            return PolicyResult(
                allowed=False,
                reason="Coupon discount percentage must be greater than 0%.",
                code="INVALID_DISCOUNT_VALUE",
            )

        return PolicyResult(
            allowed=True,
            reason=f"Coupon '{clean_code}' approved for {discount_pct}% discount.",
            code="COUPON_VALID",
        )

    def validate_upsell(
        self,
        current_upsells_count: int,
        upsell_sku: str,
        current_total: int,
        upsell_price: Optional[int] = None,
    ) -> PolicyResult:
        """
        Validates upsell bounding:
        - Must not exceed MAX_UPSELLS_PER_SESSION (1)
        - Upsell SKU must be valid and agent eligible
        - New total must not exceed SESSION_SPEND_CEILING (10000)
        """
        if current_upsells_count >= self.max_upsells_per_session:
            return PolicyResult(
                allowed=False,
                reason=f"Upsell limit reached: Maximum {self.max_upsells_per_session} upsell per session permitted.",
                code="UPSELL_LIMIT_EXCEEDED",
            )

        sku_result = self.validate_sku(upsell_sku)
        if not sku_result.allowed:
            return sku_result

        # Lookup price if not explicitly provided
        if upsell_price is None:
            product = self.catalog_mgr.get_product(upsell_sku)
            upsell_price = product["price"] if product else 0

        projected_total = current_total + upsell_price
        if projected_total > self.session_spend_ceiling:
            return PolicyResult(
                allowed=False,
                reason=f"Adding upsell would result in total ₹{projected_total}, which exceeds the session spend ceiling of ₹{self.session_spend_ceiling}.",
                code="SPEND_CEILING_EXCEEDED",
            )

        return PolicyResult(
            allowed=True,
            reason="Upsell verified and allowed within policy parameters.",
            code="UPSELL_ALLOWED",
        )

    def check_spend_ceiling(self, amount: int) -> PolicyResult:
        """Validates that transaction amount does not exceed the absolute session spend ceiling."""
        if amount > self.session_spend_ceiling:
            return PolicyResult(
                allowed=False,
                reason=f"Amount ₹{amount} exceeds session spend ceiling of ₹{self.session_spend_ceiling}.",
                code="SPEND_CEILING_EXCEEDED",
            )
        return PolicyResult(
            allowed=True,
            reason=f"Amount ₹{amount} is within session spend ceiling.",
            code="WITHIN_SPEND_CEILING",
        )

    def check_human_approval(self, amount: int, human_approved: bool = False) -> PolicyResult:
        """
        Determines whether a transaction requires explicit human approval sign-off (>= ₹5,000).
        If human_approved is True, returns approval confirmed.
        """
        if human_approved:
            return PolicyResult(
                allowed=True,
                reason="Transaction verified and explicitly signed off by human supervisor.",
                code="HUMAN_APPROVAL_GRANTED",
            )

        if amount >= self.human_approval_threshold:
            return PolicyResult(
                allowed=False,
                reason=f"Order total ₹{amount} meets or exceeds human approval threshold of ₹{self.human_approval_threshold}.",
                code="HUMAN_APPROVAL_REQUIRED",
            )
        return PolicyResult(
            allowed=True,
            reason="Transaction amount is within autonomous approval threshold.",
            code="AUTOMATIC_APPROVAL",
        )


# Global singleton
_default_policy_engine: Optional[PolicyEngine] = None


def get_policy_engine(catalog_mgr: Optional[CatalogManager] = None) -> PolicyEngine:
    global _default_policy_engine
    if _default_policy_engine is None:
        _default_policy_engine = PolicyEngine(catalog_mgr=catalog_mgr)
    return _default_policy_engine
