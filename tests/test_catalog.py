import json
import pytest
from backend.app import create_app
from backend.catalog import CatalogManager, CatalogValidationError


@pytest.fixture
def client():
    app = create_app({"TESTING": True})
    with app.test_client() as client:
        yield client


def test_catalog_manager_loads_valid_catalog():
    """Verify CatalogManager loads default seed catalog successfully."""
    mgr = CatalogManager()
    agent_catalog = mgr.get_agent_catalog()

    assert "store" in agent_catalog
    assert "products" in agent_catalog
    assert len(agent_catalog["products"]) > 0

    # Verify store policies and endpoints are exposed
    assert "endpoints" in agent_catalog["store"]
    assert "store_policies" in agent_catalog["store"]

    # Verify product properties
    first_product = agent_catalog["products"][0]
    for key in ["sku", "name", "description", "price", "currency", "in_stock", "agent_eligible"]:
        assert key in first_product


def test_catalog_sku_helpers():
    """Verify SKU lookup and eligibility checks."""
    mgr = CatalogManager()
    allowed_skus = mgr.get_allowed_skus()
    assert "EDGE-DEV-KIT-01" in allowed_skus
    assert mgr.is_sku_allowed("EDGE-DEV-KIT-01") is True

    # Non-agent-eligible SKU check
    assert mgr.is_sku_allowed("ENTERPRISE-SERVER-RACK-03") is False
    # Non-existent SKU check
    assert mgr.is_sku_allowed("NON-EXISTENT-SKU") is False


def test_catalog_validation_missing_fields(tmp_path):
    """Verify CatalogValidationError is raised for corrupted or incomplete catalog files."""
    bad_catalog = tmp_path / "bad_catalog.json"
    bad_catalog.write_text(json.dumps({"store": {"name": "Test"}}))

    with pytest.raises(CatalogValidationError):
        CatalogManager(catalog_path=str(bad_catalog))


def test_agent_catalog_endpoint(client):
    """Verify GET /.well-known/agent-catalog.json returns 200 and machine-readable data."""
    response = client.get("/.well-known/agent-catalog.json")
    assert response.status_code == 200
    assert response.content_type == "application/json"

    data = response.get_json()
    assert data["catalog_version"] == "1.0.0"
    assert data["store"]["name"] == "Nova Hardware & Cloud Gear"
    assert data["store"]["currency"] == "INR"
    assert isinstance(data["products"], list)
    assert len(data["products"]) >= 3

    # Check that each product has expected types
    for item in data["products"]:
        assert isinstance(item["sku"], str)
        assert isinstance(item["name"], str)
        assert isinstance(item["price"], (int, float))
        assert isinstance(item["in_stock"], bool)
        assert isinstance(item["agent_eligible"], bool)
