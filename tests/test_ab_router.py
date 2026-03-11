import pytest
from unittest.mock import MagicMock

from src.ab_testing.experiment import ExperimentManager
from src.ab_testing.router import ABRouter
from src.models.ab_experiment import ABExperiment
from src.models.transaction import Transaction


def _make_transaction(tx_id: str = "txn-001") -> Transaction:
    return Transaction(
        transaction_id=tx_id,
        user_id="User_1",
        amount=100.0,
        currency="USD",
        timestamp="2026-01-15T10:30:00+00:00",
        merchant_id="Merch_1",
        location="US",
        device_id="Dev_1",
        ip_address="192.168.1.10",
    )


def _make_experiment(
    traffic_split: float = 0.2,
    control_version: str = "v1.0",
    challenger_version: str = "v2.0",
) -> ABExperiment:
    return ABExperiment(
        experiment_id="exp-001",
        name="Test Experiment",
        control_model_version=control_version,
        challenger_model_version=challenger_version,
        traffic_split=traffic_split,
        status="active",
        start_date="2026-01-01T00:00:00+00:00",
        end_date=None,
        created_at="2026-01-01T00:00:00+00:00",
    )


def _make_mock_model(version: str) -> MagicMock:
    model = MagicMock()
    model.version = version
    return model


def test_route_no_experiment_returns_default():
    """When no active experiment exists, route returns the default (first) model."""
    manager = MagicMock(spec=ExperimentManager)
    manager.list_active_experiments.return_value = []

    control_model = _make_mock_model("v1.0")
    models = {"v1.0": control_model}

    router = ABRouter(manager, models)
    tx = _make_transaction()
    result = router.route(tx)

    assert result is control_model


def test_route_deterministic():
    """The same transaction_id should always route to the same model."""
    manager = MagicMock(spec=ExperimentManager)
    experiment = _make_experiment(traffic_split=0.3)
    manager.list_active_experiments.return_value = [experiment]

    control_model = _make_mock_model("v1.0")
    challenger_model = _make_mock_model("v2.0")
    models = {"v1.0": control_model, "v2.0": challenger_model}

    router = ABRouter(manager, models)
    tx = _make_transaction(tx_id="deterministic-id-123")

    # Call route multiple times with the same transaction
    results = [router.route(tx) for _ in range(50)]

    # All results should be the same model
    assert all(r is results[0] for r in results)


def test_route_splits_traffic():
    """With many unique transaction_ids, traffic should split approximately
    according to the configured traffic_split ratio."""
    manager = MagicMock(spec=ExperimentManager)
    traffic_split = 0.3
    experiment = _make_experiment(traffic_split=traffic_split)
    manager.list_active_experiments.return_value = [experiment]

    control_model = _make_mock_model("v1.0")
    challenger_model = _make_mock_model("v2.0")
    models = {"v1.0": control_model, "v2.0": challenger_model}

    router = ABRouter(manager, models)

    num_transactions = 10000
    challenger_count = 0
    for i in range(num_transactions):
        tx = _make_transaction(tx_id=f"txn-split-{i}")
        result = router.route(tx)
        if result is challenger_model:
            challenger_count += 1

    actual_ratio = challenger_count / num_transactions

    # Allow a tolerance of +/- 5 percentage points
    assert abs(actual_ratio - traffic_split) < 0.05, (
        f"Expected ~{traffic_split:.0%} challenger traffic, "
        f"got {actual_ratio:.2%} ({challenger_count}/{num_transactions})"
    )
