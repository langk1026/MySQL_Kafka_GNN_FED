import logging
import uuid
from datetime import datetime, timezone

import numpy as np
from sklearn.ensemble import IsolationForest

from src.models.transaction import Transaction

logger = logging.getLogger(__name__)


class IsolationForestModel:
    """Isolation Forest wrapper with version tracking and retraining support."""

    def __init__(self, contamination: float = 0.1, min_training_samples: int = 50, retrain_interval: int = 100):
        self._contamination = contamination
        self._min_training_samples = min_training_samples
        self._retrain_interval = retrain_interval
        self._model = IsolationForest(contamination=contamination, random_state=42)
        self._is_trained = False
        self._training_samples: list[list[float]] = []
        self._samples_since_retrain = 0
        self._version = f"v1-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    @property
    def version(self) -> str:
        return self._version

    @staticmethod
    def _extract_features(transaction: Transaction) -> list[float]:
        """Extract numerical features from a single transaction."""
        return [
            transaction.amount,
            hash(transaction.location) % 1000,
            hash(transaction.device_id) % 1000,
            hash(transaction.ip_address) % 1000,
        ]

    def add_training_sample(self, transaction: Transaction) -> None:
        """Add a transaction to the training buffer."""
        self._training_samples.append(self._extract_features(transaction))
        self._samples_since_retrain += 1

    def should_retrain(self) -> bool:
        """Check whether the model should be retrained."""
        if not self._is_trained:
            return len(self._training_samples) >= self._min_training_samples
        return self._samples_since_retrain >= self._retrain_interval

    def train(self) -> None:
        """Fit the isolation forest on accumulated training samples."""
        if len(self._training_samples) < self._min_training_samples:
            logger.warning(
                "Not enough training samples (%d / %d required)",
                len(self._training_samples),
                self._min_training_samples,
            )
            return

        features = np.array(self._training_samples)
        self._model.fit(features)
        self._is_trained = True
        self._samples_since_retrain = 0
        self._version = f"v{uuid.uuid4().hex[:8]}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        logger.info("Model trained on %d samples, version=%s", len(self._training_samples), self._version)

    def predict(self, transaction: Transaction) -> float:
        """Return an anomaly score between 0.0 and 1.0.

        Returns 0.0 if the model has not been trained yet.
        """
        if not self._is_trained:
            return 0.0

        features = np.array([self._extract_features(transaction)])
        prediction = self._model.predict(features)
        score_samples = self._model.score_samples(features)

        if prediction[0] == -1:
            # Normalize the (negative) score to a 0-1 range
            return min(abs(score_samples[0]) / 2.0, 1.0)
        return 0.0

    def retrain_with_feedback(self, labeled_data: list[tuple[Transaction, bool]]) -> str:
        """Retrain the model using analyst-labeled data.

        Args:
            labeled_data: list of (Transaction, is_fraud) tuples.

        Returns:
            The new model version string.
        """
        if not labeled_data:
            logger.warning("No labeled data provided for retraining")
            return self._version

        features = np.array([self._extract_features(tx) for tx, _ in labeled_data])
        self._model = IsolationForest(contamination=self._contamination, random_state=42)
        self._model.fit(features)
        self._is_trained = True
        self._samples_since_retrain = 0
        self._version = f"v{uuid.uuid4().hex[:8]}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        logger.info(
            "Model retrained with %d labeled samples, version=%s",
            len(labeled_data),
            self._version,
        )
        return self._version
