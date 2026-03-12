import logging
import threading

from confluent_kafka import Consumer, KafkaError

from src.config import AppConfig
from src.streaming.serialization import json_deserializer
from src.streaming.topics import TOPIC_VELOCITY_ALERTS

logger = logging.getLogger(__name__)


class FraudConsumer:
    """Consumes velocity alerts from FED_velocity_stream_alerts_all,
    scores them via the pipeline, and optionally persists results.

    Architecture alignment with production:
        ksqlDB 1h tumbling windows → FED_velocity_stream_alerts_all (JSON)
        → FraudConsumer._process_message()
        → ScoringPipeline.score_alert()
        → persist / alert on block
    """

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
        logger.info(
            "FraudConsumer started, subscribed to '%s'", TOPIC_VELOCITY_ALERTS
        )

    def _run(self) -> None:
        consumer = Consumer(
            {
                "bootstrap.servers": self._bootstrap_servers,
                "group.id": self._group_id,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        consumer.subscribe([TOPIC_VELOCITY_ALERTS])

        try:
            while self._running:
                msg = consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug(
                            "End of partition %s [%d] @ %d",
                            msg.topic(), msg.partition(), msg.offset(),
                        )
                    else:
                        logger.error("Consumer error: %s", msg.error())
                    continue
                self._process_message(msg, consumer)
        finally:
            consumer.close()
            logger.info("FraudConsumer stopped")

    def _process_message(self, msg, consumer) -> None:
        """Deserialize JSON, normalize keys to lowercase, score, persist, commit."""
        try:
            raw = json_deserializer(msg.value())

            # ksqlDB emits field names in UPPERCASE — normalize to lowercase
            # so the pipeline and rules match the expected key format.
            alert_data = {k.lower(): v for k, v in raw.items()}

            result = self._pipeline.score_alert(alert_data)

            # Optional persistence (MySQL via tx_repo)
            if self._tx_repo is not None:
                try:
                    self._tx_repo.insert_fraud_result(result)
                except Exception:
                    logger.warning(
                        "DB persist failed for %s/%s",
                        result.get("dimension"), result.get("dimension_key"),
                        exc_info=True,
                    )

            consumer.commit(message=msg)

            logger.info(
                "Scored alert: dimension=%s key=%s txn_count=%s score=%d routing=%s",
                result.get("dimension"),
                result.get("dimension_key"),
                result.get("txn_count"),
                result.get("score", 0),
                result.get("routing"),
            )
        except Exception:
            logger.exception("Failed to process message at offset %d", msg.offset())

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
