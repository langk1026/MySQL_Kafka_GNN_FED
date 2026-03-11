import json
import logging

from confluent_kafka import Producer

from src.db.repository import FeedbackRepo
from src.models import AnalystFeedback, Transaction
from src.streaming.topics import TOPIC_ANALYST_FEEDBACK

logger = logging.getLogger(__name__)


class FeedbackStore:
    """
    Persists analyst feedback to MySQL and publishes to the analyst-feedback
    Kafka topic.
    """

    def __init__(self, feedback_repo: FeedbackRepo, bootstrap_servers: str):
        self._repo = feedback_repo
        self._producer = Producer({"bootstrap.servers": bootstrap_servers})
        logger.info("FeedbackStore initialized")

    def submit_feedback(self, feedback: AnalystFeedback) -> None:
        """Persist feedback to MySQL and produce to Kafka topic."""
        # Persist to database
        self._repo.insert_feedback(feedback)

        # Produce to Kafka
        try:
            value = json.dumps(feedback.to_dict()).encode("utf-8")
            self._producer.produce(
                TOPIC_ANALYST_FEEDBACK,
                key=feedback.transaction_id.encode("utf-8"),
                value=value,
                callback=self._delivery_callback,
            )
            self._producer.poll(0)
            logger.info(
                "Feedback %s for tx %s published to %s",
                feedback.feedback_id, feedback.transaction_id, TOPIC_ANALYST_FEEDBACK,
            )
        except Exception:
            logger.exception(
                "Failed to publish feedback %s to Kafka", feedback.feedback_id
            )

    def get_feedback_count_since(self, since: str) -> int:
        """Get count of feedback entries since a given timestamp."""
        return self._repo.count_feedback_since(since)

    def get_labeled_data(self, since: str) -> list[tuple[Transaction, bool]]:
        """Get labeled training data since a given timestamp."""
        return self._repo.get_labeled_data_since(since)

    def _delivery_callback(self, err, msg):
        if err:
            logger.error("Feedback delivery failed: %s", err)
        else:
            logger.debug(
                "Feedback delivered to %s [%d] @ %d",
                msg.topic(), msg.partition(), msg.offset(),
            )
