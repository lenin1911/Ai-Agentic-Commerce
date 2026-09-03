import pytest
from backend.app import create_app
from backend.store import get_store


@pytest.fixture
def client():
    app = create_app({"TESTING": True})
    with app.test_client() as client:
        get_store().reset_all()
        yield client
        get_store().reset_all()


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
    """Test expired coupon SUMMER10 is rejected without 500 error."""
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
    assert data["code"] in ["COUPON_EXPIRED", "COUPON_INACTIVE"]
    assert "SUMMER10" in data["reason"].upper() or "EXPIRED" in data["reason"].upper()

    # Verify cart was not modified
    cart = data["cart"]
    assert cart["subtotal"] == 4200
    assert cart["discount_amount"] == 0
    assert cart["total"] == 4200
    assert cart["applied_coupon"] is None


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
