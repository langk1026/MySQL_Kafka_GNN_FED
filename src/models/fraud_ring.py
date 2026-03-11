from dataclasses import dataclass, asdict


@dataclass
class FraudRing:
    ring_id: str
    shared_resource_type: str  # "device" | "ip"
    shared_resource_id: str
    user_ids: list[str]
    risk_score: float
    total_transaction_amount: float
    detected_at: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FraudRing":
        return cls(
            ring_id=data["ring_id"],
            shared_resource_type=data["shared_resource_type"],
            shared_resource_id=data["shared_resource_id"],
            user_ids=data["user_ids"],
            risk_score=float(data["risk_score"]),
            total_transaction_amount=float(data["total_transaction_amount"]),
            detected_at=data["detected_at"],
        )
