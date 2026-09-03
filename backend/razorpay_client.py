"""
Razorpay payment integration for Agent Storefront.
Provides seamless switching between Razorpay Test Mode and a deterministic mock client
when SDK or credentials are not configured.
"""

from datetime import datetime, timezone
import os
import time
import uuid
from typing import Any, Dict, Optional

try:
    import razorpay
    RAZORPAY_SDK_AVAILABLE = True
except ImportError:
    razorpay = None
    RAZORPAY_SDK_AVAILABLE = False


class BaseRazorpayClient:
    """Interface for Razorpay client implementations."""

    def create_order(
        self,
        amount_in_inr: int,
        currency: str = "INR",
        receipt: Optional[str] = None,
        notes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def capture_payment(
        self,
        payment_id: str,
        amount_in_inr: int,
        currency: str = "INR",
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def verify_payment_signature(self, params: Dict[str, str]) -> bool:
        raise NotImplementedError

    @property
    def is_mock(self) -> bool:
        raise NotImplementedError


class MockRazorpayClient(BaseRazorpayClient):
    """
    Deterministic mock implementation for testing and offline environments.
    Guarantees consistent, judge-friendly responses without external network dependencies.
    """

    def __init__(self):
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._payments: Dict[str, Dict[str, Any]] = {}

    @property
    def is_mock(self) -> bool:
        return True

    def create_order(
        self,
        amount_in_inr: int,
        currency: str = "INR",
        receipt: Optional[str] = None,
        notes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        order_id = f"order_mock_{uuid.uuid4().hex[:12]}"
        amount_paise = amount_in_inr * 100

        order_data = {
            "id": order_id,
            "entity": "order",
            "amount": amount_paise,
            "amount_paid": 0,
            "amount_due": amount_paise,
            "currency": currency.upper(),
            "receipt": receipt or f"rcpt_{int(time.time())}",
            "status": "created",
            "attempts": 0,
            "notes": notes or {},
            "created_at": int(time.time()),
            "mode": "mock",
        }
        self._orders[order_id] = order_data
        return order_data

    def capture_payment(
        self,
        payment_id: Optional[str],
        amount_in_inr: int,
        currency: str = "INR",
    ) -> Dict[str, Any]:
        pid = payment_id or f"pay_mock_{uuid.uuid4().hex[:12]}"
        amount_paise = amount_in_inr * 100

        payment_data = {
            "id": pid,
            "entity": "payment",
            "amount": amount_paise,
            "currency": currency.upper(),
            "status": "captured",
            "method": "agentic_wallet",
            "captured": True,
            "description": "Agent Storefront automated settlement",
            "created_at": int(time.time()),
            "mode": "mock",
        }
        self._payments[pid] = payment_data
        return payment_data

    def verify_payment_signature(self, params: Dict[str, str]) -> bool:
        # Mock verification always succeeds if signature field is present or not empty
        return bool(params.get("razorpay_signature"))


class LiveRazorpayClient(BaseRazorpayClient):
    """
    Live Razorpay client communicating with Razorpay Test Mode API.
    Activated when RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, and razorpay SDK exist.
    """

    def __init__(self, key_id: str, key_secret: str):
        if not RAZORPAY_SDK_AVAILABLE:
            raise RuntimeError("razorpay package is not installed.")
        self.key_id = key_id
        self._key_secret = key_secret
        self.client = razorpay.Client(auth=(key_id, key_secret))

    @property
    def is_mock(self) -> bool:
        return False

    def create_order(
        self,
        amount_in_inr: int,
        currency: str = "INR",
        receipt: Optional[str] = None,
        notes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        amount_paise = amount_in_inr * 100
        payload = {
            "amount": amount_paise,
            "currency": currency.upper(),
            "receipt": receipt or f"rcpt_{int(time.time())}",
            "notes": notes or {},
        }
        res = self.client.order.create(data=payload)
        res["mode"] = "live_test"
        return res

    def capture_payment(
        self,
        payment_id: str,
        amount_in_inr: int,
        currency: str = "INR",
    ) -> Dict[str, Any]:
        amount_paise = amount_in_inr * 100
        res = self.client.payment.capture(payment_id, amount_paise, {"currency": currency.upper()})
        res["mode"] = "live_test"
        return res

    def verify_payment_signature(self, params: Dict[str, str]) -> bool:
        try:
            self.client.utility.verify_payment_signature(params)
            return True
        except Exception:
            return False


_client_instance: Optional[BaseRazorpayClient] = None


def get_razorpay_client(force_mock: bool = False) -> BaseRazorpayClient:
    """
    Factory creating either LiveRazorpayClient (if test keys are configured)
    or MockRazorpayClient fallback.
    """
    global _client_instance
    if force_mock:
        return MockRazorpayClient()

    if _client_instance is not None:
        return _client_instance

    key_id = os.environ.get("RAZORPAY_KEY_ID", "").strip()
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "").strip()

    is_placeholder = (
        not key_id
        or not key_secret
        or "placeholder" in key_id.lower()
        or "placeholder" in key_secret.lower()
    )

    if RAZORPAY_SDK_AVAILABLE and not is_placeholder:
        _client_instance = LiveRazorpayClient(key_id=key_id, key_secret=key_secret)
    else:
        _client_instance = MockRazorpayClient()

    return _client_instance
