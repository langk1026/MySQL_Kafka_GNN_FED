from dataclasses import dataclass, asdict


@dataclass
class ABExperiment:
    experiment_id: str
    name: str
    control_model_version: str
    challenger_model_version: str
    traffic_split: float  # 0.0-0.5
    status: str  # "active" | "paused" | "completed"
    start_date: str
    end_date: str | None
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ABExperiment":
        return cls(
            experiment_id=data["experiment_id"],
            name=data["name"],
            control_model_version=data["control_model_version"],
            challenger_model_version=data["challenger_model_version"],
            traffic_split=float(data["traffic_split"]),
            status=data["status"],
            start_date=data["start_date"],
            end_date=data.get("end_date"),
            created_at=data["created_at"],
        )
