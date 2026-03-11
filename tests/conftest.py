import pytest

from src.models.transaction import Transaction


@pytest.fixture
def sample_transaction() -> Transaction:
    """A single sample transaction for testing."""
    return Transaction(
        transaction_id="txn-001",
        user_id="User_1",
        amount=250.00,
        currency="USD",
        timestamp="2026-01-15T10:30:00+00:00",
        merchant_id="Merch_1",
        location="US",
        device_id="Dev_1",
        ip_address="192.168.1.10",
    )


@pytest.fixture
def sample_transactions() -> list[Transaction]:
    """A list of sample transactions for testing."""
    return [
        Transaction(
            transaction_id="txn-001",
            user_id="User_1",
            amount=250.00,
            currency="USD",
            timestamp="2026-01-15T10:30:00+00:00",
            merchant_id="Merch_1",
            location="US",
            device_id="Dev_1",
            ip_address="192.168.1.10",
        ),
        Transaction(
            transaction_id="txn-002",
            user_id="User_2",
            amount=7500.00,
            currency="USD",
            timestamp="2026-01-15T10:31:00+00:00",
            merchant_id="Merch_2",
            location="UK",
            device_id="Dev_2",
            ip_address="192.168.1.20",
        ),
        Transaction(
            transaction_id="txn-003",
            user_id="User_3",
            amount=15000.00,
            currency="USD",
            timestamp="2026-01-15T10:32:00+00:00",
            merchant_id="Merch_3",
            location="IN",
            device_id="Dev_3",
            ip_address="192.168.1.30",
        ),
        Transaction(
            transaction_id="txn-004",
            user_id="User_1",
            amount=100.00,
            currency="USD",
            timestamp="2026-01-15T10:33:00+00:00",
            merchant_id="Merch_4",
            location="JP",
            device_id="Dev_4",
            ip_address="192.168.1.40",
        ),
        Transaction(
            transaction_id="txn-005",
            user_id="User_4",
            amount=50.00,
            currency="USD",
            timestamp="2026-01-15T10:34:00+00:00",
            merchant_id="Merch_5",
            location="US",
            device_id="Dev_1",
            ip_address="192.168.1.50",
        ),
    ]
