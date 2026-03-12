import random
import uuid
from datetime import datetime, timezone

from src.models.transaction import Transaction


# ---------------------------------------------------------------------------
# Fixed fraud dimension keys — reused across transactions so that ksqlDB
# velocity windows accumulate above alert thresholds within one hour.
#
# Trigger times at default SimulatedProducer rate (~1 txn/sec, 100 users):
#   ~10% fraud → ~360 fraud txns/hour per entity
#   USER / DEVICE  thresholds (≥30)  → fires within ~3 min
#   IP             threshold  (≥60)  → fires within ~6 min
#   MERCHANT       threshold  (≥150) → fires within ~15 min
# ---------------------------------------------------------------------------
FRAUD_IP       = "10.99.0.99"
FRAUD_USER     = "User_FRAUD"
FRAUD_DEVICE   = "Dev_FRAUD"
FRAUD_MERCHANT = "Merch_FRAUD"


class TransactionGenerator:
    """Generates simulated transactions for ksqlDB velocity testing.

    Normal users (90%): random but unique IP/device/merchant per user.
    Fraud transactions (10%): reuse fixed FRAUD_* keys across all four
    dimensions simultaneously so every velocity window gets hit.

    A/B split within the fraud 10%:
        5%  → full fraud entity set  (FRAUD_IP + FRAUD_USER + FRAUD_DEVICE + FRAUD_MERCHANT)
        5%  → suspicious-user ring   (User_13/27/42/66/88 sharing Dev_SHARED_1 / 10.99.0.1)
    """

    LOCATIONS = ["US", "IN", "UK", "CA", "AU", "DE", "JP"]

    # Retain original suspicious users for graph/ring detection
    SUSPICIOUS_USER_IDS = {f"User_{i}" for i in [13, 27, 42, 66, 88]}

    def __init__(self):
        self.users    = [f"User_{i}" for i in range(1, 101)]
        self.merchants = [f"Merch_{i}" for i in range(1, 21)]
        self.devices  = [f"Dev_{i}" for i in range(1, 51)]
        self.ips      = [f"192.168.1.{i}" for i in range(1, 256)]

        rng = random.Random(42)
        self._user_profiles: dict[str, dict] = {}
        for idx, user in enumerate(self.users):
            self._user_profiles[user] = {
                "home_location":  rng.choice(self.LOCATIONS),
                "primary_device": f"Dev_{user}",
                "primary_ip":     f"10.0.{idx // 256}.{idx % 256}",
            }

        # Suspicious users share a device + IP → fraud ring detection
        for sus_user in self.SUSPICIOUS_USER_IDS:
            self._user_profiles[sus_user]["primary_device"] = "Dev_SHARED_1"
            self._user_profiles[sus_user]["primary_ip"]     = "10.99.0.1"

    def generate(self) -> Transaction:
        """Generate one transaction.

        Probability breakdown:
            90% → normal user transaction
             5% → velocity fraud (all four FRAUD_* keys)
             5% → suspicious ring user (existing ring detection)
        """
        roll = random.random()

        if roll < 0.05:
            return self._generate_velocity_fraud()
        if roll < 0.10:
            return self._generate_ring_user()
        return self._generate_normal()

    # ------------------------------------------------------------------

    def _generate_normal(self) -> Transaction:
        user    = random.choice(self.users)
        profile = self._user_profiles[user]

        r = random.random()
        if r < 0.02:
            amount = round(random.uniform(5000, 15000), 2)
        elif r < 0.10:
            amount = round(random.uniform(500, 2000), 2)
        else:
            amount = round(random.uniform(10, 500), 2)

        location = (
            random.choice([l for l in self.LOCATIONS if l != profile["home_location"]])
            if random.random() < 0.10 else profile["home_location"]
        )

        return Transaction(
            transaction_id=str(uuid.uuid4()),
            user_id=user,
            amount=amount,
            currency="USD",
            timestamp=datetime.now(timezone.utc).isoformat(),
            merchant_id=random.choice(self.merchants),
            location=location,
            device_id=profile["primary_device"],
            ip_address=profile["primary_ip"],
        )

    def _generate_velocity_fraud(self) -> Transaction:
        """Fraud transaction using all four fixed fraud dimension keys.

        Every call increments the ksqlDB window counter for FRAUD_IP,
        FRAUD_USER, FRAUD_DEVICE, and FRAUD_MERCHANT simultaneously.
        """
        amount = round(random.uniform(500, 8000), 2)
        return Transaction(
            transaction_id=str(uuid.uuid4()),
            user_id=FRAUD_USER,
            amount=amount,
            currency="USD",
            timestamp=datetime.now(timezone.utc).isoformat(),
            merchant_id=FRAUD_MERCHANT,
            location=random.choice(self.LOCATIONS),
            device_id=FRAUD_DEVICE,
            ip_address=FRAUD_IP,
        )

    def _generate_ring_user(self) -> Transaction:
        """Suspicious ring user — shares Dev_SHARED_1 / 10.99.0.1."""
        user    = random.choice(list(self.SUSPICIOUS_USER_IDS))
        profile = self._user_profiles[user]

        r = random.random()
        if r < 0.3:
            amount = round(random.uniform(5000, 20000), 2)
        elif r < 0.5:
            amount = round(random.uniform(1000, 5000), 2)
        else:
            amount = round(random.uniform(10, 500), 2)

        location = (
            random.choice([l for l in self.LOCATIONS if l != profile["home_location"]])
            if random.random() < 0.4 else profile["home_location"]
        )
        device_id  = random.choice(self.devices) if random.random() < 0.3 else profile["primary_device"]
        ip_address = random.choice(self.ips)     if random.random() < 0.3 else profile["primary_ip"]

        return Transaction(
            transaction_id=str(uuid.uuid4()),
            user_id=user,
            amount=amount,
            currency="USD",
            timestamp=datetime.now(timezone.utc).isoformat(),
            merchant_id=random.choice(self.merchants),
            location=location,
            device_id=device_id,
            ip_address=ip_address,
        )
