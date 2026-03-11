import logging
from datetime import datetime, timezone

from src.models.fraud_result import FraudResult
from src.models.transaction import Transaction
from src.detection.rules import Rule
from src.detection.ml_model import IsolationForestModel
from src.fraud_rings.graph_engine import FraudGraph

logger = logging.getLogger(__name__)

# Default thresholds (overridden if config is provided)
_DEFAULT_FRAUD_THRESHOLD = 0.8
_DEFAULT_REVIEW_THRESHOLD = 0.3


class ScoringPipeline:
    """Central orchestrator that combines rules, ML, graph analysis, and (optionally) LLM."""

    def __init__(
        self,
        rules: list[Rule],
        ml_model: IsolationForestModel,
        graph_engine: FraudGraph,
        llm_analyzer=None,
        ab_router=None,
        fraud_threshold: float = _DEFAULT_FRAUD_THRESHOLD,
        review_threshold: float = _DEFAULT_REVIEW_THRESHOLD,
    ):
        self._rules = rules
        self._ml_model = ml_model
        self._graph_engine = graph_engine
        self._llm_analyzer = llm_analyzer
        self._ab_router = ab_router
        self._fraud_threshold = fraud_threshold
        self._review_threshold = review_threshold
        self._history: dict[str, list[Transaction]] = {}  # user_id -> recent txns

    def score(self, transaction: Transaction) -> FraudResult:
        """Score a transaction through the full detection pipeline."""
        user_id = transaction.user_id
        user_history = self._history.get(user_id, [])

        # --- 1. Rule evaluation ---
        scores: list[float] = []
        reasons: list[str] = []
        triggered_rule: str | None = None

        for rule in self._rules:
            rule_score = rule.evaluate(transaction, user_history)
            if rule_score > 0:
                scores.append(rule_score)
                reasons.append(f"{rule.name}: {rule.description}")
                if rule_score >= self._fraud_threshold:
                    triggered_rule = rule.name

        # --- 2. ML prediction ---
        if self._ab_router is not None:
            # A/B routing: pick the model version the router selects
            model = self._ab_router.route(transaction)
            ml_score = model.predict(transaction)
        else:
            ml_score = self._ml_model.predict(transaction)

        if ml_score > 0:
            scores.append(ml_score)
            reasons.append("ML Anomaly: Machine learning detected unusual pattern")

        # Add training sample for future retraining
        self._ml_model.add_training_sample(transaction)
        if self._ml_model.should_retrain():
            self._ml_model.train()

        # --- 3. Graph analysis ---
        self._graph_engine.add_transaction(transaction)
        ring = self._graph_engine.get_ring_for_user(user_id)
        fraud_ring_id: str | None = None

        if ring is not None:
            scores.append(ring.risk_score)
            reasons.append(
                f"Fraud Ring: {len(ring.user_ids)} users share {ring.shared_resource_type} "
                f"'{ring.shared_resource_id}'"
            )
            fraud_ring_id = ring.ring_id

        # --- 4. Aggregate score ---
        # Use a blend of max and mean so that a single moderate signal
        # doesn't immediately reach the fraud threshold, but multiple
        # moderate signals or one very strong signal still do.
        if scores:
            final_score = 0.6 * max(scores) + 0.4 * (sum(scores) / len(scores))
        else:
            final_score = 0.0

        # --- 5. LLM summary (placeholder for future integration) ---
        llm_summary: str | None = None
        if self._llm_analyzer is not None and final_score >= self._review_threshold:
            try:
                llm_summary = self._llm_analyzer.analyze(transaction, reasons)
            except Exception:
                logger.debug("LLM analysis failed", exc_info=True)

        # --- 6. Determine routing ---
        if final_score >= self._fraud_threshold:
            routed_to = "fraud-alerts"
        elif final_score >= self._review_threshold:
            routed_to = "human-review"
        else:
            routed_to = "approved-transactions"

        # --- 7. Build result ---
        # Ensure native Python types (ML model can return numpy scalars)
        result = FraudResult(
            transaction_id=transaction.transaction_id,
            is_fraud=bool(final_score >= self._fraud_threshold),
            score=round(float(final_score), 4),
            reasons=reasons,
            rule_triggered=triggered_rule,
            model_version=self._ml_model.version,
            fraud_ring_id=fraud_ring_id,
            llm_summary=llm_summary,
            routed_to=routed_to,
            scored_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        )

        # --- 8. Update history (cap at 100 per user) ---
        if user_id not in self._history:
            self._history[user_id] = []
        self._history[user_id].append(transaction)
        if len(self._history[user_id]) > 100:
            self._history[user_id] = self._history[user_id][-100:]

        return result
