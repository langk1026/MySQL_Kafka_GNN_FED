import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class Rule(ABC):
    """Base class for velocity-alert fraud-detection rules."""

    @abstractmethod
    def evaluate(self, alert_data: dict) -> dict | None:
        """Evaluate the alert and return a result dict or None.

        Returns a dict with keys:
            rule_id, rule_name, severity (0-100), bucket_id, reason
        or None if the rule did not trigger.
        """
        ...


class VelocityAlertRule(Rule):
    """Tiered severity based on txn_count per dimension.

    Dimension → thresholds (count, severity), highest match wins:
        IP       ≥100→95  ≥80→80  ≥60→60
        USER     ≥60→95   ≥45→80  ≥30→60   (user_id, proxy for identity/email)
        DEVICE   ≥60→95   ≥45→80  ≥30→60   (device_id, proxy for mobile)
        MERCHANT ≥300→95  ≥200→80 ≥150→60
    """

    THRESHOLDS: dict[str, list[tuple[int, int]]] = {
        "IP":       [(100, 95), (80, 80), (60, 60)],
        "USER":     [(60, 95),  (45, 80), (30, 60)],
        "DEVICE":   [(60, 95),  (45, 80), (30, 60)],
        "MERCHANT": [(300, 95), (200, 80), (150, 60)],
    }

    def evaluate(self, alert_data: dict) -> dict | None:
        dimension = (alert_data.get("dimension") or "").upper()
        txn_count = int(alert_data.get("txn_count") or 0)
        thresholds = self.THRESHOLDS.get(dimension)
        if not thresholds:
            return None
        for threshold, severity in thresholds:
            if txn_count >= threshold:
                return {
                    "rule_id":   "velocity_alert",
                    "rule_name": "VelocityAlertRule",
                    "severity":  severity,
                    "bucket_id": f"vel_{dimension.lower()}",
                    "reason":    f"{dimension} txn_count {txn_count} >= {threshold} (sev {severity})",
                }
        return None


class HighWindowAmountRule(Rule):
    """Flag windows with unusually high total transaction amount.

    Thresholds (total_amount, severity):
        ≥50 000 → 90
        ≥20 000 → 70
        ≥10 000 → 50
    """

    THRESHOLDS: list[tuple[float, int]] = [
        (50_000, 90),
        (20_000, 70),
        (10_000, 50),
    ]

    def evaluate(self, alert_data: dict) -> dict | None:
        total = float(alert_data.get("total_amount") or 0)
        for threshold, severity in self.THRESHOLDS:
            if total >= threshold:
                return {
                    "rule_id":   "high_window_amount",
                    "rule_name": "HighWindowAmountRule",
                    "severity":  severity,
                    "bucket_id": "amt",
                    "reason":    f"total_amount {total:,.2f} >= {threshold:,.0f} (sev {severity})",
                }
        return None


class BlacklistRule(Rule):
    """Check dimension_key against an in-memory blacklist.

    In production this queries a database; for the POC it uses a
    class-level set that can be populated via BlacklistRule.add().
    """

    _BLACKLIST: set[str] = set()

    @classmethod
    def add(cls, value: str) -> None:
        cls._BLACKLIST.add(value)

    @classmethod
    def remove(cls, value: str) -> None:
        cls._BLACKLIST.discard(value)

    @classmethod
    def clear(cls) -> None:
        cls._BLACKLIST.clear()

    def evaluate(self, alert_data: dict) -> dict | None:
        key = alert_data.get("dimension_key") or ""
        if key in self._BLACKLIST:
            return {
                "rule_id":   "blacklist",
                "rule_name": "BlacklistRule",
                "severity":  100,
                "bucket_id": "bl",
                "reason":    f"dimension_key {key!r} is blacklisted",
            }
        return None
