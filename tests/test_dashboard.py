"""
Tests for Agent Storefront Dashboard (Milestone 13).
Verifies that Flask serves frontend dashboard assets, CORS headers, and required dashboard views.
"""

import pytest
from backend.app import create_app


@pytest.fixture
def client():
    app = create_app({"TESTING": True})
    with app.test_client() as client:
        yield client


def test_dashboard_html_served(client):
    """Test /dashboard serves the frontend index.html successfully."""
    res = client.get("/dashboard")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "<!DOCTYPE html>" in html
    assert "Agent Storefront" in html
    assert "Merchant Product Catalog" in html
    assert "Agent Shopping Cart" in html
    assert "Immutable Audit Trail" in html
    assert "stat-cart-total" in html
    assert "stat-approval-status" in html


def test_dashboard_static_assets_served(client):
    """Test /dashboard static files (styles.css, app.js) are served cleanly."""
    res_css = client.get("/dashboard/styles.css")
    assert res_css.status_code == 200
    css_content = res_css.get_data(as_text=True)
    assert ":root" in css_content or "navbar" in css_content

    res_js = client.get("/dashboard/app.js")
    assert res_js.status_code == 200
    js_content = res_js.get_data(as_text=True)
    assert "setupEventListeners" in js_content
    assert "loadCatalog" in js_content


def test_cors_headers_present(client):
    """Test backend endpoints include CORS headers for frontend integration."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.headers.get("Access-Control-Allow-Origin") == "*"
    assert "Content-Type" in res.headers.get("Access-Control-Allow-Headers", "")
