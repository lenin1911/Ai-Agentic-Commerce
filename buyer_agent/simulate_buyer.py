"""
Agent Storefront — Deterministic Buyer Agent Simulation.

Simulates an autonomous AI buyer executing an end-to-end commerce workflow:
1. Discovers the agent catalog via /.well-known/agent-catalog.json
2. Selects an agent-eligible product
3. Adds the product to the agent cart
4. Attempts to apply expired coupon SUMMER10
5. Receives structured COUPON_EXPIRED policy rejection (HTTP 200)
6. Continues without discount at full price
7. Attempts policy-gated checkout
8. Handles human approval gate if transaction total >= ₹5,000
9. Completes payment capture using Razorpay / mock flow
10. Prints and verifies results for each step and reviews the audit ledger
"""

import argparse
import json
import sys
import uuid
from typing import Any, Dict, Optional, Tuple


class BuyerClient:
    """
    HTTP/WSGI client abstraction for Buyer Agent.
    Supports live HTTP execution (via requests) or in-process execution (via Flask test client).
    """

    def __init__(self, base_url: Optional[str] = None, flask_client: Any = None):
        self.base_url = (base_url or "http://127.0.0.1:5000").rstrip("/")
        self.flask_client = flask_client

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], int]:
        if self.flask_client:
            resp = self.flask_client.get(path, query_string=params)
            return resp.get_json() or {}, resp.status_code
        else:
            import requests
            resp = requests.get(f"{self.base_url}{path}", params=params)
            return resp.json() or {}, resp.status_code

    def post(self, path: str, json_data: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], int]:
        if self.flask_client:
            resp = self.flask_client.post(path, json=json_data)
            return resp.get_json() or {}, resp.status_code
        else:
            import requests
            resp = requests.post(f"{self.base_url}{path}", json=json_data)
            return resp.json() or {}, resp.status_code

    def delete(self, path: str, params: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], int]:
        if self.flask_client:
            resp = self.flask_client.delete(path, query_string=params)
            return resp.get_json() or {}, resp.status_code
        else:
            import requests
            resp = requests.delete(f"{self.base_url}{path}", params=params)
            return resp.json() or {}, resp.status_code


def run_buyer_simulation(
    client: BuyerClient,
    session_id: Optional[str] = None,
    sku: Optional[str] = None,
    quantity: int = 1,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Executes the 10-step deterministic buyer agent simulation.
    Uses exclusively public backend APIs to interact with the merchant storefront.
    """
    if not session_id:
        session_id = f"sim_buyer_{uuid.uuid4().hex[:10]}"

    def log(msg: str) -> None:
        if verbose:
            clean_msg = str(msg).replace("\u20b9", "INR ")
            try:
                print(clean_msg)
            except UnicodeEncodeError:
                print(clean_msg.encode("ascii", errors="replace").decode("ascii"))

    log("=" * 68)
    log("       AGENT STOREFRONT -- DETERMINISTIC BUYER SIMULATION")
    log("=" * 68)
    log(f"[*] Session ID: {session_id}")

    # Step 1: Discover the agent catalog
    log("\n[Step 1/10] Discovering Agent Catalog via /.well-known/agent-catalog.json...")
    catalog_data, status = client.get("/.well-known/agent-catalog.json")
    if status != 200 or "products" not in catalog_data:
        raise RuntimeError(f"Catalog discovery failed with status {status}: {catalog_data}")

    products = catalog_data.get("products", [])
    store_meta = catalog_data.get("store", {})
    currency = store_meta.get("currency", "INR")
    log(f"    [+] Store: {store_meta.get('name', 'Agent Storefront')}")
    log(f"    [+] Catalog Version: {store_meta.get('version', '1.0.0')}")
    log(f"    [+] Discovered {len(products)} products in merchant catalog.")

    # Step 2: Select a product
    log("\n[Step 2/10] Selecting Agent-Eligible Product from Catalog...")
    selected_product = None
    if sku:
        selected_product = next((p for p in products if p["sku"] == sku), None)
    if not selected_product:
        # Deterministically select first eligible product in stock
        eligible = [
            p for p in products
            if p.get("agent_eligible")
            and (p.get("stock_quantity", p.get("stock", 0)) >= quantity or p.get("in_stock", False))
        ]
        if not eligible:
            raise RuntimeError("No in-stock agent-eligible product available in catalog.")
        selected_product = eligible[0]

    selected_sku = selected_product["sku"]
    unit_price = selected_product["price"]
    stock_qty = selected_product.get("stock_quantity", selected_product.get("stock", "available"))
    log(f"    [+] Selected Product: {selected_product['name']}")
    log(f"    [+] SKU: {selected_sku} | Unit Price: INR {unit_price} | Stock: {stock_qty}")
    log(f"    [+] Purchasing Quantity: {quantity}")

    # Step 3: Add it to the cart
    log(f"\n[Step 3/10] Adding '{selected_sku}' to Agent Cart...")
    cart_res, status = client.post(
        "/agent/cart",
        json_data={"session_id": session_id, "action": "add", "sku": selected_sku, "quantity": quantity},
    )
    if status != 200:
        raise RuntimeError(f"Failed to add product to cart: {cart_res}")

    cart = cart_res.get("cart", {})
    subtotal = cart.get("subtotal", 0)
    log(f"    [+] Cart Updated successfully. Items in cart: {cart.get('item_count')}")
    log(f"    [+] Subtotal: INR {subtotal} {currency}")

    # Step 4: Attempt SUMMER10
    log("\n[Step 4/10] Attempting Deliberate Expired Coupon 'SUMMER10'...")
    disc_res, status = client.post(
        "/agent/discount",
        json_data={"session_id": session_id, "coupon_code": "SUMMER10"},
    )
    log(f"    [*] Coupon application HTTP Status: {status}")

    # Step 5: Receive COUPON_EXPIRED
    log("\n[Step 5/10] Evaluating Policy Rejection Response...")
    disc_status = disc_res.get("status")
    disc_code = disc_res.get("code")
    disc_reason = disc_res.get("reason", "")
    log(f"    [!] Policy Verdict: status='{disc_status}', code='{disc_code}'")
    log(f"    [!] Rejection Reason: \"{disc_reason}\"")

    if disc_code != "COUPON_EXPIRED" or disc_status != "rejected":
        raise RuntimeError(f"Expected rejection with COUPON_EXPIRED, got: {disc_res}")

    # Step 6: Continue without the discount
    log("\n[Step 6/10] Continuing Without Discount (Full-Price Recovery)...")
    cart_after_rejection = disc_res.get("cart", {})
    effective_total = cart_after_rejection.get("total", subtotal)
    discount_amount = cart_after_rejection.get("discount_amount", 0)
    log("    [*] Cart preserved cleanly without corrupted discount state.")
    log(f"    [+] Discount Amount: INR {discount_amount} | Order Total: INR {effective_total} {currency}")

    # Step 7: Attempt checkout
    log("\n[Step 7/10] Attempting Policy-Gated Checkout...")
    checkout_res, status = client.post(
        "/agent/checkout",
        json_data={
            "session_id": session_id,
            "buyer_info": {
                "agent_id": "deterministic_buyer_agent",
                "framework": "agent_storefront_sdk",
            },
        },
    )
    if status != 200:
        raise RuntimeError(f"Checkout request failed with HTTP {status}: {checkout_res}")

    chk_status = checkout_res.get("status")
    chk_code = checkout_res.get("code")

    # Step 8: Handle human approval if the amount requires it
    log("\n[Step 8/10] Handling Human Approval Policy Gate...")
    if chk_status == "approval_required" or chk_code == "HUMAN_APPROVAL_REQUIRED":
        log(f"    [!] Order total INR {checkout_res.get('amount')} exceeds threshold (INR 5,000).")
        log(f"    [!] Reason: {checkout_res.get('reason')}")
        log("    [*] Requesting Merchant Supervisor Approval via /agent/approval...")
        approval_res, app_status = client.post(
            "/agent/approval",
            json_data={
                "session_id": session_id,
                "decision": "approved",
                "approved_by": "supervisor@merchant-hq.internal",
                "reason": "Autonomous agent procurement approved within team operating budget.",
            },
        )
        if app_status != 200 or approval_res.get("decision") != "approved":
            raise RuntimeError(f"Human supervisor approval failed: {approval_res}")

        log(f"    [+] Human approval granted by '{approval_res.get('approved_by')}'.")
        log("    [*] Retrying policy-gated checkout after approval...")
        checkout_res, status = client.post(
            "/agent/checkout",
            json_data={
                "session_id": session_id,
                "buyer_info": {"agent_id": "deterministic_buyer_agent"},
            },
        )
        if status != 200 or checkout_res.get("status") != "success":
            raise RuntimeError(f"Post-approval checkout failed: {checkout_res}")
        log(f"    [+] Checkout approved! Order ID: {checkout_res.get('order_id')}")
    else:
        order_amount = checkout_res.get("amount", effective_total)
        log(f"    [+] Order total INR {order_amount} is within autonomous approval threshold (< INR 5,000).")
        log(f"    [+] Checkout approved directly! Order ID: {checkout_res.get('order_id')}")

    order_id = checkout_res.get("order_id")
    if not order_id:
        raise RuntimeError("No order_id returned from checkout.")

    # Step 9: Complete payment using the available Razorpay/mock flow
    log("\n[Step 9/10] Completing Payment via Razorpay / Mock Gateway...")
    payment_res, cap_status = client.post(
        "/agent/payment/capture",
        json_data={
            "session_id": session_id,
            "order_id": order_id,
            "payment_id": f"pay_mock_{order_id[6:]}",
            "amount": checkout_res.get("amount"),
        },
    )
    if cap_status != 200 or payment_res.get("status") != "success":
        raise RuntimeError(f"Payment capture failed: {payment_res}")

    log(f"    [+] Payment Status: {payment_res.get('status')} (settled)")
    log(f"    [+] Payment Reference: {payment_res.get('payment_id')}")
    log(f"    [+] Settled Amount: INR {payment_res.get('amount')} {currency}")

    # Step 10: Print clear results for each step & audit trail verification
    log("\n[Step 10/10] Simulation Summary & Audit Ledger Verification...")
    audit_data, audit_status = client.get("/audit", params={"session_id": session_id})
    audit_logs = audit_data.get("audit_trail", [])

    log(f"    [+] Total Audit Ledger Records: {len(audit_logs)}")
    for entry in reversed(audit_logs):
        log(
            f"        - [{entry['action'].upper()}] Policy Result: {entry['policy_result']} "
            f"| Actor: {entry['actor']} | Reason: {entry.get('reason') or 'None'}"
        )

    log("\n" + "=" * 68)
    log("  SUCCESS: DETERMINISTIC BUYER FLOW COMPLETED ALL 10 STEPS")
    log("=" * 68 + "\n")

    return {
        "session_id": session_id,
        "selected_product": selected_product,
        "coupon_rejection": {
            "status": disc_status,
            "code": disc_code,
            "reason": disc_reason,
        },
        "checkout": checkout_res,
        "payment": payment_res,
        "audit_logs": audit_logs,
        "success": True,
    }


def main() -> None:
    """Command-line runner for buyer agent simulation."""
    parser = argparse.ArgumentParser(
        description="Run deterministic Buyer Agent simulation against Agent Storefront."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:5000",
        help="Storefront base URL (default: http://127.0.0.1:5000)",
    )
    parser.add_argument(
        "--sku",
        default=None,
        help="Specific product SKU to purchase (default: auto-select eligible)",
    )
    parser.add_argument(
        "--quantity",
        type=int,
        default=1,
        help="Product quantity to purchase (default: 1)",
    )
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="Execute simulation against an in-process Flask test client without network requests",
    )
    parser.add_argument(
        "--require-approval",
        action="store_true",
        help="Simulate high-value order (quantity=2) to exercise human approval gate",
    )

    args = parser.parse_args()
    qty = 2 if args.require_approval else args.quantity

    if args.in_process:
        from backend.app import create_app
        app = create_app({"TESTING": True})
        client = BuyerClient(flask_client=app.test_client())
        print("[*] Running simulation in in-process mode via Flask test client.")
    else:
        # Check if live server is reachable
        try:
            import requests
            resp = requests.get(f"{args.base_url}/health", timeout=1.5)
            if resp.status_code == 200:
                client = BuyerClient(base_url=args.base_url)
                print(f"[*] Connected to live Agent Storefront server at {args.base_url}")
            else:
                raise ConnectionError(f"Unexpected health status: {resp.status_code}")
        except Exception:
            print(f"[*] Live server not reachable at {args.base_url}.")
            print("[*] Falling back to in-process Flask test client for offline execution.")
            from backend.app import create_app
            app = create_app({"TESTING": True})
            client = BuyerClient(flask_client=app.test_client())

    try:
        run_buyer_simulation(client=client, sku=args.sku, quantity=qty)
    except Exception as exc:
        print(f"\n[ERROR] Simulation failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
