import logging
from datetime import datetime, timezone

from src.models.ab_experiment import ABExperiment
from src.db.repository import ExperimentRepo

logger = logging.getLogger(__name__)


class ExperimentManager:
    """Manages the lifecycle of A/B testing experiments."""

    def __init__(self, experiment_repo: ExperimentRepo):
        self._repo = experiment_repo

    def create_experiment(self, experiment: ABExperiment) -> ABExperiment:
        """Create a new experiment after validation.

        Raises ValueError if traffic_split > 0.5 or another active experiment exists.
        """
        if experiment.traffic_split > 0.5:
            raise ValueError(
                f"traffic_split must be <= 0.5, got {experiment.traffic_split}"
            )

        active = self.list_active_experiments()
        if active:
            raise ValueError(
                f"Cannot create experiment: active experiment '{active[0].experiment_id}' already exists"
            )

        self._repo.insert_experiment(experiment)
        logger.info("Created experiment %s (%s)", experiment.experiment_id, experiment.name)
        return experiment

    def get_experiment(self, experiment_id: str) -> ABExperiment | None:
        """Retrieve an experiment by ID, or None if not found."""
        return self._repo.get_experiment(experiment_id)

    def list_active_experiments(self) -> list[ABExperiment]:
        """Return all experiments with status 'active'."""
        return self._repo.list_active()

    def update_status(self, experiment_id: str, status: str) -> None:
        """Update the status of an experiment."""
        self._repo.update_status(experiment_id, status)
        logger.info("Experiment %s status -> %s", experiment_id, status)

    def promote_challenger(self, experiment_id: str) -> None:
        """Mark experiment as completed."""
        self._repo.update_status(experiment_id, "completed")
        logger.info("Experiment %s promoted challenger, marked completed", experiment_id)
