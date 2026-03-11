import json
import logging
import threading
import time
from datetime import datetime, timezone

from confluent_kafka import Producer

from src.feedback.feedback_store import FeedbackStore
from src.streaming.topics import TOPIC_RETRAIN_TRIGGER

logger = logging.getLogger(__name__)


class RetrainTrigger:
    """
    Periodically checks if enough analyst feedback has accumulated to
    trigger a model retrain.
    """

    def __init__(
        self,
        feedback_store: FeedbackStore,
        ml_model,
        bootstrap_servers: str,
        threshold: int = 100,
        check_interval_secs: int = 300,
    ):
        self._feedback_store = feedback_store
        self._ml_model = ml_model
        self._bootstrap_servers = bootstrap_servers
        self._threshold = threshold
        self._check_interval = check_interval_secs
        self._producer = Producer({"bootstrap.servers": bootstrap_servers})
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_retrain_time: str = datetime.now(timezone.utc).isoformat()

    def start(self) -> None:
        """Start the periodic retrain check in a background thread."""
        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="retrain-trigger"
        )
        self._thread.start()
        logger.info(
            "RetrainTrigger started (threshold=%d, interval=%ds)",
            self._threshold, self._check_interval,
        )

    def _run(self) -> None:
        while self._running:
            try:
                self._check_and_retrain()
            except Exception:
                logger.exception("Error in retrain check")
            time.sleep(self._check_interval)

    def _check_and_retrain(self) -> None:
        """Count feedback since last retrain; if >= threshold, trigger retrain."""
        count = self._feedback_store.get_feedback_count_since(self._last_retrain_time)
        logger.info(
            "Retrain check: %d feedback items since %s (threshold: %d)",
            count, self._last_retrain_time, self._threshold,
        )

        if count < self._threshold:
            return

        logger.info("Feedback threshold reached (%d >= %d), triggering retrain", count, self._threshold)

        # Fetch labeled data
        labeled_data = self._feedback_store.get_labeled_data(self._last_retrain_time)

        if not labeled_data:
            logger.warning("No labeled data available for retraining")
            return

        # Retrain the ML model
        try:
            self._ml_model.retrain_with_feedback(labeled_data)
            logger.info("Model retrained with %d labeled samples", len(labeled_data))
        except Exception:
            logger.exception("Model retraining failed")
            return

        # Update last retrain time
        retrain_time = datetime.now(timezone.utc).isoformat()
        self._last_retrain_time = retrain_time

        # Produce retrain event to Kafka
        try:
            event = {
                "event": "model_retrained",
                "timestamp": retrain_time,
                "samples_used": len(labeled_data),
                "feedback_count": count,
            }
            self._producer.produce(
                TOPIC_RETRAIN_TRIGGER,
                key=b"retrain",
                value=json.dumps(event).encode("utf-8"),
                callback=self._delivery_callback,
            )
            self._producer.poll(0)
            logger.info("Retrain event published to %s", TOPIC_RETRAIN_TRIGGER)
        except Exception:
            logger.exception("Failed to publish retrain event")

    def _delivery_callback(self, err, msg):
        if err:
            logger.error("Retrain event delivery failed: %s", err)
        else:
            logger.debug(
                "Retrain event delivered to %s [%d] @ %d",
                msg.topic(), msg.partition(), msg.offset(),
            )

    def stop(self) -> None:
        """Stop the retrain trigger thread."""
        self._running = False
        self._producer.flush(timeout=5)
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("RetrainTrigger stopped")
