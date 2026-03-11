from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.ab_testing.experiment import ExperimentManager
from src.models.transaction import Transaction

if TYPE_CHECKING:
    from src.detection.ml_model import IsolationForestModel

logger = logging.getLogger(__name__)


class ABRouter:
    """Routes transactions to control or challenger models based on active A/B experiments."""

    def __init__(
        self,
        experiment_manager: ExperimentManager,
        models: dict[str, "IsolationForestModel"],
    ):
        self._experiment_manager = experiment_manager
        self._models = models

    def route(self, transaction: Transaction) -> "IsolationForestModel":
        """Determine which model should score this transaction.

        Uses a deterministic hash of the transaction_id to decide routing:
        - If hash value < experiment.traffic_split -> challenger model
        - Otherwise -> control model
        - If no active experiment -> first model in dict (default)
        """
        active_experiments = self._experiment_manager.list_active_experiments()

        if not active_experiments:
            # No active experiment: return the default (first) model
            return next(iter(self._models.values()))

        experiment = active_experiments[0]
        hash_value = hash(transaction.transaction_id) % 10000 / 10000.0

        if hash_value < experiment.traffic_split:
            # Route to challenger
            model = self._models.get(experiment.challenger_model_version)
            if model is not None:
                return model
            logger.warning(
                "Challenger model version '%s' not found, falling back to control",
                experiment.challenger_model_version,
            )

        # Route to control (or fallback)
        model = self._models.get(experiment.control_model_version)
        if model is not None:
            return model

        # Ultimate fallback: first model
        return next(iter(self._models.values()))

    def get_model_version(self, transaction: Transaction) -> str:
        """Return the version string of the model that would be used for this transaction."""
        model = self.route(transaction)
        return model.version
