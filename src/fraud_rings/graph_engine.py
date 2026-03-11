import logging
import uuid
from datetime import datetime, timezone

import networkx as nx

from src.models.fraud_ring import FraudRing
from src.models.transaction import Transaction

logger = logging.getLogger(__name__)


class FraudGraph:
    """Build a multi-modal graph connecting users, devices, and IPs to detect fraud rings."""

    def __init__(self, min_users: int = 3):
        self.graph = nx.Graph()
        self._min_users = min_users
        # Track total transaction amounts per resource for ring reporting
        self._resource_amounts: dict[str, float] = {}

    def add_transaction(self, tx: Transaction) -> None:
        """Add nodes and edges for a transaction."""
        user_node = f"User:{tx.user_id}"
        device_node = f"Device:{tx.device_id}"
        ip_node = f"IP:{tx.ip_address}"

        self.graph.add_node(user_node, type="user")
        self.graph.add_node(device_node, type="device")
        self.graph.add_node(ip_node, type="ip")

        # Add weighted edges
        self.graph.add_edge(user_node, device_node, weight=tx.amount)
        self.graph.add_edge(user_node, ip_node, weight=tx.amount)
        self.graph.add_edge(device_node, ip_node, weight=tx.amount)

        # Track amounts per shared resource
        for resource in (device_node, ip_node):
            self._resource_amounts[resource] = (
                self._resource_amounts.get(resource, 0.0) + tx.amount
            )

    def detect_fraud_rings(self) -> list[FraudRing]:
        """Identify fraud rings where 3+ users share a device or IP."""
        fraud_rings: list[FraudRing] = []

        for node in self.graph.nodes():
            if not (node.startswith("Device:") or node.startswith("IP:")):
                continue

            neighbors = list(self.graph.neighbors(node))
            user_neighbors = [n for n in neighbors if n.startswith("User:")]

            if len(user_neighbors) >= self._min_users:
                resource_type = "device" if node.startswith("Device:") else "ip"
                resource_id = node.split(":", 1)[1]
                user_ids = [u.split(":", 1)[1] for u in user_neighbors]
                risk_score = min(len(user_neighbors) / 10.0, 1.0)
                total_amount = self._resource_amounts.get(node, 0.0)

                fraud_rings.append(
                    FraudRing(
                        ring_id=str(uuid.uuid4()),
                        shared_resource_type=resource_type,
                        shared_resource_id=resource_id,
                        user_ids=user_ids,
                        risk_score=risk_score,
                        total_transaction_amount=total_amount,
                        detected_at=datetime.now(timezone.utc).isoformat(),
                    )
                )

        return fraud_rings

    def get_ring_for_user(self, user_id: str) -> FraudRing | None:
        """Return the highest-risk fraud ring involving this user, or None."""
        rings = self.detect_fraud_rings()
        user_rings = [r for r in rings if user_id in r.user_ids]
        if not user_rings:
            return None
        return max(user_rings, key=lambda r: r.risk_score)

    def get_network_stats(self) -> dict:
        """Return graph statistics."""
        return {
            "node_count": self.graph.number_of_nodes(),
            "edge_count": self.graph.number_of_edges(),
            "components": nx.number_connected_components(self.graph),
        }
