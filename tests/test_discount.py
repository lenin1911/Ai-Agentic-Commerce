import pytest
from backend.app import create_app
from backend.store import get_store


from backend.audit import get_audit_logger


@pytest.fixture
def client(tmp_path):
    db_file = str(tmp_path / "test_discount_audit.db")
    app = create_app({
        "TESTING": True,
        "AUDIT_DB_PATH": db_file,
    })
    logger = get_audit_logger(db_file)
    logger.clear()
    with app.test_client() as client:
        get_store().reset_all()
        yield client
        get_store().reset_all()
        logger.clear()


def test_valid_coupon_discount_applied(client):
    """Test applying valid coupon WELCOME10 reduces total by 10% within 15% limit."""
    session_id = "test_discount_valid"

    # Add item: EDGE-DEV-KIT-01 (price: 4200)
    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )

    # Apply WELCOME10 (10% discount)
    res = client.post(
        "/agent/discount",
        json={"session_id": session_id, "coupon_code": "WELCOME10"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "applied"
    assert data["coupon_code"] == "WELCOME10"
    assert data["discount_pct"] == 10
    assert data["discount_amount"] == 420

    cart = data["cart"]
    assert cart["subtotal"] == 4200
    assert cart["discount_amount"] == 420
    assert cart["total"] == 3780
    assert cart["applied_coupon"]["code"] == "WELCOME10"


def test_expired_coupon_rejected(client):
    """Test expired coupon SUMMER10 is rejected with code COUPON_EXPIRED without 500 error."""
    session_id = "test_discount_expired"

    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )

    res = client.post(
        "/agent/discount",
        json={"session_id": session_id, "coupon_code": "SUMMER10"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "rejected"
    assert data["code"] == "COUPON_EXPIRED"
    assert "SUMMER10" in data["reason"].upper() and "EXPIRED" in data["reason"].upper()

    # Verify cart was not modified
    cart = data["cart"]
    assert cart["subtotal"] == 4200
    assert cart["discount_amount"] == 0
    assert cart["total"] == 4200
    assert cart["applied_coupon"] is None


def test_expired_coupon_recovery_ignore_and_full_price_checkout(client):
    """
    Test deliberate failure/recovery scenario (Milestone 11):
    1. Buyer adds product to cart.
    2. Buyer attempts to apply expired coupon SUMMER10.
    3. Policy engine rejects with 200 OK and code: COUPON_EXPIRED.
    4. Buyer ignores the rejection and continues to full-price checkout.
    5. Checkout succeeds and payment is captured.
    6. Audit trail records both the coupon rejection and successful continuation.
    """
    session_id = "test_recovery_ignore"

    # 1. Add item: EDGE-DEV-KIT-01 (price: 4200)
    add_res = client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )
    assert add_res.status_code == 200

    # 2. Attempt expired coupon SUMMER10
    disc_res = client.post(
        "/agent/discount",
        json={"session_id": session_id, "coupon_code": "SUMMER10"},
    )
    assert disc_res.status_code == 200
    disc_data = disc_res.get_json()
    assert disc_data["status"] == "rejected"
    assert disc_data["code"] == "COUPON_EXPIRED"
    assert "EXPIRED" in disc_data["reason"].upper()

    # 3. Verify cart state is intact and total is full price
    cart = disc_data["cart"]
    assert cart["subtotal"] == 4200
    assert cart["discount_amount"] == 0
    assert cart["total"] == 4200
    assert cart["applied_coupon"] is None

    # 4. Continue to checkout at full price without discount
    chk_res = client.post(
        "/agent/checkout",
        json={"session_id": session_id, "buyer_info": {"agent_id": "buyer_agent_01"}},
    )
    assert chk_res.status_code == 200
    chk_data = chk_res.get_json()
    assert chk_data["status"] == "success"
    assert chk_data["amount"] == 4200
    order_id = chk_data["order_id"]
    assert order_id.startswith("order_")

    # 5. Capture payment at full price
    cap_res = client.post(
        "/agent/payment/capture",
        json={
            "session_id": session_id,
            "order_id": order_id,
            "payment_id": "pay_mock_recovery_01",
            "amount": 4200,
        },
    )
    assert cap_res.status_code == 200
    cap_data = cap_res.get_json()
    assert cap_data["status"] == "success"
    assert cap_data["amount"] == 4200

    # 6. Verify audit trail records both rejection and successful continuation
    audit_res = client.get(f"/audit?session_id={session_id}")
    assert audit_res.status_code == 200
    logs = audit_res.get_json()["audit_trail"]
    actions = [entry["action"] for entry in logs]
    assert "cart_add" in actions
    assert "discount_request" in actions
    assert "checkout" in actions
    assert "payment_capture" in actions

    # Verify rejection entry
    disc_log = next(entry for entry in logs if entry["action"] == "discount_request")
    assert disc_log["policy_result"] == "REJECTED"
    assert "EXPIRED" in disc_log["reason"].upper()

    # Verify checkout entry (successful full-price continuation)
    chk_log = next(entry for entry in logs if entry["action"] == "checkout")
    assert chk_log["policy_result"] == "ALLOWED"
    assert chk_log["razorpay_ref"] == order_id


def test_expired_coupon_recovery_explicit_remove_and_checkout(client):
    """
    Test deliberate failure/recovery scenario with explicit discount removal:
    1. Buyer adds product to cart.
    2. Buyer attempts SUMMER10 -> receives COUPON_EXPIRED.
    3. Buyer explicitly removes discount via DELETE /agent/discount.
    4. Full-price checkout succeeds.
    5. Audit trail records rejection, discount removal, and checkout.
    """
    session_id = "test_recovery_remove"

    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )

    # Attempt expired coupon
    disc_res = client.post(
        "/agent/discount",
        json={"session_id": session_id, "coupon_code": "SUMMER10"},
    )
    assert disc_res.status_code == 200
    assert disc_res.get_json()["code"] == "COUPON_EXPIRED"

    # Explicitly remove discount
    rem_res = client.delete(f"/agent/discount?session_id={session_id}")
    assert rem_res.status_code == 200
    assert rem_res.get_json()["status"] == "removed"
    assert rem_res.get_json()["cart"]["total"] == 4200

    # Checkout at full price
    chk_res = client.post(
        "/agent/checkout",
        json={"session_id": session_id},
    )
    assert chk_res.status_code == 200
    assert chk_res.get_json()["amount"] == 4200

    # Audit records all events (newest first)
    audit_res = client.get(f"/audit?session_id={session_id}")
    logs = audit_res.get_json()["audit_trail"]
    actions = [entry["action"] for entry in logs]
    assert actions == ["checkout", "discount_remove", "discount_request", "cart_add"]


def test_invalid_coupon_rejected(client):
    """Test non-existent coupon code is rejected cleanly."""
    session_id = "test_discount_fake"

    res = client.post(
        "/agent/discount",
        json={"session_id": session_id, "coupon_code": "NOT_A_REAL_COUPON"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "rejected"
    assert data["code"] == "COUPON_NOT_FOUND"


def test_excessive_discount_rejected(client):
    """Test coupon EXCESSIVE50 offering 50% (> 15% limit) is rejected."""
    session_id = "test_discount_excessive"

    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )

    res = client.post(
        "/agent/discount",
        json={"session_id": session_id, "coupon_code": "EXCESSIVE50"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "rejected"
    assert data["code"] == "DISCOUNT_EXCEEDS_POLICY_MAX"
    assert "15%" in data["reason"]

    # Cart unchanged
    assert data["cart"]["total"] == 4200


def test_remove_discount(client):
    """Test removing an applied discount restores full price."""
    session_id = "test_discount_remove"

    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )
    client.post(
        "/agent/discount",
        json={"session_id": session_id, "coupon_code": "WELCOME10"},
    )

    # Remove discount
    res = client.post(
        "/agent/discount",
        json={"session_id": session_id, "action": "remove"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "removed"
    assert data["cart"]["discount_amount"] == 0
    assert data["cart"]["total"] == 4200
    assert data["cart"]["applied_coupon"] is None
