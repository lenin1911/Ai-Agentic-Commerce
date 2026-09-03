from datetime import date
import pytest
from backend.policy import PolicyEngine, PolicyResult, get_policy_engine
from backend.catalog import get_catalog_manager


@pytest.fixture
def policy_engine():
    return PolicyEngine(catalog_mgr=get_catalog_manager())


def test_sku_policy_valid(policy_engine):
    """Test valid, eligible in-stock SKU passes policy check."""
    result = policy_engine.validate_sku("EDGE-DEV-KIT-01")
    assert isinstance(result, PolicyResult)
    assert result.allowed is True
    assert result.code == "SKU_ALLOWED"


def test_sku_policy_ineligible(policy_engine):
    """Test non-agent-eligible SKU is rejected by policy."""
    result = policy_engine.validate_sku("ENTERPRISE-SERVER-RACK-03")
    assert result.allowed is False
    assert result.code == "SKU_NOT_ELIGIBLE"


def test_sku_policy_not_found(policy_engine):
    """Test non-existent SKU is rejected."""
    result = policy_engine.validate_sku("GHOST-SKU-999")
    assert result.allowed is False
    assert result.code == "SKU_NOT_FOUND"


def test_coupon_policy_valid(policy_engine):
    """Test valid coupon under 15% limit is allowed."""
    result = policy_engine.validate_coupon("WELCOME10", reference_date=date(2026, 6, 1))
    assert result.allowed is True
    assert result.code == "COUPON_VALID"
    assert "10%" in result.reason


def test_coupon_policy_non_existent(policy_engine):
    """Test non-existent coupon code rejection."""
    result = policy_engine.validate_coupon("FAKECODE123")
    assert result.allowed is False
    assert result.code == "COUPON_NOT_FOUND"


def test_coupon_policy_expired_or_inactive(policy_engine):
    """Test expired coupon rejection (SUMMER10 expired 2024-06-30)."""
    result = policy_engine.validate_coupon("SUMMER10", reference_date=date(2026, 6, 1))
    assert result.allowed is False
    assert result.code == "COUPON_EXPIRED"
    assert "SUMMER10" in result.reason.upper() and "EXPIRED" in result.reason.upper()


def test_coupon_policy_excessive_discount(policy_engine):
    """Test coupon offering > 15% discount is rejected by policy ceiling."""
    result = policy_engine.validate_coupon("EXCESSIVE50")
    assert result.allowed is False
    assert result.code == "DISCOUNT_EXCEEDS_POLICY_MAX"
    assert "15%" in result.reason


def test_upsell_policy_allowed(policy_engine):
    """Test initial upsell within spend ceiling is approved."""
    result = policy_engine.validate_upsell(
        current_upsells_count=0,
        upsell_sku="CABLE-USB4-PRO-04",
        current_total=4200,
        upsell_price=650,
    )
    assert result.allowed is True
    assert result.code == "UPSELL_ALLOWED"


def test_upsell_policy_limit_exceeded(policy_engine):
    """Test second upsell request is rejected (max 1 per session)."""
    result = policy_engine.validate_upsell(
        current_upsells_count=1,
        upsell_sku="CASE-ALU-COOL-05",
        current_total=4850,
    )
    assert result.allowed is False
    assert result.code == "UPSELL_LIMIT_EXCEEDED"


def test_upsell_policy_spend_ceiling_exceeded(policy_engine):
    """Test upsell that pushes session total past ₹10,000 ceiling is rejected."""
    result = policy_engine.validate_upsell(
        current_upsells_count=0,
        upsell_sku="EDGE-DEV-KIT-01",  # 4200
        current_total=7000,
        upsell_price=4200,  # 7000 + 4200 = 11200 > 10000
    )
    assert result.allowed is False
    assert result.code == "SPEND_CEILING_EXCEEDED"


def test_spend_ceiling_check(policy_engine):
    """Test session spend ceiling check for ₹10,000 boundary."""
    assert policy_engine.check_spend_ceiling(9999).allowed is True
    assert policy_engine.check_spend_ceiling(10000).allowed is True
    assert policy_engine.check_spend_ceiling(10001).allowed is False
    assert policy_engine.check_spend_ceiling(10001).code == "SPEND_CEILING_EXCEEDED"


def test_human_approval_threshold(policy_engine):
    """Test transactions >= ₹5,000 require human approval unless explicitly signed off."""
    assert policy_engine.check_human_approval(4999).allowed is True
    res_exact = policy_engine.check_human_approval(5000)
    assert res_exact.allowed is False
    assert res_exact.code == "HUMAN_APPROVAL_REQUIRED"

    res_high = policy_engine.check_human_approval(7000)
    assert res_high.allowed is False
    assert res_high.code == "HUMAN_APPROVAL_REQUIRED"

    # When explicitly approved by human supervisor
    res_approved = policy_engine.check_human_approval(7000, human_approved=True)
    assert res_approved.allowed is True
    assert res_approved.code == "HUMAN_APPROVAL_GRANTED"
