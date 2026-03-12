import pytest

from src.detection.rules import VelocityAlertRule, HighWindowAmountRule, BlacklistRule


# ---------------------------------------------------------------------------
# VelocityAlertRule
# ---------------------------------------------------------------------------

@pytest.fixture
def velocity_rule():
    return VelocityAlertRule()


def test_velocity_user_high(velocity_rule):
    result = velocity_rule.evaluate({"dimension": "USER", "txn_count": 65})
    assert result is not None
    assert result["severity"] == 95
    assert result["bucket_id"] == "vel_user"


def test_velocity_user_medium(velocity_rule):
    result = velocity_rule.evaluate({"dimension": "USER", "txn_count": 47})
    assert result is not None
    assert result["severity"] == 80


def test_velocity_user_low(velocity_rule):
    result = velocity_rule.evaluate({"dimension": "USER", "txn_count": 30})
    assert result is not None
    assert result["severity"] == 60


def test_velocity_user_no_trigger(velocity_rule):
    result = velocity_rule.evaluate({"dimension": "USER", "txn_count": 10})
    assert result is None


def test_velocity_ip_threshold(velocity_rule):
    # IP threshold: >=60 → sev 60
    result = velocity_rule.evaluate({"dimension": "IP", "txn_count": 62})
    assert result is not None
    assert result["severity"] == 60
    assert result["bucket_id"] == "vel_ip"


def test_velocity_ip_no_trigger(velocity_rule):
    result = velocity_rule.evaluate({"dimension": "IP", "txn_count": 59})
    assert result is None


def test_velocity_merchant_threshold(velocity_rule):
    # MERCHANT lowest threshold >=150 → sev 60
    result = velocity_rule.evaluate({"dimension": "MERCHANT", "txn_count": 155})
    assert result is not None
    assert result["severity"] == 60


def test_velocity_unknown_dimension(velocity_rule):
    result = velocity_rule.evaluate({"dimension": "UNKNOWN", "txn_count": 9999})
    assert result is None


def test_velocity_missing_dimension(velocity_rule):
    result = velocity_rule.evaluate({"txn_count": 100})
    assert result is None


# ---------------------------------------------------------------------------
# HighWindowAmountRule
# ---------------------------------------------------------------------------

@pytest.fixture
def amount_rule():
    return HighWindowAmountRule()


def test_high_window_amount_above_50k(amount_rule):
    result = amount_rule.evaluate({"total_amount": 55000.0})
    assert result is not None
    assert result["severity"] == 90
    assert result["rule_id"] == "high_window_amount"


def test_high_window_amount_above_20k(amount_rule):
    result = amount_rule.evaluate({"total_amount": 25000.0})
    assert result is not None
    assert result["severity"] == 70


def test_high_window_amount_above_10k(amount_rule):
    result = amount_rule.evaluate({"total_amount": 12000.0})
    assert result is not None
    assert result["severity"] == 50


def test_high_window_amount_no_trigger(amount_rule):
    result = amount_rule.evaluate({"total_amount": 5000.0})
    assert result is None


def test_high_window_amount_missing(amount_rule):
    result = amount_rule.evaluate({})
    assert result is None


# ---------------------------------------------------------------------------
# BlacklistRule
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_blacklist():
    BlacklistRule.clear()
    yield
    BlacklistRule.clear()


def test_blacklist_triggers(clear_blacklist):
    BlacklistRule.add("10.99.0.99")
    rule = BlacklistRule()
    result = rule.evaluate({"dimension_key": "10.99.0.99"})
    assert result is not None
    assert result["severity"] == 100
    assert result["rule_id"] == "blacklist"


def test_blacklist_no_trigger(clear_blacklist):
    rule = BlacklistRule()
    result = rule.evaluate({"dimension_key": "192.168.1.1"})
    assert result is None


def test_blacklist_remove(clear_blacklist):
    BlacklistRule.add("bad-key")
    BlacklistRule.remove("bad-key")
    rule = BlacklistRule()
    result = rule.evaluate({"dimension_key": "bad-key"})
    assert result is None


def test_blacklist_missing_key(clear_blacklist):
    rule = BlacklistRule()
    result = rule.evaluate({})
    assert result is None
