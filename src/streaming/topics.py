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

# Unified velocity alert stream (fan-in from all 4 dimension alert streams)
TOPIC_VELOCITY_ALERTS = "FED_velocity_stream_alerts_all"

ALL_TOPICS: dict[str, int] = {
    TOPIC_TRANSACTIONS: 3,
    TOPIC_FRAUD_ALERTS: 3,
    TOPIC_HUMAN_REVIEW: 3,
    TOPIC_APPROVED: 3,
    TOPIC_ANALYST_FEEDBACK: 3,
    TOPIC_RETRAIN_TRIGGER: 1,
    TOPIC_FRAUD_RINGS: 1,
    TOPIC_VELOCITY_ALERTS: 1,
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
            future.result()
            logger.info("Created topic '%s'", topic_name)
        except Exception as exc:
            logger.error("Failed to create topic '%s': %s", topic_name, exc)


# ---------------------------------------------------------------------------
# ksqlDB statements — submitted in order at startup
# ---------------------------------------------------------------------------

_KSQL_TRANSACTIONS_STREAM = """
CREATE STREAM IF NOT EXISTS transactions_stream (
    transaction_id VARCHAR,
    user_id        VARCHAR,
    amount         DOUBLE,
    currency       VARCHAR,
    `timestamp`    VARCHAR,
    merchant_id    VARCHAR,
    location       VARCHAR,
    device_id      VARCHAR,
    ip_address     VARCHAR
) WITH (
    KAFKA_TOPIC='transactions',
    VALUE_FORMAT='JSON'
);
"""

_KSQL_TABLE_IP = """
CREATE TABLE IF NOT EXISTS FED_velocity_table_ip_1h AS
SELECT
    ip_address           AS ip_key,
    AS_VALUE(ip_address) AS dimension_key,
    COUNT(*)             AS txn_count,
    SUM(amount)          AS total_amount,
    WINDOWSTART          AS window_start,
    WINDOWEND            AS window_end
FROM transactions_stream
WINDOW TUMBLING (SIZE 1 HOURS)
GROUP BY ip_address
EMIT CHANGES;
"""

_KSQL_TABLE_USER = """
CREATE TABLE IF NOT EXISTS FED_velocity_table_user_1h AS
SELECT
    user_id              AS user_key,
    AS_VALUE(user_id)    AS dimension_key,
    COUNT(*)             AS txn_count,
    SUM(amount)          AS total_amount,
    WINDOWSTART          AS window_start,
    WINDOWEND            AS window_end
FROM transactions_stream
WINDOW TUMBLING (SIZE 1 HOURS)
GROUP BY user_id
EMIT CHANGES;
"""

_KSQL_TABLE_DEVICE = """
CREATE TABLE IF NOT EXISTS FED_velocity_table_device_1h AS
SELECT
    device_id            AS device_key,
    AS_VALUE(device_id)  AS dimension_key,
    COUNT(*)             AS txn_count,
    SUM(amount)          AS total_amount,
    WINDOWSTART          AS window_start,
    WINDOWEND            AS window_end
FROM transactions_stream
WINDOW TUMBLING (SIZE 1 HOURS)
GROUP BY device_id
EMIT CHANGES;
"""

_KSQL_TABLE_MERCHANT = """
CREATE TABLE IF NOT EXISTS FED_velocity_table_merchant_1h AS
SELECT
    merchant_id              AS merchant_key,
    AS_VALUE(merchant_id)    AS dimension_key,
    COUNT(*)                 AS txn_count,
    SUM(amount)              AS total_amount,
    WINDOWSTART              AS window_start,
    WINDOWEND                AS window_end
FROM transactions_stream
WINDOW TUMBLING (SIZE 1 HOURS)
GROUP BY merchant_id
EMIT CHANGES;
"""

_KSQL_ALERT_IP = """
CREATE STREAM IF NOT EXISTS FED_velocity_stream_ip_alert_1h AS
SELECT 'IP' AS dimension, '1h' AS window_size,
       dimension_key, txn_count, total_amount, window_start, window_end
FROM FED_velocity_table_ip_1h
WHERE ip_key IS NOT NULL AND ip_key != '' AND txn_count >= 60
EMIT CHANGES;
"""

_KSQL_ALERT_USER = """
CREATE STREAM IF NOT EXISTS FED_velocity_stream_user_alert_1h AS
SELECT 'USER' AS dimension, '1h' AS window_size,
       dimension_key, txn_count, total_amount, window_start, window_end
FROM FED_velocity_table_user_1h
WHERE user_key IS NOT NULL AND user_key != '' AND txn_count >= 30
EMIT CHANGES;
"""

_KSQL_ALERT_DEVICE = """
CREATE STREAM IF NOT EXISTS FED_velocity_stream_device_alert_1h AS
SELECT 'DEVICE' AS dimension, '1h' AS window_size,
       dimension_key, txn_count, total_amount, window_start, window_end
FROM FED_velocity_table_device_1h
WHERE device_key IS NOT NULL AND device_key != '' AND txn_count >= 30
EMIT CHANGES;
"""

_KSQL_ALERT_MERCHANT = """
CREATE STREAM IF NOT EXISTS FED_velocity_stream_merchant_alert_1h AS
SELECT 'MERCHANT' AS dimension, '1h' AS window_size,
       dimension_key, txn_count, total_amount, window_start, window_end
FROM FED_velocity_table_merchant_1h
WHERE merchant_key IS NOT NULL AND merchant_key != '' AND txn_count >= 150
EMIT CHANGES;
"""

_KSQL_ALERTS_ALL = """
CREATE STREAM IF NOT EXISTS FED_velocity_stream_alerts_all (
    dimension     VARCHAR,
    window_size   VARCHAR,
    dimension_key VARCHAR,
    txn_count     BIGINT,
    total_amount  DOUBLE,
    window_start  BIGINT,
    window_end    BIGINT
) WITH (
    KAFKA_TOPIC='FED_velocity_stream_alerts_all',
    VALUE_FORMAT='JSON',
    PARTITIONS=1
);
"""

_KSQL_INSERT_IP     = "INSERT INTO FED_velocity_stream_alerts_all SELECT * FROM FED_velocity_stream_ip_alert_1h EMIT CHANGES;"
_KSQL_INSERT_USER   = "INSERT INTO FED_velocity_stream_alerts_all SELECT * FROM FED_velocity_stream_user_alert_1h EMIT CHANGES;"
_KSQL_INSERT_DEVICE = "INSERT INTO FED_velocity_stream_alerts_all SELECT * FROM FED_velocity_stream_device_alert_1h EMIT CHANGES;"
_KSQL_INSERT_MERCH  = "INSERT INTO FED_velocity_stream_alerts_all SELECT * FROM FED_velocity_stream_merchant_alert_1h EMIT CHANGES;"

_KSQL_STATEMENTS = [
    ("transactions_stream",               _KSQL_TRANSACTIONS_STREAM),
    ("FED_velocity_table_ip_1h",          _KSQL_TABLE_IP),
    ("FED_velocity_table_user_1h",        _KSQL_TABLE_USER),
    ("FED_velocity_table_device_1h",      _KSQL_TABLE_DEVICE),
    ("FED_velocity_table_merchant_1h",    _KSQL_TABLE_MERCHANT),
    ("FED_velocity_stream_ip_alert_1h",   _KSQL_ALERT_IP),
    ("FED_velocity_stream_user_alert_1h", _KSQL_ALERT_USER),
    ("FED_velocity_stream_device_alert_1h", _KSQL_ALERT_DEVICE),
    ("FED_velocity_stream_merchant_alert_1h", _KSQL_ALERT_MERCHANT),
    ("FED_velocity_stream_alerts_all",    _KSQL_ALERTS_ALL),
    ("insert_ip_into_alerts_all",         _KSQL_INSERT_IP),
    ("insert_user_into_alerts_all",       _KSQL_INSERT_USER),
    ("insert_device_into_alerts_all",     _KSQL_INSERT_DEVICE),
    ("insert_merchant_into_alerts_all",   _KSQL_INSERT_MERCH),
]


def setup_ksqldb(ksqldb_url: str, retries: int = 5, delay: float = 5.0) -> None:
    """Submit all ksqlDB statements via REST API with retries."""
    url = f"{ksqldb_url.rstrip('/')}/ksql"
    headers = {"Accept": "application/vnd.ksql.v1+json"}

    for stmt_name, stmt in _KSQL_STATEMENTS:
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
