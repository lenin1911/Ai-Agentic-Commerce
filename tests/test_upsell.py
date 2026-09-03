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


def test_valid_upsell_added_and_total_recalculated(client):
    """Test valid upsell adds item to cart and recalculates total."""
    session_id = "test_upsell_valid"

    # Start with Edge Dev Kit (4200)
    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )

    # Upsell Thunderbolt 4 Cable (650)
    res = client.post(
        "/agent/upsell",
        json={"session_id": session_id, "sku": "CABLE-USB4-PRO-04"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "applied"
    assert data["upsell_sku"] == "CABLE-USB4-PRO-04"

    cart = data["cart"]
    assert cart["item_count"] == 2
    assert cart["subtotal"] == 4850  # 4200 + 650
    assert cart["total"] == 4850
    assert cart["upsells_count"] == 1


def test_invalid_sku_upsell_rejected(client):
    """Test upsell with non-existent or ineligible SKU is rejected."""
    session_id = "test_upsell_bad_sku"

    res = client.post(
        "/agent/upsell",
        json={"session_id": session_id, "sku": "NON_EXISTENT_ACC"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "rejected"
    assert data["code"] == "SKU_NOT_FOUND"


def test_second_upsell_rejected(client):
    """Test policy boundary: maximum 1 upsell allowed per session."""
    session_id = "test_upsell_limit"

    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 1},
    )

    # First upsell succeeds
    res1 = client.post(
        "/agent/upsell",
        json={"session_id": session_id, "sku": "CABLE-USB4-PRO-04"},
    )
    assert res1.status_code == 200
    assert res1.get_json()["status"] == "applied"

    # Second upsell must be rejected by policy
    res2 = client.post(
        "/agent/upsell",
        json={"session_id": session_id, "sku": "CASE-ALU-COOL-05"},
    )
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert data2["status"] == "rejected"
    assert data2["code"] == "UPSELL_LIMIT_EXCEEDED"
    assert "Maximum 1 upsell" in data2["reason"]

    # Cart retains exactly 1 upsell
    assert data2["cart"]["upsells_count"] == 1
    assert data2["cart"]["subtotal"] == 4850


def test_upsell_spend_ceiling_rejection(client):
    """Test upsell that would push total over ₹10,000 ceiling is rejected."""
    session_id = "test_upsell_ceiling"

    # Add 2 Edge Dev Kits (4200 * 2 = 8400)
    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "EDGE-DEV-KIT-01", "quantity": 2},
    )

    # Attempt to upsell USB AI Co-Processor Stick (2800) -> 8400 + 2800 = 11200 > 10000
    res = client.post(
        "/agent/upsell",
        json={"session_id": session_id, "sku": "USB-CORAL-TPU-02"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "rejected"
    assert data["code"] == "SPEND_CEILING_EXCEEDED"
    assert "10000" in data["reason"]

    # Cart remains at 8400
    assert data["cart"]["total"] == 8400
    assert data["cart"]["upsells_count"] == 0
