import pytest

from src.detection.rules import HighAmountRule, LocationAnomalyRule
from src.models.transaction import Transaction


@pytest.fixture
def high_amount_rule():
    return HighAmountRule()


@pytest.fixture
def location_anomaly_rule():
    return LocationAnomalyRule()


def _make_transaction(amount: float = 100.0, location: str = "US", user_id: str = "User_1") -> Transaction:
    return Transaction(
        transaction_id="txn-test",
        user_id=user_id,
        amount=amount,
        currency="USD",
        timestamp="2026-01-15T10:30:00+00:00",
        merchant_id="Merch_1",
        location=location,
        device_id="Dev_1",
        ip_address="192.168.1.10",
    )


# -- HighAmountRule tests --


def test_high_amount_rule_above_10k(high_amount_rule):
    tx = _make_transaction(amount=15000.0)
    score = high_amount_rule.evaluate(tx, [])
    assert score == 0.9


def test_high_amount_rule_above_5k(high_amount_rule):
    tx = _make_transaction(amount=7500.0)
    score = high_amount_rule.evaluate(tx, [])
    assert score == 0.6


def test_high_amount_rule_below_5k(high_amount_rule):
    tx = _make_transaction(amount=500.0)
    score = high_amount_rule.evaluate(tx, [])
    assert score == 0.0


# -- LocationAnomalyRule tests --


def test_location_anomaly_different(location_anomaly_rule):
    history_tx = _make_transaction(location="US", user_id="User_1")
    current_tx = _make_transaction(location="JP", user_id="User_1")
    score = location_anomaly_rule.evaluate(current_tx, [history_tx])
    assert score == 0.5


def test_location_anomaly_multiple_jumps(location_anomaly_rule):
    """3+ distinct locations in recent history → elevated score."""
    history = [
        _make_transaction(location="US", user_id="User_1"),
        _make_transaction(location="JP", user_id="User_1"),
        _make_transaction(location="IN", user_id="User_1"),
    ]
    current_tx = _make_transaction(location="DE", user_id="User_1")
    score = location_anomaly_rule.evaluate(current_tx, history)
    assert score == 0.7


def test_location_anomaly_same(location_anomaly_rule):
    history_tx = _make_transaction(location="US", user_id="User_1")
    current_tx = _make_transaction(location="US", user_id="User_1")
    score = location_anomaly_rule.evaluate(current_tx, [history_tx])
    assert score == 0.0
