"""Seeder script — produces synthetic transactions to Kafka.

Designed to trigger the ksqlDB 1h velocity alert thresholds within minutes
without requiring any database connection. All data is synthetic.

Fraud dimension keys (10% of output):
    ip_address  = 10.99.0.99    → IP     dimension (threshold ≥60/1h)
    user_id     = User_FRAUD    → USER   dimension (threshold ≥30/1h)
    device_id   = Dev_FRAUD     → DEVICE dimension (threshold ≥30/1h)
    merchant_id = Merch_FRAUD   → MERCHANT dimension (threshold ≥150/1h)

Expected trigger times at default settings (--rate 10, --interval 6):
    10 batches/min × 10 txns × 10% = 10 fraud txns/min
    USER / DEVICE  → alert in ~3 min
    IP             → alert in ~6 min
    MERCHANT       → alert in ~15 min

Usage:
    # Preview without producing
    python seed.py --dry-run

    # Run continuously until Ctrl-C
    python seed.py

    # Faster — all thresholds within ~5 min
    python seed.py --rate 20 --interval 3

    # Fixed count then exit
    python seed.py --count 300

    # Produce to a non-default broker
    python seed.py --broker localhost:9092
"""
import argparse
import json
import logging
import random
import signal
import string
import time
import uuid
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("seed")

# ---------------------------------------------------------------------------
# Fraud dimension keys — fixed so ksqlDB windows accumulate predictably
# ---------------------------------------------------------------------------
FRAUD_IP       = "10.99.0.99"
FRAUD_USER     = "User_FRAUD"
FRAUD_DEVICE   = "Dev_FRAUD"
FRAUD_MERCHANT = "Merch_FRAUD"

LOCATIONS = ["US", "IN", "UK", "CA", "AU", "DE", "JP"]

_RUNNING = True


def _on_signal(signum, frame):
    global _RUNNING
    logger.info("Shutdown signal received, stopping after current batch")
    _RUNNING = False


def _rand_str(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


def _build_transaction(is_fraud: bool) -> dict:
    """Build one synthetic transaction dict."""
    now = datetime.now(timezone.utc).isoformat()
    amount = round(random.uniform(10.0, 8000.0) if is_fraud else random.uniform(10.0, 2000.0), 2)
    return {
        "transaction_id": str(uuid.uuid4()),
        "user_id":        FRAUD_USER     if is_fraud else f"User_{random.randint(1, 100)}",
        "amount":         amount,
        "currency":       "USD",
        "timestamp":      now,
        "merchant_id":    FRAUD_MERCHANT if is_fraud else f"Merch_{random.randint(1, 20)}",
        "location":       random.choice(LOCATIONS),
        "device_id":      FRAUD_DEVICE   if is_fraud else f"Dev_{random.randint(1, 50)}",
        "ip_address":     FRAUD_IP       if is_fraud else f"192.168.{random.randint(1,254)}.{random.randint(1,254)}",
    }


def _delivery_callback(err, msg):
    if err:
        logger.error("Delivery failed: %s", err)


def main():
    parser = argparse.ArgumentParser(
        description="Produce synthetic transactions to Kafka for FED velocity testing",
    )
    parser.add_argument("--broker",    default="localhost:9092", help="Kafka bootstrap server (default: localhost:9092)")
    parser.add_argument("--topic",     default="transactions",   help="Kafka topic (default: transactions)")
    parser.add_argument("--rate",      type=int,   default=10,   help="Transactions per batch (default: 10)")
    parser.add_argument("--interval",  type=float, default=6.0,  help="Seconds between batches (default: 6.0)")
    parser.add_argument("--count",     type=int,   default=0,    help="Total transactions then stop; 0=unlimited (default: 0)")
    parser.add_argument("--fraud-pct", type=float, default=10.0, help="Fraud percentage 0-100 (default: 10.0)")
    parser.add_argument("--dry-run",   action="store_true",      help="Print transactions without producing")
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    producer = None
    if not args.dry_run:
        try:
            from confluent_kafka import Producer
            producer = Producer({"bootstrap.servers": args.broker})
        except ImportError:
            logger.error("confluent-kafka not installed. Run: pip install confluent-kafka")
            return

    fraud_threshold = args.fraud_pct / 100.0

    logger.info(
        "Seeder starting: broker=%s topic=%s rate=%d interval=%.1fs fraud=%.0f%% dry_run=%s",
        args.broker, args.topic, args.rate, args.interval, args.fraud_pct, args.dry_run,
    )
    logger.info(
        "Fraud keys — IP: %s  USER: %s  DEVICE: %s  MERCHANT: %s",
        FRAUD_IP, FRAUD_USER, FRAUD_DEVICE, FRAUD_MERCHANT,
    )

    total = 0
    fraud_total = 0
    errors = 0
    batch_num = 0

    while _RUNNING:
        if args.count and total >= args.count:
            break

        batch_fraud = 0

        for _ in range(args.rate):
            if args.count and total >= args.count:
                break

            is_fraud = random.random() < fraud_threshold
            txn = _build_transaction(is_fraud)

            if args.dry_run:
                logger.info(
                    "[DRY-RUN] %s user=%s merchant=%s ip=%s amount=%.2f",
                    "FRAUD" if is_fraud else "normal",
                    txn["user_id"], txn["merchant_id"], txn["ip_address"], txn["amount"],
                )
            else:
                try:
                    producer.produce(
                        args.topic,
                        key=txn["user_id"].encode(),
                        value=json.dumps(txn).encode(),
                        callback=_delivery_callback,
                    )
                    producer.poll(0)
                except Exception:
                    errors += 1
                    logger.exception("Produce failed")

            total += 1
            if is_fraud:
                fraud_total += 1
                batch_fraud += 1

        if not args.dry_run and producer:
            producer.flush(timeout=2)

        batch_num += 1
        logger.info(
            "Batch %d: produced=%d fraud=%d | total=%d fraud=%d (%.1f%%) errors=%d",
            batch_num, args.rate, batch_fraud,
            total, fraud_total,
            100.0 * fraud_total / total if total else 0.0,
            errors,
        )

        if _RUNNING and not (args.count and total >= args.count):
            time.sleep(args.interval)

    if producer:
        producer.flush(timeout=5)

    logger.info(
        "Done. total=%d fraud=%d (%.1f%%) errors=%d",
        total, fraud_total,
        100.0 * fraud_total / total if total else 0.0,
        errors,
    )


if __name__ == "__main__":
    main()
