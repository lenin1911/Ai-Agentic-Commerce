import pytest
from backend.app import create_app
from backend.store import get_store
from backend.audit import get_audit_logger
from backend.razorpay_client import get_razorpay_client, MockRazorpayClient


@pytest.fixture
def client(tmp_path):
    db_file = str(tmp_path / "test_rzp_audit.db")
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


def test_mock_razorpay_client_direct():
    """Test MockRazorpayClient creates orders and captures payments with 100x paise conversion."""
    rzp = MockRazorpayClient()
    assert rzp.is_mock is True

    # Create Order for ₹4,200 (420,000 paise)
    order = rzp.create_order(
        amount_in_inr=4200,
        currency="INR",
        receipt="rcpt_unit_01",
        notes={"test": "true"},
    )
    assert order["id"].startswith("order_mock_")
    assert order["amount"] == 420000
    assert order["currency"] == "INR"
    assert order["status"] == "created"
    assert order["mode"] == "mock"

    # Capture Payment
    payment = rzp.capture_payment(
        payment_id=None,
        amount_in_inr=4200,
        currency="INR",
    )
    assert payment["id"].startswith("pay_mock_")
    assert payment["amount"] == 420000
    assert payment["status"] == "captured"
    assert payment["captured"] is True
    assert payment["mode"] == "mock"


def test_razorpay_fallback_when_credentials_placeholder(monkeypatch):
    """Test get_razorpay_client falls back to Mock client when keys are placeholders."""
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_placeholder")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_secret_placeholder")

    client_instance = get_razorpay_client()
    assert client_instance.is_mock is True


def test_checkout_creates_razorpay_order_and_captures_payment(client):
    """Test full flow: cart -> checkout (Razorpay order) -> payment capture -> audit."""
    session_id = "test_rzp_e2e_sess"

    # 1. Add item to cart (4200 <= 5000)
    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )

    # 2. Checkout (creates Razorpay order)
    checkout_res = client.post(
        "/agent/checkout",
        json={"session_id": session_id},
    )
    assert checkout_res.status_code == 200
    checkout_data = checkout_res.get_json()
    assert checkout_data["status"] == "success"
    order_id = checkout_data["order_id"]
    assert "razorpay_order" in checkout_data
    assert checkout_data["razorpay_order"]["amount"] == 420000

    # 3. Capture payment
    capture_res = client.post(
        "/agent/payment/capture",
        json={
            "session_id": session_id,
            "order_id": order_id,
            "payment_id": "pay_mock_test999",
            "amount": 4200,
        },
    )
    assert capture_res.status_code == 200
    capture_data = capture_res.get_json()
    assert capture_data["status"] == "success"
    assert capture_data["payment_id"] == "pay_mock_test999"
    assert capture_data["order_id"] == order_id

    # 4. Verify audit trail has checkout and payment capture entries
    audit_res = client.get(f"/audit?session_id={session_id}")
    entries = audit_res.get_json()["audit_trail"]
    actions = [e["action"] for e in entries]
    assert "checkout" in actions
    assert "payment_capture" in actions

    capture_entry = next(e for e in entries if e["action"] == "payment_capture")
    assert capture_entry["policy_result"] == "ALLOWED"
    assert capture_entry["razorpay_ref"] == "pay_mock_test999"
