import logging
from abc import ABC, abstractmethod

import httpx

from src.models.transaction import Transaction

logger = logging.getLogger(__name__)


class Rule(ABC):
    """Base class for fraud-detection rules."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    def evaluate(self, transaction: Transaction, history: list[Transaction]) -> float:
        """Return a risk score between 0.0 and 1.0."""
        ...


class HighAmountRule(Rule):
    """Flag transactions with unusually high amounts.

    Graduated scoring:
      >$10k → 0.9  (very suspicious, near-certain block)
      >$5k  → 0.6  (elevated, human review)
      >$2k  → 0.35 (mild, human review)
    """

    def __init__(self):
        super().__init__("High Value", "Transaction amount exceeds threshold")

    def evaluate(self, transaction: Transaction, history: list[Transaction]) -> float:
        if transaction.amount > 10000:
            return 0.9
        if transaction.amount > 5000:
            return 0.6
        if transaction.amount > 2000:
            return 0.35
        return 0.0


class LocationAnomalyRule(Rule):
    """Flag rapid location changes for the same user.

    A single location change is suspicious (0.5 → human review range).
    Multiple recent location changes are stronger signals (0.7).
    """

    def __init__(self):
        super().__init__("Location Jump", "User location changed rapidly")

    def evaluate(self, transaction: Transaction, history: list[Transaction]) -> float:
        user_txs = [tx for tx in history if tx.user_id == transaction.user_id]
        if not user_txs:
            return 0.0

        last_tx = user_txs[-1]
        if last_tx.location == transaction.location:
            return 0.0

        # Count distinct locations in the last 5 transactions
        recent = user_txs[-5:]
        recent_locations = {tx.location for tx in recent}
        recent_locations.add(transaction.location)

        if len(recent_locations) >= 3:
            # User has been in 3+ locations recently — stronger signal
            return 0.7
        # Single location change — moderate suspicion
        return 0.5


class VelocityRule(Rule):
    """Query ksqlDB for user transaction velocity.

    With 100 users and ~1-2 txn/sec producer rate, each user averages
    ~6 txns per 5-minute window.  Thresholds are set higher to only flag
    genuinely abnormal bursts:
      8-14 txns  → 0.4  (moderate, human review)
      15-24 txns → 0.6  (elevated)
      25+  txns  → 0.85 (extreme, likely fraud)
    """

    def __init__(self, ksqldb_url: str = "http://ksqldb-server:8088"):
        super().__init__("Velocity", "High transaction velocity detected via ksqlDB")
        self._ksqldb_url = ksqldb_url.rstrip("/")

    def evaluate(self, transaction: Transaction, history: list[Transaction]) -> float:
        # Sanitize user_id to prevent injection
        safe_user_id = transaction.user_id.replace("'", "''")
        query = (
            f"SELECT txn_count FROM user_velocity "
            f"WHERE user_id = '{safe_user_id}';"
        )
        try:
            response = httpx.post(
                f"{self._ksqldb_url}/query",
                json={"ksql": query, "streamsProperties": {}},
                headers={"Accept": "application/vnd.ksql.v1+json"},
                timeout=5.0,
            )
            response.raise_for_status()
            rows = response.json()

            for row in rows:
                if "row" in row and "columns" in row["row"]:
                    txn_count = row["row"]["columns"][0]
                    if txn_count >= 25:
                        return 0.85
                    if txn_count >= 15:
                        return 0.6
                    if txn_count >= 8:
                        return 0.4
            return 0.0
        except Exception:
            logger.debug(
                "VelocityRule: ksqlDB query failed for user %s, returning 0.0",
                transaction.user_id,
                exc_info=True,
            )
            return 0.0
