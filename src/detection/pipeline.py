import logging
from datetime import datetime, timezone

from src.detection.rules import BlacklistRule, HighWindowAmountRule, Rule, VelocityAlertRule
from src.detection.ml_model import IsolationForestModel
from src.fraud_rings.graph_engine import FraudGraph

logger = logging.getLogger(__name__)

# Routing thresholds (0-100 integer scale)
_DEFAULT_FRAUD_THRESHOLD  = 80
_DEFAULT_REVIEW_THRESHOLD = 30


def _probabilistic_union(rule_results: list[dict]) -> int:
    """Aggregate severities using probabilistic union: 1 − ∏(1 − pᵢ/100).

    Mirrors production fed_backend.scoring.calculate_bucketed_fraud_score().
    A single 95-severity rule alone yields score 95.
    Two 60-severity rules yield 1-(0.4*0.4)=84, escalating to block.
    """
    if not rule_results:
        return 0
    product = 1.0
    for r in rule_results:
        product *= 1.0 - r["severity"] / 100.0
    return min(round((1.0 - product) * 100), 100)


class ScoringPipeline:
    """Orchestrates multi-layer fraud scoring for velocity alerts.

    Input:  alert_data dict — {dimension, dimension_key, txn_count,
                               total_amount, window_start, window_end}
    Output: scored result dict — same fields plus score, routing,
                                 triggered_rules, reasons, scored_at
    """

    def __init__(
        self,
        ml_model: IsolationForestModel | None = None,
        graph_engine: FraudGraph | None = None,
        fraud_threshold: int = _DEFAULT_FRAUD_THRESHOLD,
        review_threshold: int = _DEFAULT_REVIEW_THRESHOLD,
    ):
        self._rules: list[Rule] = [VelocityAlertRule(), HighWindowAmountRule()]
        self._blacklist_rule = BlacklistRule()
        self._ml_model = ml_model or IsolationForestModel()
        self._graph_engine = graph_engine
        self._fraud_threshold  = fraud_threshold
        self._review_threshold = review_threshold

    def score_alert(self, alert_data: dict) -> dict:
        """Score a pre-aggregated velocity alert through all detection layers."""
        triggered_rules: list[dict] = []
        reasons: list[str] = []

        # 1. Rule evaluation
        for rule in self._rules:
            result = rule.evaluate(alert_data)
            if result:
                triggered_rules.append(result)
                reasons.append(result["reason"])

        # 2. Blacklist
        bl = self._blacklist_rule.evaluate(alert_data)
        if bl:
            triggered_rules.append(bl)
            reasons.append(bl["reason"])

        # 3. ML anomaly (optional — only active once trained)
        self._ml_model.add_sample(alert_data)
        if self._ml_model.should_retrain():
            self._ml_model.train()

        ml_score = self._ml_model.predict(alert_data)
        if ml_score > 0:
            severity = min(round(ml_score * 100), 100)
            triggered_rules.append({
                "rule_id":   "ml_anomaly",
                "rule_name": "ML Anomaly",
                "severity":  severity,
                "bucket_id": "ml",
            })
            reasons.append(f"ML anomaly score: {ml_score:.2f}")

        # 4. Graph ring detection (optional)
        if self._graph_engine is not None:
            dim_key = alert_data.get("dimension_key", "")
            ring = self._graph_engine.get_ring_for_user(dim_key)
            if ring is not None:
                ring_sev = min(round(ring.risk_score * 100), 100)
                triggered_rules.append({
                    "rule_id":   "fraud_ring",
                    "rule_name": "FraudRing",
                    "severity":  ring_sev,
                    "bucket_id": "ring",
                })
                reasons.append(
                    f"Fraud ring: {len(ring.user_ids)} members share "
                    f"{ring.shared_resource_type} '{ring.shared_resource_id}'"
                )

        # 5. Probabilistic union aggregation
        final_score = _probabilistic_union(triggered_rules)

        # 6. Route
        if final_score >= self._fraud_threshold:
            routing = "block"
        elif final_score >= self._review_threshold:
            routing = "review"
        else:
            routing = "allow"

        return {
            "dimension":      alert_data.get("dimension"),
            "dimension_key":  alert_data.get("dimension_key"),
            "txn_count":      alert_data.get("txn_count"),
            "total_amount":   alert_data.get("total_amount"),
            "window_start":   alert_data.get("window_start"),
            "window_end":     alert_data.get("window_end"),
            "score":          final_score,
            "routing":        routing,
            "triggered_rules": triggered_rules,
            "reasons":        reasons,
            "model_version":  self._ml_model.version,
            "scored_at":      datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }
