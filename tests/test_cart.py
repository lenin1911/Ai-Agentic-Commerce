import pytest
from backend.app import create_app
from backend.store import get_store, Store, CartError


@pytest.fixture
def client():
    app = create_app({"TESTING": True})
    with app.test_client() as client:
        # Reset store before each test
        get_store().reset_all()
        yield client
        get_store().reset_all()


def test_add_valid_item_to_cart(client):
    """Test adding an eligible product to cart updates items and subtotal."""
    res = client.post(
        "/agent/cart",
        json={
            "session_id": "test_sess_01",
            "action": "add",
            "sku": "EDGE-DEV-KIT-01",
            "quantity": 1,
        },
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    cart = data["cart"]
    assert cart["session_id"] == "test_sess_01"
    assert cart["item_count"] == 1
    assert cart["subtotal"] == 4200
    assert len(cart["items"]) == 1
    assert cart["items"][0]["sku"] == "EDGE-DEV-KIT-01"
    assert cart["items"][0]["quantity"] == 1
    assert cart["items"][0]["unit_price"] == 4200
    assert cart["items"][0]["total_price"] == 4200


def test_add_multiple_quantities_and_items(client):
    """Test cumulative item additions and multiple distinct SKUs."""
    session_id = "test_sess_multi"

    # Add 2 cables (650 each = 1300)
    res1 = client.post(
        "/agent/cart",
        json={
            "session_id": session_id,
            "action": "add",
            "sku": "CABLE-USB4-PRO-04",
            "quantity": 2,
        },
    )
    assert res1.status_code == 200
    assert res1.get_json()["cart"]["subtotal"] == 1300

    # Add 1 more cable (now 3 cables = 1950)
    res2 = client.post(
        "/agent/cart",
        json={
            "session_id": session_id,
            "action": "add",
            "sku": "CABLE-USB4-PRO-04",
            "quantity": 1,
        },
    )
    assert res2.status_code == 200
    assert res2.get_json()["cart"]["subtotal"] == 1950
    assert res2.get_json()["cart"]["item_count"] == 3

    # Add 1 cooling case (850, total 2800)
    res3 = client.post(
        "/agent/cart",
        json={
            "session_id": session_id,
            "action": "add",
            "sku": "CASE-ALU-COOL-05",
            "quantity": 1,
        },
    )
    assert res3.status_code == 200
    cart = res3.get_json()["cart"]
    assert cart["subtotal"] == 2800
    assert cart["item_count"] == 4
    assert len(cart["items"]) == 2


def test_update_item_quantity(client):
    """Test updating existing item quantity."""
    session_id = "test_sess_update"
    client.post(
        "/agent/cart",
        json={
            "session_id": session_id,
            "action": "add",
            "sku": "CABLE-USB4-PRO-04",
            "quantity": 5,
        },
    )

    res = client.post(
        "/agent/cart",
        json={
            "session_id": session_id,
            "action": "update",
            "sku": "CABLE-USB4-PRO-04",
            "quantity": 2,
        },
    )
    assert res.status_code == 200
    cart = res.get_json()["cart"]
    assert cart["items"][0]["quantity"] == 2
    assert cart["subtotal"] == 1300


def test_remove_item_and_clear_cart(client):
    """Test removing specific item and clearing cart."""
    session_id = "test_sess_remove"
    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "CABLE-USB4-PRO-04", "quantity": 2},
    )
    client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "add", "sku": "CASE-ALU-COOL-05", "quantity": 1},
    )

    # Remove cable
    res_remove = client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "remove", "sku": "CABLE-USB4-PRO-04"},
    )
    assert res_remove.status_code == 200
    cart = res_remove.get_json()["cart"]
    assert len(cart["items"]) == 1
    assert cart["items"][0]["sku"] == "CASE-ALU-COOL-05"

    # Clear cart
    res_clear = client.post(
        "/agent/cart",
        json={"session_id": session_id, "action": "clear"},
    )
    assert res_clear.status_code == 200
    assert res_clear.get_json()["cart"]["item_count"] == 0
    assert res_clear.get_json()["cart"]["subtotal"] == 0


def test_invalid_sku_rejection(client):
    """Test that non-existent SKU returns 400 with INVALID_SKU code."""
    res = client.post(
        "/agent/cart",
        json={
            "session_id": "test_sess_err",
            "action": "add",
            "sku": "NON-EXISTENT-SKU",
            "quantity": 1,
        },
    )
    assert res.status_code == 400
    data = res.get_json()
    assert data["status"] == "error"
    assert data["code"] == "INVALID_SKU"


def test_ineligible_sku_rejection(client):
    """Test that SKU flagged agent_eligible=false returns 400 with SKU_NOT_ELIGIBLE."""
    res = client.post(
        "/agent/cart",
        json={
            "session_id": "test_sess_err2",
            "action": "add",
            "sku": "ENTERPRISE-SERVER-RACK-03",
            "quantity": 1,
        },
    )
    assert res.status_code == 400
    data = res.get_json()
    assert data["status"] == "error"
    assert data["code"] == "SKU_NOT_ELIGIBLE"


def test_invalid_quantity_rejection(client):
    """Test negative and non-integer quantity rejection."""
    res = client.post(
        "/agent/cart",
        json={
            "session_id": "test_sess_err3",
            "action": "add",
            "sku": "CABLE-USB4-PRO-04",
            "quantity": -2,
        },
    )
    assert res.status_code == 400
    data = res.get_json()
    assert data["status"] == "error"
    assert data["code"] == "INVALID_QUANTITY"


def test_insufficient_stock_rejection(client):
    """Test requesting more than available stock is rejected."""
    # EDGE-DEV-KIT-01 has 25 in stock
    res = client.post(
        "/agent/cart",
        json={
            "session_id": "test_sess_stock",
            "action": "add",
            "sku": "EDGE-DEV-KIT-01",
            "quantity": 9999,
        },
    )
    assert res.status_code == 400
    data = res.get_json()
    assert data["status"] == "error"
    assert data["code"] == "INSUFFICIENT_STOCK"


def test_get_cart_and_session_isolation(client):
    """Test GET /agent/cart returns session-scoped state."""
    # Add item to session A
    client.post(
        "/agent/cart",
        json={"session_id": "sess_A", "action": "add", "sku": "CABLE-USB4-PRO-04", "quantity": 2},
    )

    # Add item to session B
    client.post(
        "/agent/cart",
        json={"session_id": "sess_B", "action": "add", "sku": "CASE-ALU-COOL-05", "quantity": 1},
    )

    res_a = client.get("/agent/cart?session_id=sess_A")
    assert res_a.status_code == 200
    cart_a = res_a.get_json()["cart"]
    assert cart_a["subtotal"] == 1300
    assert cart_a["items"][0]["sku"] == "CABLE-USB4-PRO-04"

    res_b = client.get("/agent/cart?session_id=sess_B")
    assert res_b.status_code == 200
    cart_b = res_b.get_json()["cart"]
    assert cart_b["subtotal"] == 850
    assert cart_b["items"][0]["sku"] == "CASE-ALU-COOL-05"
