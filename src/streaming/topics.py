import logging
import time

import httpx
from confluent_kafka.admin import AdminClient, NewTopic

logger = logging.getLogger(__name__)

TOPIC_TRANSACTIONS = "transactions"
TOPIC_FRAUD_ALERTS = "fraud-alerts"
TOPIC_HUMAN_REVIEW = "human-review"
TOPIC_APPROVED = "approved-transactions"
TOPIC_ANALYST_FEEDBACK = "analyst-feedback"
TOPIC_RETRAIN_TRIGGER = "model-retrain-trigger"
TOPIC_FRAUD_RINGS = "fraud-rings-detected"

ALL_TOPICS: dict[str, int] = {
    TOPIC_TRANSACTIONS: 3,
    TOPIC_FRAUD_ALERTS: 3,
    TOPIC_HUMAN_REVIEW: 3,
    TOPIC_APPROVED: 3,
    TOPIC_ANALYST_FEEDBACK: 3,
    TOPIC_RETRAIN_TRIGGER: 1,
    TOPIC_FRAUD_RINGS: 1,
}


def ensure_topics(bootstrap_servers: str) -> None:
    """Create all required Kafka topics if they do not already exist."""
    admin = AdminClient({"bootstrap.servers": bootstrap_servers})

    existing_topics = set(admin.list_topics(timeout=10).topics.keys())

    new_topics = []
    for topic_name, num_partitions in ALL_TOPICS.items():
        if topic_name not in existing_topics:
            new_topics.append(
                NewTopic(topic_name, num_partitions=num_partitions, replication_factor=1)
            )

    if not new_topics:
        logger.info("All topics already exist.")
        return

    futures = admin.create_topics(new_topics)
    for topic_name, future in futures.items():
        try:
            future.result()  # block until topic is created
            logger.info("Created topic '%s'", topic_name)
        except Exception as exc:
            logger.error("Failed to create topic '%s': %s", topic_name, exc)


_KSQL_STREAM = """
CREATE STREAM IF NOT EXISTS transactions_stream (
    transaction_id VARCHAR,
    user_id VARCHAR,
    amount DOUBLE,
    currency VARCHAR,
    `timestamp` VARCHAR,
    merchant_id VARCHAR,
    location VARCHAR,
    device_id VARCHAR,
    ip_address VARCHAR
) WITH (
    KAFKA_TOPIC='transactions',
    VALUE_FORMAT='JSON'
);
"""

_KSQL_TABLE = """
CREATE TABLE IF NOT EXISTS user_velocity AS
    SELECT
        user_id,
        COUNT(*) AS txn_count,
        SUM(amount) AS total_amount
    FROM transactions_stream
    WINDOW TUMBLING (SIZE 5 MINUTES)
    GROUP BY user_id
    EMIT CHANGES;
"""


def setup_ksqldb(ksqldb_url: str, retries: int = 5, delay: float = 5.0) -> None:
    """Submit ksqlDB stream and table creation via REST API with retries."""
    url = f"{ksqldb_url.rstrip('/')}/ksql"
    headers = {"Accept": "application/vnd.ksql.v1+json"}

    for stmt_name, stmt in [("transactions_stream", _KSQL_STREAM), ("user_velocity", _KSQL_TABLE)]:
        for attempt in range(1, retries + 1):
            try:
                resp = httpx.post(
                    url,
                    json={"ksql": stmt, "streamsProperties": {}},
                    headers=headers,
                    timeout=15.0,
                )
                if resp.status_code in (200, 201):
                    logger.info("ksqlDB: created '%s'", stmt_name)
                    break
                # 40001 = stream/table already exists — treat as success
                body = resp.json()
                if isinstance(body, list) and body and body[0].get("@type") == "currentStatus":
                    logger.info("ksqlDB: '%s' already exists", stmt_name)
                    break
                logger.warning(
                    "ksqlDB: attempt %d/%d for '%s' returned %d: %s",
                    attempt, retries, stmt_name, resp.status_code, resp.text[:200],
                )
            except Exception as exc:
                logger.warning(
                    "ksqlDB: attempt %d/%d for '%s' failed: %s",
                    attempt, retries, stmt_name, exc,
                )
            if attempt < retries:
                time.sleep(delay)
        else:
            logger.error("ksqlDB: failed to create '%s' after %d attempts", stmt_name, retries)
