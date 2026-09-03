"""
End-to-End Integration Tests for Agent Storefront (Milestone 14).

Covers the complete 11-step agentic commerce journey:
1. Catalog discovery
2. Cart creation & update
3. Valid discount application
4. Expired coupon rejection (SUMMER10 -> COUPON_EXPIRED)
5. Recovery from expired coupon
6. Bounded upsell policy (1 max per session)
7. Spend ceiling rejection (> ₹10,000)
8. Policy-gated checkout
9. Human approval gate (≥ ₹5,000)
10. Mock/Razorpay payment flow & capture
11. Immutable SQLite audit trail verification
"""

import pytest
from backend.app import create_app
from backend.store import get_store
from backend.audit import get_audit_logger


@pytest.fixture
def client(tmp_path):
    """Provides an isolated Flask test client with a private test SQLite audit DB."""
    db_file = str(tmp_path / "integration_audit.db")
    app = create_app({
        "TESTING": True,
        "AUDIT_DB_PATH": db_file,
        "FORCE_MOCK_RAZORPAY": True,
    })
    logger = get_audit_logger(db_file)
    logger.clear()
    with app.test_client() as client:
        get_store().reset_all()
        yield client
        get_store().reset_all()
        logger.clear()


def test_complete_agent_commerce_e2e_flow(client):
    """
    Executes a comprehensive, uninterrupted end-to-end agentic commerce transaction
    covering all 11 milestone requirements in a single multi-step journey.
    """
    session_id = "e2e_session_full_flow"

    # =========================================================================
    # Step 1: Catalog Discovery
    # =========================================================================
    cat_res = client.get("/.well-known/agent-catalog.json")
    assert cat_res.status_code == 200
    catalog = cat_res.get_json()
    assert "store" in catalog
    assert "products" in catalog
    assert len(catalog["products"]) >= 4

    policies = catalog["store"]["store_policies"]
    assert policies["session_spend_ceiling"] == 10000
    assert policies["human_approval_threshold"] == 5000
    assert policies["max_discount_pct"] == 15
    assert policies["max_upsells_per_session"] == 1

    # =========================================================================
    # Step 2: Cart Creation & Update
    # =========================================================================
    # Add 1x EDGE-DEV-KIT-01 (price: 4200)
    add_res = client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )
    assert add_res.status_code == 200
    cart = add_res.get_json()["cart"]
    assert cart["item_count"] == 1
    assert cart["subtotal"] == 4200
    assert cart["total"] == 4200

    # Update item quantity
    upd_res = client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "update", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )
    assert upd_res.status_code == 200

    # =========================================================================
    # Step 3: Valid Discount Application
    # =========================================================================
    disc_res = client.post(
        "/agent/discount",
        json={"session_id": session_id, "coupon_code": "WELCOME10"},
    )
    assert disc_res.status_code == 200
    disc_data = disc_res.get_json()
    assert disc_data["status"] == "applied"
    assert disc_data["discount_pct"] == 10
    assert disc_data["discount_amount"] == 420
    assert disc_data["cart"]["total"] == 3780

    # =========================================================================
    # Step 4: Expired Coupon Rejection (SUMMER10)
    # =========================================================================
    exp_res = client.post(
        "/agent/discount",
        json={"session_id": session_id, "coupon_code": "SUMMER10"},
    )
    assert exp_res.status_code == 200  # Structured 200, not 500
    exp_data = exp_res.get_json()
    assert exp_data["status"] == "rejected"
    assert exp_data["code"] == "COUPON_EXPIRED"
    assert "EXPIRED" in exp_data["reason"].upper()

    # =========================================================================
    # Step 5: Recovery from Expired Coupon
    # =========================================================================
    # Verify cart was not corrupted and retains valid previous state
    # Explicitly remove discount to continue to full-price checkout flow
    rem_res = client.delete(f"/agent/discount?session_id={session_id}")
    assert rem_res.status_code == 200
    rec_cart = rem_res.get_json()["cart"]
    assert rec_cart["discount_amount"] == 0
    assert rec_cart["total"] == 4200
    assert rec_cart["applied_coupon"] is None

    # =========================================================================
    # Step 6: Policy-Bounded Upsell (1 Max Per Session)
    # =========================================================================
    # Add initial upsell: CABLE-USB4-PRO-04 (price: 650)
    upsell_res = client.post(
        "/agent/upsell",
        json={"session_id": session_id, "sku": "CABLE-USB4-PRO-04"},
    )
    assert upsell_res.status_code == 200
    upsell_data = upsell_res.get_json()
    assert upsell_data["status"] == "applied"
    assert upsell_data["cart"]["upsells_count"] == 1
    # Total: 4200 + 650 = 4850
    assert upsell_data["cart"]["total"] == 4850

    # Attempt 2nd upsell in same session: CASE-ALU-COOL-05 (price: 850) -> REJECTED
    upsell2_res = client.post(
        "/agent/upsell",
        json={"session_id": session_id, "sku": "CASE-ALU-COOL-05"},
    )
    assert upsell2_res.status_code == 200
    upsell2_data = upsell2_res.get_json()
    assert upsell2_data["status"] == "rejected"
    assert upsell2_data["code"] == "UPSELL_LIMIT_EXCEEDED"
    assert "Maximum 1 upsell" in upsell2_data["reason"]
    # Cart remains at 4850
    assert upsell2_data["cart"]["total"] == 4850

    # =========================================================================
    # Step 7: Spend Ceiling Rejection (> ₹10,000)
    # =========================================================================
    # Add 2 more EDGE-DEV-KIT-01 boards (3 * 4200 + 650 = 13,250 > 10,000 ceiling)
    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 2},
    )
    # Attempt checkout exceeding ceiling
    chk_ceiling = client.post(
        "/agent/checkout",
        json={"session_id": session_id, "buyer_info": {"agent": "e2e_buyer"}},
    )
    assert chk_ceiling.status_code == 200
    ceiling_data = chk_ceiling.get_json()
    assert ceiling_data["status"] == "rejected"
    assert ceiling_data["code"] == "SPEND_CEILING_EXCEEDED"
    assert "exceeds session spend ceiling" in ceiling_data["reason"]

    # Restore cart to within ceiling: update quantity of EDGE-DEV-KIT-01 back to 1
    # New total: 1 * 4200 + 1 * 650 = 4850
    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "update", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )

    # Now add USB-CORAL-TPU-02 (price: 2800) to bring total to 4850 + 2800 = 7650 (>= 5000)
    # This keeps total <= 10000 ceiling while exercising the human approval gate (>= 5000)
    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "USB-CORAL-TPU-02", "quantity": 1},
    )

    cart_state = client.get(f"/agent/cart?session_id={session_id}").get_json()["cart"]
    order_total = cart_state["total"]
    assert order_total == 7650
    assert 5000 <= order_total <= 10000

    # =========================================================================
    # Step 8: Checkout Policy Check
    # =========================================================================
    chk_res = client.post(
        "/agent/checkout",
        json={"session_id": session_id, "buyer_info": {"agent_id": "ai_buyer_pro"}},
    )
    assert chk_res.status_code == 200
    chk_data = chk_res.get_json()

    # =========================================================================
    # Step 9: Human Approval Gate Handling
    # =========================================================================
    # Order total ₹7,650 >= ₹5,000 threshold requires supervisor approval
    assert chk_data["status"] == "approval_required"
    assert chk_data["code"] == "HUMAN_APPROVAL_REQUIRED"
    assert chk_data["amount"] == 7650

    # Human supervisor grants sign-off via /agent/approval
    app_res = client.post(
        "/agent/approval",
        json={
            "session_id": session_id,
            "decision": "approved",
            "approved_by": "supervisor@merchant-ops.internal",
            "reason": "Quarterly hardware procurement quota verified.",
        },
    )
    assert app_res.status_code == 200
    assert app_res.get_json()["decision"] == "approved"

    # Re-invoke checkout after approval
    chk_app_res = client.post(
        "/agent/checkout",
        json={"session_id": session_id, "buyer_info": {"agent_id": "ai_buyer_pro"}},
    )
    assert chk_app_res.status_code == 200
    chk_app_data = chk_app_res.get_json()
    assert chk_app_data["status"] == "success"
    order_id = chk_app_data["order_id"]
    assert order_id.startswith("order_")
    assert chk_app_data["amount"] == 7650
    assert "razorpay_order" in chk_app_data

    # =========================================================================
    # Step 10: Mock/Razorpay Payment Flow & Settlement
    # =========================================================================
    cap_res = client.post(
        "/agent/payment/capture",
        json={
            "session_id": session_id,
            "order_id": order_id,
            "payment_id": f"pay_mock_{order_id[6:]}",
            "amount": 7650,
        },
    )
    assert cap_res.status_code == 200
    cap_data = cap_res.get_json()
    assert cap_data["status"] == "success"
    assert cap_data["amount"] == 7650
    assert cap_data["order_id"] == order_id
    assert cap_data["payment_id"].startswith("pay_")

    # Verify cart was cleared upon settlement
    cleared_cart = client.get(f"/agent/cart?session_id={session_id}").get_json()["cart"]
    assert cleared_cart["item_count"] == 0
    assert cleared_cart["total"] == 0

    # =========================================================================
    # Step 11: Comprehensive Audit Ledger Verification
    # =========================================================================
    audit_res = client.get(f"/audit?session_id={session_id}&limit=100")
    assert audit_res.status_code == 200
    logs = audit_res.get_json()["audit_trail"]
    assert len(logs) >= 8

    actions = [entry["action"] for entry in logs]
    assert "cart_add" in actions
    assert "cart_update" in actions
    assert "discount_request" in actions
    assert "discount_remove" in actions
    assert "upsell_request" in actions
    assert "checkout" in actions
    assert "human_approval" in actions
    assert "payment_capture" in actions

    # Verify expired coupon rejection was recorded
    disc_logs = [e for e in logs if e["action"] == "discount_request"]
    expired_log = next(e for e in disc_logs if e["policy_result"] == "REJECTED")
    assert "EXPIRED" in expired_log["reason"].upper()

    # Verify spend ceiling rejection was recorded
    ceiling_log = next(e for e in logs if e["action"] == "checkout" and "spend ceiling" in e["reason"])
    assert ceiling_log["policy_result"] == "REJECTED"

    # Verify human approval was recorded
    approval_log = next(e for e in logs if e["action"] == "human_approval")
    assert approval_log["policy_result"] == "ALLOWED"
    assert approval_log["actor"] == "merchant"

    # Verify payment capture was recorded with payment reference
    capture_log = next(e for e in logs if e["action"] == "payment_capture")
    assert capture_log["policy_result"] == "ALLOWED"
    assert capture_log["razorpay_ref"].startswith("pay_")


def test_e2e_human_approval_rejection_blocks_checkout_and_capture(client):
    """
    Test human supervisor rejection branch:
    - High-value order (total >= ₹5,000)
    - Human supervisor explicitly rejects transaction
    - Subsequent checkout and payment attempts are strictly blocked
    """
    session_id = "e2e_session_supervisor_reject"

    # Add 2x EDGE-DEV-KIT-01 (2 * 4200 = ₹8,400 >= ₹5,000 threshold)
    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 2},
    )

    # Checkout triggers approval gate
    chk_res = client.post(
        "/agent/checkout",
        json={"session_id": session_id},
    )
    assert chk_res.get_json()["status"] == "approval_required"

    # Human supervisor rejects order
    app_res = client.post(
        "/agent/approval",
        json={
            "session_id": session_id,
            "decision": "rejected",
            "approved_by": "security_officer@merchant.com",
            "reason": "Suspicious autonomous procurement pattern detected.",
        },
    )
    assert app_res.status_code == 200
    assert app_res.get_json()["decision"] == "rejected"

    # Checkout is blocked
    chk2_res = client.post(
        "/agent/checkout",
        json={"session_id": session_id},
    )
    assert chk2_res.status_code == 200
    chk2_data = chk2_res.get_json()
    assert chk2_data["status"] == "rejected"
    assert chk2_data["code"] == "HUMAN_APPROVAL_REJECTED"

    # Payment capture is blocked
    cap_res = client.post(
        "/agent/payment/capture",
        json={"session_id": session_id, "order_id": "order_fake_123"},
    )
    assert cap_res.status_code == 400
    assert cap_res.get_json()["code"] == "HUMAN_APPROVAL_REJECTED"


def test_e2e_empty_cart_checkout_blocked(client):
    """Test policy gates prevent checkout on empty carts."""
    session_id = "e2e_session_empty_cart"
    chk_res = client.post(
        "/agent/checkout",
        json={"session_id": session_id},
    )
    assert chk_res.status_code == 200
    assert chk_res.get_json()["code"] == "EMPTY_CART"
