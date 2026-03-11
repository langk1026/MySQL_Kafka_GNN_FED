import logging

from src.llm.client import AzureOpenAIClient
from src.llm.prompts import (
    TRANSACTION_ANALYSIS_SYSTEM,
    RING_ANALYSIS_SYSTEM,
    build_transaction_prompt,
    build_ring_prompt,
)
from src.models import Transaction, FraudRing

logger = logging.getLogger(__name__)


class LLMAnalyzer:
    """Uses Azure OpenAI to generate fraud analysis summaries."""

    def __init__(self, client: AzureOpenAIClient, enabled: bool = True):
        self._client = client
        self._enabled = enabled
        logger.info("LLMAnalyzer initialized (enabled=%s)", enabled)

    def analyze(self, transaction: Transaction, reasons: list[str]) -> str | None:
        """Convenience method called by ScoringPipeline with reason strings."""
        rule_scores = {}
        for reason in reasons:
            parts = reason.split(":", 1)
            if len(parts) == 2:
                rule_scores[parts[0].strip()] = 1.0
        return self.analyze_transaction(transaction, rule_scores, 0.0)

    def analyze_transaction(
        self,
        transaction: Transaction,
        rule_scores: dict[str, float],
        ml_score: float,
    ) -> str | None:
        """
        Analyze a suspicious transaction using the LLM.
        Returns an analysis summary string, or None if LLM is disabled.
        """
        if not self._enabled:
            logger.debug("LLM disabled, skipping transaction analysis for %s", transaction.transaction_id)
            return None

        try:
            user_prompt = build_transaction_prompt(transaction, rule_scores, ml_score)
            summary = self._client.chat(
                system_prompt=TRANSACTION_ANALYSIS_SYSTEM,
                user_prompt=user_prompt,
            )
            logger.info(
                "LLM analysis completed for tx %s (%d chars)",
                transaction.transaction_id, len(summary),
            )
            return summary
        except Exception:
            logger.exception(
                "LLM analysis failed for tx %s", transaction.transaction_id
            )
            return None

    def analyze_ring(
        self,
        ring: FraudRing,
        member_transactions: list[Transaction],
    ) -> str:
        """
        Analyze a potential fraud ring using the LLM.
        Returns an investigation narrative.
        """
        if not self._enabled:
            logger.debug("LLM disabled, returning default ring analysis for %s", ring.ring_id)
            return (
                f"LLM analysis disabled. Fraud ring {ring.ring_id} detected with "
                f"{len(ring.user_ids)} members sharing {ring.shared_resource_type} "
                f"'{ring.shared_resource_id}'. Risk score: {ring.risk_score:.3f}. "
                f"Total amount: {ring.total_transaction_amount:.2f}."
            )

        try:
            user_prompt = build_ring_prompt(ring, member_transactions)
            narrative = self._client.chat(
                system_prompt=RING_ANALYSIS_SYSTEM,
                user_prompt=user_prompt,
            )
            logger.info(
                "LLM ring analysis completed for ring %s (%d chars)",
                ring.ring_id, len(narrative),
            )
            return narrative
        except Exception:
            logger.exception("LLM ring analysis failed for ring %s", ring.ring_id)
            return (
                f"LLM analysis failed. Fraud ring {ring.ring_id} detected with "
                f"{len(ring.user_ids)} members sharing {ring.shared_resource_type} "
                f"'{ring.shared_resource_id}'. Risk score: {ring.risk_score:.3f}."
            )
