import logging
import threading

from confluent_kafka import Consumer, Producer, KafkaError

from src.config import AppConfig
from src.models.fraud_result import FraudResult
from src.models.transaction import Transaction
from src.streaming.serialization import json_deserializer, json_serializer
from src.streaming.topics import (
    TOPIC_APPROVED,
    TOPIC_FRAUD_ALERTS,
    TOPIC_HUMAN_REVIEW,
    TOPIC_TRANSACTIONS,
)

logger = logging.getLogger(__name__)


class FraudConsumer:
    """Consumes transactions, scores them via the pipeline, and routes results."""

    def __init__(
        self,
        bootstrap_servers: str,
        pipeline,
        tx_repo=None,
        group_id: str = "fraud-detection-group",
        config: AppConfig | None = None,
    ):
        self._config = config or AppConfig()
        self._pipeline = pipeline
        self._tx_repo = tx_repo
        self._bootstrap_servers = bootstrap_servers
        self._group_id = group_id
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start consuming in a background thread (non-blocking)."""
        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="fraud-consumer"
        )
        self._thread.start()
        logger.info("FraudConsumer started, subscribed to '%s'", TOPIC_TRANSACTIONS)

    def _run(self) -> None:
        consumer = Consumer(
            {
                "bootstrap.servers": self._bootstrap_servers,
                "group.id": self._group_id,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        producer = Producer({"bootstrap.servers": self._bootstrap_servers})
        consumer.subscribe([TOPIC_TRANSACTIONS])

        try:
            while self._running:
                msg = consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug(
                            "End of partition %s [%d] @ %d",
                            msg.topic(),
                            msg.partition(),
                            msg.offset(),
                        )
                    else:
                        logger.error("Consumer error: %s", msg.error())
                    continue

                self._process_message(msg, consumer, producer)
        finally:
            consumer.close()
            producer.flush(timeout=5)
            logger.info("FraudConsumer stopped")

    def _process_message(self, msg, consumer, producer) -> None:
        """Deserialize, score, route, and commit."""
        try:
            data = json_deserializer(msg.value())
            transaction = Transaction.from_dict(data)

            result: FraudResult = self._pipeline.score(transaction)

            # Persist to MySQL
            if self._tx_repo is not None:
                try:
                    self._tx_repo.insert_transaction(transaction)
                    self._tx_repo.insert_fraud_result(result)
                except Exception:
                    logger.warning("DB persist failed for txn %s", transaction.transaction_id, exc_info=True)

            output_topic = self._route(result.score)
            producer.produce(
                output_topic,
                key=transaction.user_id.encode("utf-8"),
                value=json_serializer(result.to_dict()),
                callback=self._delivery_callback,
            )
            producer.poll(0)

            consumer.commit(message=msg)

            logger.debug(
                "Scored txn %s -> %.2f, routed to '%s'",
                transaction.transaction_id,
                result.score,
                output_topic,
            )
        except Exception:
            logger.exception("Failed to process message at offset %d", msg.offset())

    def _route(self, score: float) -> str:
        """Determine the output topic based on the fraud score."""
        if score >= self._config.SCORE_THRESHOLD_FRAUD:
            return TOPIC_FRAUD_ALERTS
        if score >= self._config.SCORE_THRESHOLD_REVIEW:
            return TOPIC_HUMAN_REVIEW
        return TOPIC_APPROVED

    def _delivery_callback(self, err, msg):
        if err:
            logger.error("Output delivery failed: %s", err)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
