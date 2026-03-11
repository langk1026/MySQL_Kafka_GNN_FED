import pytest

from src.fraud_rings.graph_engine import FraudGraph
from src.models.transaction import Transaction


def _make_transaction(
    user_id: str = "User_1",
    device_id: str = "Dev_1",
    ip_address: str = "192.168.1.10",
    amount: float = 100.0,
    tx_id: str | None = None,
) -> Transaction:
    return Transaction(
        transaction_id=tx_id or f"txn-{user_id}-{device_id}",
        user_id=user_id,
        amount=amount,
        currency="USD",
        timestamp="2026-01-15T10:30:00+00:00",
        merchant_id="Merch_1",
        location="US",
        device_id=device_id,
        ip_address=ip_address,
    )


def test_add_transaction_creates_nodes():
    graph = FraudGraph()
    tx = _make_transaction(user_id="User_1", device_id="Dev_1", ip_address="192.168.1.10")
    graph.add_transaction(tx)

    assert graph.graph.has_node("User:User_1")
    assert graph.graph.has_node("Device:Dev_1")
    assert graph.graph.has_node("IP:192.168.1.10")
    assert graph.graph.has_edge("User:User_1", "Device:Dev_1")
    assert graph.graph.has_edge("User:User_1", "IP:192.168.1.10")
    assert graph.graph.has_edge("Device:Dev_1", "IP:192.168.1.10")


def test_detect_fraud_rings_below_threshold():
    """Two users sharing a device should NOT produce a fraud ring (min_users=3)."""
    graph = FraudGraph(min_users=3)

    tx1 = _make_transaction(user_id="User_1", device_id="SharedDev", ip_address="10.0.0.1")
    tx2 = _make_transaction(user_id="User_2", device_id="SharedDev", ip_address="10.0.0.2")

    graph.add_transaction(tx1)
    graph.add_transaction(tx2)

    rings = graph.detect_fraud_rings()
    assert len(rings) == 0


def test_detect_fraud_rings_above_threshold():
    """Three or more users sharing a device should produce a fraud ring."""
    graph = FraudGraph(min_users=3)

    tx1 = _make_transaction(user_id="User_1", device_id="SharedDev", ip_address="10.0.0.1")
    tx2 = _make_transaction(user_id="User_2", device_id="SharedDev", ip_address="10.0.0.2")
    tx3 = _make_transaction(user_id="User_3", device_id="SharedDev", ip_address="10.0.0.3")

    graph.add_transaction(tx1)
    graph.add_transaction(tx2)
    graph.add_transaction(tx3)

    rings = graph.detect_fraud_rings()
    # At least one ring should be detected for the shared device
    device_rings = [r for r in rings if r.shared_resource_type == "device"]
    assert len(device_rings) >= 1

    ring = device_rings[0]
    assert set(ring.user_ids) == {"User_1", "User_2", "User_3"}
    assert ring.shared_resource_id == "SharedDev"


def test_get_ring_for_user():
    """get_ring_for_user should return the ring containing the specified user."""
    graph = FraudGraph(min_users=3)

    for i in range(1, 4):
        tx = _make_transaction(
            user_id=f"User_{i}",
            device_id="SharedDev",
            ip_address=f"10.0.0.{i}",
        )
        graph.add_transaction(tx)

    ring = graph.get_ring_for_user("User_1")
    assert ring is not None
    assert "User_1" in ring.user_ids

    # A user not in the graph should return None
    ring_none = graph.get_ring_for_user("User_999")
    assert ring_none is None
