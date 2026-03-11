from dataclasses import dataclass, asdict


@dataclass
class FraudResult:
    transaction_id: str
    is_fraud: bool
    score: float
    reasons: list[str]
    rule_triggered: str | None
    model_version: str
    fraud_ring_id: str | None
    llm_summary: str | None
    routed_to: str
    scored_at: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FraudResult":
        return cls(
            transaction_id=data["transaction_id"],
            is_fraud=data["is_fraud"],
            score=float(data["score"]),
            reasons=data.get("reasons", []),
            rule_triggered=data.get("rule_triggered"),
            model_version=data["model_version"],
            fraud_ring_id=data.get("fraud_ring_id"),
            llm_summary=data.get("llm_summary"),
            routed_to=data["routed_to"],
            scored_at=data["scored_at"],
        )
