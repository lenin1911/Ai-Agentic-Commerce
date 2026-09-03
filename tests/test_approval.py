import pytest
from backend.app import create_app
from backend.store import get_store
from backend.audit import get_audit_logger


@pytest.fixture
def client(tmp_path):
    db_file = str(tmp_path / "test_approval_audit.db")
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


def test_checkout_below_threshold_proceeds_automatically(client):
    """Test order < ₹5,000 (e.g. ₹4,200) proceeds automatically without human approval."""
    session_id = "sess_under_threshold"

    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )

    res = client.post(
        "/agent/checkout",
        json={"session_id": session_id},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert "order_id" in data
    assert data["amount"] == 4200


def test_checkout_at_or_above_threshold_requires_approval(client):
    """Test order >= ₹5,000 (e.g. ₹7,000) pauses checkout and demands human sign-off."""
    session_id = "sess_needs_approval"

    # Edge Dev Kit (4200) + USB Co-Processor (2800) = 7000
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
    assert data["amount"] == 7000
    assert "5000" in data["reason"]
    # Verify no order_id was created
    assert "order_id" not in data

    # Verify audit logged HUMAN_APPROVAL_REQUIRED
    audit_res = client.get(f"/audit?session_id={session_id}")
    entries = audit_res.get_json()["audit_trail"]
    checkout_entry = next(e for e in entries if e["action"] == "checkout")
    assert checkout_entry["policy_result"] == "HUMAN_APPROVAL_REQUIRED"


def test_approved_checkout_completes_order(client):
    """Test human supervisor approves high-value order, allowing checkout to succeed."""
    session_id = "sess_approved_flow"

    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )
    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "USB-CORAL-TPU-02", "quantity": 1},
    )

    # 1. Initial attempt paused
    res1 = client.post("/agent/checkout", json={"session_id": session_id})
    assert res1.get_json()["status"] == "approval_required"

    # 2. Human merchant supervisor signs off
    approval_res = client.post(
        "/agent/approval",
        json={
            "session_id": session_id,
            "decision": "approved",
            "approved_by": "alice_merchant_manager",
            "reason": "Verified enterprise developer order",
        },
    )
    assert approval_res.status_code == 200
    assert approval_res.get_json()["status"] == "success"
    assert approval_res.get_json()["decision"] == "approved"

    # 3. Subsequent checkout now completes successfully
    res2 = client.post("/agent/checkout", json={"session_id": session_id})
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert data2["status"] == "success"
    assert "order_id" in data2
    assert data2["amount"] == 7000

    # 4. Check audit has human approval entry
    audit_res = client.get(f"/audit?session_id={session_id}")
    entries = audit_res.get_json()["audit_trail"]
    approval_entry = next(e for e in entries if e["action"] == "human_approval")
    assert approval_entry["actor"] == "merchant"
    assert approval_entry["policy_result"] == "ALLOWED"


def test_rejected_checkout_blocks_order_and_capture(client):
    """Test human supervisor rejects high-value order, permanently blocking checkout and capture."""
    session_id = "sess_rejected_flow"

    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )
    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "USB-CORAL-TPU-02", "quantity": 1},
    )

    # 1. Supervisor explicitly rejects
    approval_res = client.post(
        "/agent/approval",
        json={
            "session_id": session_id,
            "decision": "rejected",
            "approved_by": "security_officer",
            "reason": "Suspected anomalous automated spike",
        },
    )
    assert approval_res.status_code == 200
    assert approval_res.get_json()["decision"] == "rejected"

    # 2. Checkout is blocked
    checkout_res = client.post("/agent/checkout", json={"session_id": session_id})
    assert checkout_res.status_code == 200
    checkout_data = checkout_res.get_json()
    assert checkout_data["status"] == "rejected"
    assert checkout_data["code"] == "HUMAN_APPROVAL_REJECTED"
    assert "order_id" not in checkout_data

    # 3. Payment capture is also blocked
    capture_res = client.post(
        "/agent/payment/capture",
        json={
            "session_id": session_id,
            "order_id": "fake_order_123",
            "payment_id": "pay_fake_999",
        },
    )
    assert capture_res.status_code == 400
    assert capture_res.get_json()["code"] == "HUMAN_APPROVAL_REJECTED"

    # 4. Audit trail verifies rejection
    audit_res = client.get(f"/audit?session_id={session_id}")
    entries = audit_res.get_json()["audit_trail"]
    actions = [e["action"] for e in entries]
    assert "human_approval" in actions
    approval_audit = next(e for e in entries if e["action"] == "human_approval")
    assert approval_audit["policy_result"] == "REJECTED"
