-- =============================================================================
-- ksqlDB -- 4-dimension velocity windows (1h tumbling) + fan-in alert stream
-- =============================================================================
-- Architecture (mirrors production FED fraud pipeline):
--
--   transactions_stream  (source, JSON, from 'transactions' Kafka topic)
--          |
--     +-----------+-----------+-----------+
--     |           |           |           |
--   ip_1h     user_1h    device_1h   merchant_1h   (windowed aggregation tables)
--     |           |           |           |
--   ip_alert  user_alert  device_alert  merchant_alert  (threshold filter streams)
--     |           |           |           |
--     +------+----+------+----+           |
--            |                           |
--            +--- INSERT INTO FED_velocity_stream_alerts_all ---+
--                         (unified fan-in alert stream)
--
-- Dimension mapping (POC field → production equivalent):
--   ip_address  → IP      (threshold ≥60 txns/1h)
--   user_id     → USER    (≡ EMAIL/identity, threshold ≥30 txns/1h)
--   device_id   → DEVICE  (≡ MOBILE, threshold ≥30 txns/1h)
--   merchant_id → MERCHANT (threshold ≥150 txns/1h)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Source stream (unchanged schema from original POC)
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- 2. 1-hour tumbling aggregation tables (one per dimension)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS FED_velocity_table_ip_1h AS
SELECT
    ip_address                    AS ip_key,
    AS_VALUE(ip_address)          AS dimension_key,
    COUNT(*)                      AS txn_count,
    SUM(amount)                   AS total_amount,
    WINDOWSTART                   AS window_start,
    WINDOWEND                     AS window_end
FROM transactions_stream
WINDOW TUMBLING (SIZE 1 HOURS)
GROUP BY ip_address
EMIT CHANGES;

CREATE TABLE IF NOT EXISTS FED_velocity_table_user_1h AS
SELECT
    user_id                       AS user_key,
    AS_VALUE(user_id)             AS dimension_key,
    COUNT(*)                      AS txn_count,
    SUM(amount)                   AS total_amount,
    WINDOWSTART                   AS window_start,
    WINDOWEND                     AS window_end
FROM transactions_stream
WINDOW TUMBLING (SIZE 1 HOURS)
GROUP BY user_id
EMIT CHANGES;

CREATE TABLE IF NOT EXISTS FED_velocity_table_device_1h AS
SELECT
    device_id                     AS device_key,
    AS_VALUE(device_id)           AS dimension_key,
    COUNT(*)                      AS txn_count,
    SUM(amount)                   AS total_amount,
    WINDOWSTART                   AS window_start,
    WINDOWEND                     AS window_end
FROM transactions_stream
WINDOW TUMBLING (SIZE 1 HOURS)
GROUP BY device_id
EMIT CHANGES;

CREATE TABLE IF NOT EXISTS FED_velocity_table_merchant_1h AS
SELECT
    merchant_id                   AS merchant_key,
    AS_VALUE(merchant_id)         AS dimension_key,
    COUNT(*)                      AS txn_count,
    SUM(amount)                   AS total_amount,
    WINDOWSTART                   AS window_start,
    WINDOWEND                     AS window_end
FROM transactions_stream
WINDOW TUMBLING (SIZE 1 HOURS)
GROUP BY merchant_id
EMIT CHANGES;

-- ---------------------------------------------------------------------------
-- 3. Per-dimension alert streams (threshold filters)
-- ---------------------------------------------------------------------------
CREATE STREAM IF NOT EXISTS FED_velocity_stream_ip_alert_1h AS
SELECT
    'IP'           AS dimension,
    '1h'           AS window_size,
    dimension_key,
    txn_count,
    total_amount,
    window_start,
    window_end
FROM FED_velocity_table_ip_1h
WHERE ip_key IS NOT NULL AND ip_key != '' AND txn_count >= 60
EMIT CHANGES;

CREATE STREAM IF NOT EXISTS FED_velocity_stream_user_alert_1h AS
SELECT
    'USER'         AS dimension,
    '1h'           AS window_size,
    dimension_key,
    txn_count,
    total_amount,
    window_start,
    window_end
FROM FED_velocity_table_user_1h
WHERE user_key IS NOT NULL AND user_key != '' AND txn_count >= 30
EMIT CHANGES;

CREATE STREAM IF NOT EXISTS FED_velocity_stream_device_alert_1h AS
SELECT
    'DEVICE'       AS dimension,
    '1h'           AS window_size,
    dimension_key,
    txn_count,
    total_amount,
    window_start,
    window_end
FROM FED_velocity_table_device_1h
WHERE device_key IS NOT NULL AND device_key != '' AND txn_count >= 30
EMIT CHANGES;

CREATE STREAM IF NOT EXISTS FED_velocity_stream_merchant_alert_1h AS
SELECT
    'MERCHANT'     AS dimension,
    '1h'           AS window_size,
    dimension_key,
    txn_count,
    total_amount,
    window_start,
    window_end
FROM FED_velocity_table_merchant_1h
WHERE merchant_key IS NOT NULL AND merchant_key != '' AND txn_count >= 150
EMIT CHANGES;

-- ---------------------------------------------------------------------------
-- 4. Unified fan-in alert stream (INSERT INTO workaround for UNION ALL)
-- ---------------------------------------------------------------------------
CREATE STREAM IF NOT EXISTS FED_velocity_stream_alerts_all (
    dimension      VARCHAR,
    window_size    VARCHAR,
    dimension_key  VARCHAR,
    txn_count      BIGINT,
    total_amount   DOUBLE,
    window_start   BIGINT,
    window_end     BIGINT
) WITH (
    KAFKA_TOPIC='FED_velocity_stream_alerts_all',
    VALUE_FORMAT='JSON',
    PARTITIONS=1
);

INSERT INTO FED_velocity_stream_alerts_all
SELECT * FROM FED_velocity_stream_ip_alert_1h EMIT CHANGES;

INSERT INTO FED_velocity_stream_alerts_all
SELECT * FROM FED_velocity_stream_user_alert_1h EMIT CHANGES;

INSERT INTO FED_velocity_stream_alerts_all
SELECT * FROM FED_velocity_stream_device_alert_1h EMIT CHANGES;

INSERT INTO FED_velocity_stream_alerts_all
SELECT * FROM FED_velocity_stream_merchant_alert_1h EMIT CHANGES;
