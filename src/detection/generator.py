import random
import uuid
from datetime import datetime, timezone

from src.models.transaction import Transaction


class TransactionGenerator:
    """Generates simulated transactions for testing and development.

    Each user has a stable home location, primary device, and IP range.
    Most transactions are normal; a small fraction exhibit anomalous behaviour
    (location jumps, device changes, high amounts) to produce a realistic
    mix of Approved / Challenge / Block decisions.
    """

    LOCATIONS = ["US", "IN", "UK", "CA", "AU", "DE", "JP"]

    # ~5% of users are designated as suspicious (more varied behaviour)
    SUSPICIOUS_USER_IDS = {f"User_{i}" for i in [13, 27, 42, 66, 88]}

    def __init__(self):
        self.users = [f"User_{i}" for i in range(1, 101)]
        self.merchants = [f"Merch_{i}" for i in range(1, 21)]
        self.devices = [f"Dev_{i}" for i in range(1, 51)]
        self.ips = [f"192.168.1.{i}" for i in range(1, 256)]

        # Assign each user a UNIQUE device and IP so normal users don't
        # accidentally form fraud rings.  Only suspicious users share
        # resources to create genuinely detectable rings.
        rng = random.Random(42)  # deterministic for reproducibility
        self._user_profiles: dict[str, dict] = {}
        for idx, user in enumerate(self.users):
            self._user_profiles[user] = {
                "home_location": rng.choice(self.LOCATIONS),
                "primary_device": f"Dev_{user}",                   # unique per user
                "primary_ip": f"10.0.{idx // 256}.{idx % 256}",   # unique per user
            }

        # Suspicious users intentionally share a device + IP → real fraud ring
        shared_device = "Dev_SHARED_1"
        shared_ip = "10.99.0.1"
        for sus_user in self.SUSPICIOUS_USER_IDS:
            self._user_profiles[sus_user]["primary_device"] = shared_device
            self._user_profiles[sus_user]["primary_ip"] = shared_ip

    def generate(self) -> Transaction:
        """Generate a single transaction with realistic patterns."""
        user = random.choice(self.users)
        profile = self._user_profiles[user]
        is_suspicious = user in self.SUSPICIOUS_USER_IDS

        # --- Amount ---
        if is_suspicious:
            # Suspicious users: wider range, occasionally very high
            r = random.random()
            if r < 0.3:
                amount = round(random.uniform(5000, 20000), 2)  # high
            elif r < 0.5:
                amount = round(random.uniform(1000, 5000), 2)   # medium
            else:
                amount = round(random.uniform(10, 500), 2)      # normal
        else:
            # Normal users: mostly small, rare medium
            r = random.random()
            if r < 0.02:
                amount = round(random.uniform(5000, 15000), 2)  # rare high
            elif r < 0.10:
                amount = round(random.uniform(500, 2000), 2)    # occasional medium
            else:
                amount = round(random.uniform(10, 500), 2)      # typical

        # --- Location ---
        if is_suspicious:
            # Suspicious users jump locations ~40% of the time
            if random.random() < 0.4:
                location = random.choice([l for l in self.LOCATIONS if l != profile["home_location"]])
            else:
                location = profile["home_location"]
        else:
            # Normal users stay home ~90% of the time
            if random.random() < 0.10:
                location = random.choice([l for l in self.LOCATIONS if l != profile["home_location"]])
            else:
                location = profile["home_location"]

        # --- Device ---
        if is_suspicious and random.random() < 0.3:
            device_id = random.choice(self.devices)
        else:
            device_id = profile["primary_device"]

        # --- IP ---
        if is_suspicious and random.random() < 0.3:
            ip_address = random.choice(self.ips)
        else:
            ip_address = profile["primary_ip"]

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
