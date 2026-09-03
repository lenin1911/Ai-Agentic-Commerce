"""
Tests for Buyer Agent Simulation (Milestone 12).
Verifies deterministic buyer flow through public backend endpoints:
catalog discovery -> cart addition -> expired coupon rejection -> recovery -> checkout -> approval gate -> payment capture.
"""

import pytest
from backend.app import create_app
from backend.store import get_store
from backend.audit import get_audit_logger
from buyer_agent.simulate_buyer import BuyerClient, run_buyer_simulation


@pytest.fixture
def isolated_client(tmp_path):
    db_file = str(tmp_path / "sim_test_audit.db")
    app = create_app({
        "TESTING": True,
        "AUDIT_DB_PATH": db_file,
    })
    logger = get_audit_logger(db_file)
    logger.clear()
    with app.test_client() as flask_client:
        get_store().reset_all()
        yield BuyerClient(flask_client=flask_client)
        get_store().reset_all()
        logger.clear()


def test_deterministic_buyer_simulation_standard_flow(isolated_client):
    """
    Test standard deterministic buyer flow:
    - Order total < ₹5,000 (autonomous approval)
    - Expired SUMMER10 rejected with COUPON_EXPIRED
    - Recovery to full price
    - Settlement via Razorpay mock
    """
    result = run_buyer_simulation(
        client=isolated_client,
        session_id="test_sim_standard",
        sku="EDGE-DEV-KIT-01",
        quantity=1,
        verbose=False,
    )

    assert result["success"] is True
    assert result["session_id"] == "test_sim_standard"
    assert result["selected_product"]["sku"] == "EDGE-DEV-KIT-01"

    # Verify coupon rejection
    coupon_rej = result["coupon_rejection"]
    assert coupon_rej["status"] == "rejected"
    assert coupon_rej["code"] == "COUPON_EXPIRED"

    # Verify checkout
    checkout = result["checkout"]
    assert checkout["status"] == "success"
    assert checkout["amount"] == 4200
    assert checkout["order_id"].startswith("order_")

    # Verify payment capture
    payment = result["payment"]
    assert payment["status"] == "success"
    assert payment["amount"] == 4200
    assert payment["payment_id"].startswith("pay_")

    # Verify audit logs
    actions = [entry["action"] for entry in result["audit_logs"]]
    assert "cart_add" in actions
    assert "discount_request" in actions
    assert "checkout" in actions
    assert "payment_capture" in actions


def test_deterministic_buyer_simulation_high_value_human_approval_gate(isolated_client):
    """
    Test high-value deterministic buyer flow:
    - Order total >= ₹5,000 requires human approval
    - Buyer agent handles human approval gate via /agent/approval
    - Retries and completes checkout and payment capture
    """
    result = run_buyer_simulation(
        client=isolated_client,
        session_id="test_sim_high_value",
        sku="EDGE-DEV-KIT-01",
        quantity=2,  # 2 * 4200 = ₹8,400 (exceeds ₹5,000 threshold)
        verbose=False,
    )

    assert result["success"] is True
    assert result["checkout"]["amount"] == 8400
    assert result["payment"]["status"] == "success"
    assert result["payment"]["amount"] == 8400

    actions = [entry["action"] for entry in result["audit_logs"]]
    assert "cart_add" in actions
    assert "discount_request" in actions
    assert "checkout" in actions
    assert "human_approval" in actions
    assert "payment_capture" in actions


def test_buyer_simulation_cli_in_process_execution(monkeypatch, tmp_path):
    """Test CLI entrypoint execution with --in-process flag."""
    from buyer_agent.simulate_buyer import main

    monkeypatch.setattr(
        "sys.argv",
        ["simulate_buyer.py", "--in-process", "--quantity", "1"],
    )
    # Should execute and complete without uncaught exceptions or sys.exit(1)
    main()
