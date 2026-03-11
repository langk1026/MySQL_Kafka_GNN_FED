from dataclasses import dataclass, asdict


@dataclass
class Transaction:
    transaction_id: str
    user_id: str
    amount: float
    currency: str
    timestamp: str  # ISO 8601
    merchant_id: str
    location: str
    device_id: str
    ip_address: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Transaction":
        return cls(
            transaction_id=data["transaction_id"],
            user_id=data["user_id"],
            amount=float(data["amount"]),
            currency=data.get("currency", "USD"),
            timestamp=str(data["timestamp"]),
            merchant_id=data["merchant_id"],
            location=data["location"],
            device_id=data["device_id"],
            ip_address=data["ip_address"],
        )
