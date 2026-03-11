from dataclasses import dataclass, asdict


@dataclass
class AnalystFeedback:
    feedback_id: str
    transaction_id: str
    analyst_id: str
    verdict: str  # "true_positive" | "false_positive" | "false_negative"
    notes: str
    original_score: float
    original_model_version: str
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AnalystFeedback":
        return cls(
            feedback_id=data["feedback_id"],
            transaction_id=data["transaction_id"],
            analyst_id=data["analyst_id"],
            verdict=data["verdict"],
            notes=data.get("notes", ""),
            original_score=float(data["original_score"]),
            original_model_version=data["original_model_version"],
            created_at=data["created_at"],
        )
