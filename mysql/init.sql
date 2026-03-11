-- =============================================================================
-- init.sql -- Fraud AI Streaming Database Schema
-- =============================================================================
-- Runs ONCE on first container start via /docker-entrypoint-initdb.d/
-- =============================================================================

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id   VARCHAR(64) PRIMARY KEY,
    user_id          VARCHAR(64) NOT NULL,
    amount           DECIMAL(12, 2) NOT NULL,
    currency         VARCHAR(3) NOT NULL DEFAULT 'USD',
    timestamp        VARCHAR(64) NOT NULL,
    merchant_id      VARCHAR(64) NOT NULL,
    location         VARCHAR(64) NOT NULL,
    device_id        VARCHAR(64) NOT NULL,
    ip_address       VARCHAR(45) NOT NULL,
    created_at       DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    INDEX idx_transactions_user (user_id),
    INDEX idx_transactions_timestamp (timestamp),
    INDEX idx_transactions_device (device_id),
    INDEX idx_transactions_ip (ip_address)
);

CREATE TABLE IF NOT EXISTS fraud_results (
    transaction_id        VARCHAR(64) PRIMARY KEY,
    is_fraud              BOOLEAN NOT NULL,
    score                 DECIMAL(5, 4) NOT NULL,
    reasons               JSON NOT NULL,
    rule_triggered        VARCHAR(64),
    model_version         VARCHAR(32) NOT NULL,
    fraud_ring_id         VARCHAR(64),
    llm_summary           TEXT,
    routed_to             VARCHAR(32) NOT NULL,
    scored_at             DATETIME(3) NOT NULL,

    FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id),
    INDEX idx_fraud_results_score (score),
    INDEX idx_fraud_results_routed (routed_to)
);

CREATE TABLE IF NOT EXISTS analyst_feedback (
    feedback_id             VARCHAR(64) PRIMARY KEY,
    transaction_id          VARCHAR(64) NOT NULL,
    analyst_id              VARCHAR(64) NOT NULL,
    verdict                 ENUM('true_positive', 'false_positive', 'false_negative') NOT NULL,
    notes                   TEXT,
    original_score          DECIMAL(5, 4) NOT NULL,
    original_model_version  VARCHAR(32) NOT NULL,
    created_at              DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id),
    INDEX idx_feedback_created (created_at),
    INDEX idx_feedback_verdict (verdict)
);

CREATE TABLE IF NOT EXISTS ab_experiments (
    experiment_id             VARCHAR(64) PRIMARY KEY,
    name                      VARCHAR(128) NOT NULL,
    control_model_version     VARCHAR(32) NOT NULL,
    challenger_model_version  VARCHAR(32) NOT NULL,
    traffic_split             DECIMAL(3, 2) NOT NULL,
    status                    ENUM('active', 'paused', 'completed') NOT NULL DEFAULT 'active',
    start_date                DATETIME(3) NOT NULL,
    end_date                  DATETIME(3),
    created_at                DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    INDEX idx_experiments_status (status),
    CONSTRAINT chk_traffic_split CHECK (traffic_split >= 0.0 AND traffic_split <= 0.5)
);

CREATE TABLE IF NOT EXISTS model_versions (
    version              VARCHAR(32) PRIMARY KEY,
    trained_at           DATETIME(3) NOT NULL,
    training_data_count  INT NOT NULL,
    contamination_param  DECIMAL(3, 2) NOT NULL,
    feedback_count       INT NOT NULL DEFAULT 0,
    is_active            BOOLEAN NOT NULL DEFAULT FALSE,
    notes                TEXT,

    INDEX idx_model_versions_active (is_active)
);

CREATE TABLE IF NOT EXISTS ab_metrics (
    id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
    experiment_id      VARCHAR(64) NOT NULL,
    model_version      VARCHAR(32) NOT NULL,
    transaction_id     VARCHAR(64) NOT NULL,
    score              DECIMAL(5, 4) NOT NULL,
    latency_ms         DECIMAL(8, 2) NOT NULL,
    was_correct        BOOLEAN,
    created_at         DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    FOREIGN KEY (experiment_id) REFERENCES ab_experiments(experiment_id),
    INDEX idx_metrics_experiment (experiment_id, model_version),
    INDEX idx_metrics_transaction (transaction_id)
);

CREATE TABLE IF NOT EXISTS fraud_rings (
    ring_id                VARCHAR(64) PRIMARY KEY,
    shared_resource_type   ENUM('device', 'ip') NOT NULL,
    shared_resource_id     VARCHAR(64) NOT NULL,
    user_ids               JSON NOT NULL,
    risk_score             DECIMAL(5, 4) NOT NULL,
    total_transaction_amount DECIMAL(14, 2) NOT NULL,
    detected_at            DATETIME(3) NOT NULL,

    INDEX idx_rings_resource (shared_resource_type, shared_resource_id),
    INDEX idx_rings_risk (risk_score)
);

-- Seed: initial model version
INSERT INTO model_versions (version, trained_at, training_data_count, contamination_param, is_active, notes)
VALUES ('v1.0', NOW(3), 0, 0.10, TRUE, 'Initial untrained model')
ON DUPLICATE KEY UPDATE version = version;
