import pytest
from backend.app import create_app
from backend.store import get_store
from backend.audit import get_audit_logger


@pytest.fixture
def client(tmp_path):
    db_file = str(tmp_path / "test_checkout_audit.db")
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


def test_checkout_empty_cart_rejected(client):
    """Test checkout with an empty cart is rejected and audited."""
    session_id = "test_empty_checkout"

    res = client.post(
        "/agent/checkout",
        json={"session_id": session_id},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "rejected"
    assert data["code"] == "EMPTY_CART"

    # Verify audit trail
    audit_res = client.get(f"/audit?session_id={session_id}")
    entries = audit_res.get_json()["audit_trail"]
    assert len(entries) == 1
    assert entries[0]["action"] == "checkout"
    assert entries[0]["policy_result"] == "REJECTED"


def test_checkout_successful_autonomous(client):
    """Test valid order <= ₹5,000 passes autonomous checkout and creates order ref."""
    session_id = "test_auto_checkout"

    # Add Edge Dev Kit (4200 <= 5000)
    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )

    res = client.post(
        "/agent/checkout",
        json={
            "session_id": session_id,
            "buyer_info": {"agent": "TestBuyerAgent", "budget": 5000},
        },
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert "order_id" in data
    assert data["order_id"].startswith("order_")
    assert data["amount"] == 4200
    assert data["currency"] == "INR"

    # Verify audit
    audit_res = client.get(f"/audit?session_id={session_id}")
    entries = audit_res.get_json()["audit_trail"]
    checkout_entry = next(e for e in entries if e["action"] == "checkout")
    assert checkout_entry["policy_result"] == "ALLOWED"
    assert checkout_entry["razorpay_ref"] == data["order_id"]


def test_checkout_human_approval_required(client):
    """Test order > ₹5,000 requires human approval sign-off."""
    session_id = "test_approval_checkout"

    # Add Edge Dev Kit (4200) + USB Co-Processor (2800) = 7000 (> 5000, <= 10000)
    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )
    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "USB-CORAL-TPU-02", "quantity": 1},
    )

    res = client.post(
        "/agent/checkout",
        json={"session_id": session_id},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "approval_required"
    assert data["code"] == "HUMAN_APPROVAL_REQUIRED"
    assert "5000" in data["reason"]
    assert data["amount"] == 7000

    # Verify audit logged HUMAN_APPROVAL_REQUIRED
    audit_res = client.get(f"/audit?session_id={session_id}")
    entries = audit_res.get_json()["audit_trail"]
    checkout_entry = next(e for e in entries if e["action"] == "checkout")
    assert checkout_entry["policy_result"] == "HUMAN_APPROVAL_REQUIRED"


def test_checkout_spend_ceiling_exceeded(client):
    """Test order > ₹10,000 spend ceiling is rejected completely."""
    session_id = "test_ceiling_checkout"

    # Add 3 Edge Dev Kits (4200 * 3 = 12600 > 10000)
    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 3},
    )

    res = client.post(
        "/agent/checkout",
        json={"session_id": session_id},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "rejected"
    assert data["code"] == "SPEND_CEILING_EXCEEDED"
    assert "10000" in data["reason"]

    # Verify audit
    audit_res = client.get(f"/audit?session_id={session_id}")
    entries = audit_res.get_json()["audit_trail"]
    checkout_entry = next(e for e in entries if e["action"] == "checkout")
    assert checkout_entry["policy_result"] == "REJECTED"
