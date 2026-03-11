"""Prompt templates for LLM-based fraud analysis."""

from src.models import Transaction, FraudRing

TRANSACTION_ANALYSIS_SYSTEM = """You are a senior fraud analyst AI assistant. Your job is to analyze suspicious financial transactions and provide a concise, actionable summary.

Given a transaction and its fraud detection scores, you should:
1. Assess the overall risk level (LOW, MEDIUM, HIGH, CRITICAL)
2. Explain the key risk indicators
3. Identify any patterns that suggest fraud or legitimate behavior
4. Provide a recommended action (APPROVE, REVIEW, BLOCK)

Be concise and factual. Focus on the most important signals. Use plain language that a human analyst can quickly understand."""

RING_ANALYSIS_SYSTEM = """You are a senior fraud investigator AI assistant specializing in organized fraud ring detection. Your job is to analyze groups of connected users and their transactions to identify coordinated fraud patterns.

Given information about a potential fraud ring, you should:
1. Assess the strength of the connection between ring members
2. Identify coordination patterns (timing, amounts, merchants)
3. Evaluate the likelihood this represents organized fraud vs coincidental shared resources
4. Provide an investigation narrative with recommended next steps

Be thorough but concise. Structure your analysis clearly with sections for each finding."""


def build_transaction_prompt(
    transaction: Transaction,
    rule_scores: dict[str, float],
    ml_score: float,
) -> str:
    """Build a user prompt for transaction analysis."""
    rules_text = "\n".join(
        f"  - {rule}: {score:.3f}" for rule, score in rule_scores.items()
    )

    return f"""Analyze the following transaction for potential fraud:

TRANSACTION DETAILS:
- Transaction ID: {transaction.transaction_id}
- User ID: {transaction.user_id}
- Amount: {transaction.amount} {transaction.currency}
- Timestamp: {transaction.timestamp}
- Merchant: {transaction.merchant_id}
- Location: {transaction.location}
- Device ID: {transaction.device_id}
- IP Address: {transaction.ip_address}

RULE-BASED SCORES:
{rules_text}

ML MODEL SCORE: {ml_score:.3f}

Please provide your fraud risk assessment."""


def build_ring_prompt(
    ring: FraudRing,
    member_transactions: list[Transaction],
) -> str:
    """Build a user prompt for fraud ring analysis."""
    tx_lines = []
    for tx in member_transactions:
        tx_lines.append(
            f"  - TX {tx.transaction_id}: user={tx.user_id}, "
            f"amount={tx.amount} {tx.currency}, merchant={tx.merchant_id}, "
            f"time={tx.timestamp}, device={tx.device_id}, ip={tx.ip_address}"
        )
    tx_text = "\n".join(tx_lines) if tx_lines else "  No transactions available"

    return f"""Analyze the following potential fraud ring:

RING DETAILS:
- Ring ID: {ring.ring_id}
- Shared Resource Type: {ring.shared_resource_type}
- Shared Resource ID: {ring.shared_resource_id}
- Number of Members: {len(ring.user_ids)}
- Member User IDs: {', '.join(ring.user_ids)}
- Total Transaction Amount: {ring.total_transaction_amount:.2f}
- Risk Score: {ring.risk_score:.3f}
- Detected At: {ring.detected_at}

MEMBER TRANSACTIONS:
{tx_text}

Please provide your fraud ring investigation analysis."""
