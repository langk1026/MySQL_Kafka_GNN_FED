import logging
import uuid
from datetime import datetime, timezone

import numpy as np
from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)


class IsolationForestModel:
    """Isolation Forest wrapper tuned for velocity-alert feature space.

    Features extracted from an alert_data dict:
        txn_count        — number of transactions in the 1h window
        total_amount     — sum of transaction amounts in the window
        duration_min     — window duration in minutes (window_end - window_start)
        amount_per_txn   — total_amount / txn_count (average spend per transaction)

    These features mirror the production FED scoring model and are more
    meaningful for anomaly detection on pre-aggregated velocity windows
    than raw per-transaction fields.
    """

    def __init__(
        self,
        contamination: float = 0.1,
        min_training_samples: int = 50,
        retrain_interval: int = 200,
    ):
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
    def _extract_features(alert_data: dict) -> list[float]:
        """Extract numerical features from a velocity alert dict."""
        txn_count    = float(alert_data.get("txn_count") or 0)
        total_amount = float(alert_data.get("total_amount") or 0)
        window_start = float(alert_data.get("window_start") or 0)
        window_end   = float(alert_data.get("window_end") or 0)

        duration_ms  = max(window_end - window_start, 1)
        duration_min = duration_ms / 60_000.0
        amount_per_txn = total_amount / txn_count if txn_count > 0 else 0.0

        return [txn_count, total_amount, duration_min, amount_per_txn]

    def add_sample(self, alert_data: dict) -> None:
        """Add an alert to the training buffer."""
        self._training_samples.append(self._extract_features(alert_data))
        self._samples_since_retrain += 1

    # Keep backward-compat alias used by older pipeline code
    def add_training_sample(self, alert_data: dict) -> None:
        self.add_sample(alert_data)

    def should_retrain(self) -> bool:
        if not self._is_trained:
            return len(self._training_samples) >= self._min_training_samples
        return self._samples_since_retrain >= self._retrain_interval

    def train(self) -> None:
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

    def predict(self, alert_data: dict) -> float:
        """Return anomaly score 0.0–1.0. Returns 0.0 if not yet trained."""
        if not self._is_trained:
            return 0.0
        features = np.array([self._extract_features(alert_data)])
        prediction = self._model.predict(features)
        score_samples = self._model.score_samples(features)
        if prediction[0] == -1:
            return min(abs(float(score_samples[0])) / 2.0, 1.0)
        return 0.0

    def retrain_with_feedback(self, labeled_data: list[tuple[dict, bool]]) -> str:
        """Retrain using analyst-labeled alert dicts.

        Args:
            labeled_data: list of (alert_data, is_fraud) tuples.
        Returns:
            New model version string.
        """
        if not labeled_data:
            logger.warning("No labeled data provided for retraining")
            return self._version
        features = np.array([self._extract_features(d) for d, _ in labeled_data])
        self._model = IsolationForest(contamination=self._contamination, random_state=42)
        self._model.fit(features)
        self._is_trained = True
        self._samples_since_retrain = 0
        self._version = f"v{uuid.uuid4().hex[:8]}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        logger.info(
            "Model retrained with %d labeled samples, version=%s",
            len(labeled_data), self._version,
        )
        return self._version
