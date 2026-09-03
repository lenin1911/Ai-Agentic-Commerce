import pytest
from backend.app import create_app
from backend.store import get_store
from backend.audit import get_audit_logger, AuditLogger


@pytest.fixture
def client(tmp_path):
    db_file = str(tmp_path / "test_audit.db")
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


def test_audit_logger_direct_insert(tmp_path):
    """Test direct audit logger database insertion and querying."""
    db_file = str(tmp_path / "direct_test_audit.db")
    logger = AuditLogger(db_file)
    row_id = logger.log(
        session_id="sess_direct_01",
        actor="buyer_agent",
        action="test_action",
        payload_summary={"key": "val"},
        policy_result="ALLOWED",
        reason="Test reason",
        razorpay_ref="order_test_123",
    )
    assert row_id > 0
    entries = logger.get_entries(session_id="sess_direct_01")
    assert len(entries) == 1
    assert entries[0]["session_id"] == "sess_direct_01"
    assert entries[0]["action"] == "test_action"
    assert entries[0]["policy_result"] == "ALLOWED"
    assert entries[0]["razorpay_ref"] == "order_test_123"


def test_cart_operations_generate_audit_trail(client):
    """Test cart additions, updates, and invalid attempts write to audit log."""
    session_id = "test_audit_cart_sess"

    # Add item
    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )
    # Attempt invalid SKU
    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "INVALID_SKU_TEST", "quantity": 1},
    )

    res = client.get(f"/audit?session_id={session_id}")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    entries = data["audit_trail"]
    assert len(entries) == 2

    # Newest first
    rejected_entry = entries[0]
    assert rejected_entry["policy_result"] == "REJECTED"
    assert "INVALID_SKU" in rejected_entry["reason"]

    allowed_entry = entries[1]
    assert allowed_entry["policy_result"] == "ALLOWED"
    assert allowed_entry["action"] == "cart_add"


def test_discount_operations_generate_audit_trail(client):
    """Test valid and expired coupon attempts write audit records."""
    session_id = "test_audit_disc_sess"

    # Add item
    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )

    # Attempt expired coupon SUMMER10
    client.post(
        "/agent/discount",
        json={"session_id": session_id, "coupon_code": "SUMMER10"},
    )

    # Apply valid coupon WELCOME10
    client.post(
        "/agent/discount",
        json={"session_id": session_id, "coupon_code": "WELCOME10"},
    )

    res = client.get(f"/audit?session_id={session_id}")
    assert res.status_code == 200
    entries = res.get_json()["audit_trail"]

    # Filter discount actions
    disc_entries = [e for e in entries if e["action"] == "discount_request"]
    assert len(disc_entries) == 2

    # Most recent is allowed
    assert disc_entries[0]["policy_result"] == "ALLOWED"
    # Older is rejected
    assert disc_entries[1]["policy_result"] == "REJECTED"
    assert "SUMMER10" in disc_entries[1]["reason"].upper() or "EXPIRED" in disc_entries[1]["reason"].upper()


def test_upsell_operations_generate_audit_trail(client):
    """Test upsell attempts write audit records for allowed and limit-exceeded."""
    session_id = "test_audit_upsell_sess"

    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )

    # First upsell (allowed)
    client.post(
        "/agent/upsell",
        json={"session_id": session_id, "sku": "CABLE-USB4-PRO-04"},
    )

    # Second upsell (rejected by policy limit)
    client.post(
        "/agent/upsell",
        json={"session_id": session_id, "sku": "CASE-ALU-COOL-05"},
    )

    res = client.get(f"/audit?session_id={session_id}")
    entries = res.get_json()["audit_trail"]
    upsell_entries = [e for e in entries if e["action"] == "upsell_request"]
    assert len(upsell_entries) == 2

    assert upsell_entries[0]["policy_result"] == "REJECTED"
    assert "UPSELL_LIMIT_EXCEEDED" in upsell_entries[0]["reason"] or "Maximum 1 upsell" in upsell_entries[0]["reason"]

    assert upsell_entries[1]["policy_result"] == "ALLOWED"
