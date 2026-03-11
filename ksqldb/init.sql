-- =============================================================================
-- ksqlDB -- Streaming SQL for real-time velocity counting
-- =============================================================================
-- Creates a stream over the 'transactions' Kafka topic and a windowed
-- aggregation table that counts transactions per user in 5-minute windows.
-- =============================================================================

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

CREATE TABLE IF NOT EXISTS user_velocity AS
    SELECT
        user_id,
        COUNT(*) AS txn_count,
        SUM(amount) AS total_amount
    FROM transactions_stream
    WINDOW TUMBLING (SIZE 5 MINUTES)
    GROUP BY user_id
    EMIT CHANGES;
