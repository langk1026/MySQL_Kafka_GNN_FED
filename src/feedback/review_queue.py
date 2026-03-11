import json
import logging
import threading

from confluent_kafka import Consumer, KafkaError

from src.models import FraudResult
from src.streaming.topics import TOPIC_HUMAN_REVIEW

logger = logging.getLogger(__name__)


class ReviewQueue:
    """
    Consumes from the human-review Kafka topic in a background thread
    and maintains an in-memory dict of pending review items.
    """

    def __init__(self, bootstrap_servers: str, group_id: str = "review-queue-group"):
        self._bootstrap_servers = bootstrap_servers
        self._group_id = group_id
        self._pending: dict[str, FraudResult] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start consuming from the human-review topic in a background thread."""
        self._running = True
        self._thread = threading.Thread(
            target=self._consume_loop, daemon=True, name="review-queue-consumer"
        )
        self._thread.start()
        logger.info("ReviewQueue started, consuming from '%s'", TOPIC_HUMAN_REVIEW)

    def _consume_loop(self) -> None:
        consumer = Consumer({
            "bootstrap.servers": self._bootstrap_servers,
            "group.id": self._group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
        })
        consumer.subscribe([TOPIC_HUMAN_REVIEW])

        try:
            while self._running:
                msg = consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug("Reached end of partition for %s", TOPIC_HUMAN_REVIEW)
                    else:
                        logger.error("Consumer error: %s", msg.error())
                    continue

                try:
                    data = json.loads(msg.value().decode("utf-8"))
                    fraud_result = FraudResult.from_dict(data)
                    with self._lock:
                        self._pending[fraud_result.transaction_id] = fraud_result
                    logger.debug(
                        "Added review item for tx %s (score: %.3f)",
                        fraud_result.transaction_id, fraud_result.score,
                    )
                except Exception:
                    logger.exception("Failed to process review queue message")
        finally:
            consumer.close()
            logger.info("ReviewQueue consumer closed")

    def get_pending(self, limit: int = 50, offset: int = 0) -> list[FraudResult]:
        """Get paginated list of pending review items."""
        with self._lock:
            items = list(self._pending.values())
        return items[offset: offset + limit]

    def get_item(self, transaction_id: str) -> FraudResult | None:
        """Get a single pending review item."""
        with self._lock:
            return self._pending.get(transaction_id)

    def mark_reviewed(self, transaction_id: str) -> None:
        """Remove item from pending queue after review."""
        with self._lock:
            removed = self._pending.pop(transaction_id, None)
        if removed:
            logger.info("Marked tx %s as reviewed", transaction_id)
        else:
            logger.warning("Attempted to mark non-pending tx %s as reviewed", transaction_id)

    def stop(self) -> None:
        """Stop the consumer thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("ReviewQueue stopped")
