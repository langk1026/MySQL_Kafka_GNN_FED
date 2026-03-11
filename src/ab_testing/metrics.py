import logging

from src.db.repository import ExperimentRepo

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects and retrieves prediction metrics for A/B experiments."""

    def __init__(self, experiment_repo: ExperimentRepo):
        self._repo = experiment_repo

    def record_prediction(
        self,
        experiment_id: str,
        model_version: str,
        transaction_id: str,
        score: float,
        latency_ms: float,
    ) -> None:
        """Record a prediction metric for an experiment."""
        self._repo.insert_metric(
            experiment_id=experiment_id,
            model_version=model_version,
            transaction_id=transaction_id,
            score=score,
            latency_ms=latency_ms,
        )

    def record_feedback(self, transaction_id: str, was_correct: bool) -> None:
        """Update a metric record with correctness feedback."""
        self._repo.update_metric_correctness(
            transaction_id=transaction_id,
            was_correct=was_correct,
        )

    def get_experiment_metrics(self, experiment_id: str) -> dict:
        """Retrieve aggregated metrics for an experiment."""
        return self._repo.get_metrics(experiment_id=experiment_id)
