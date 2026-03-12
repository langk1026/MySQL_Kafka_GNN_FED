# MySQL Kafka GNN FED

Real-time fraud detection platform. Kafka streams transactions through ksqlDB velocity aggregation, then a multi-layer scoring pipeline classifies each alert and routes it to block, review, or allow.

---

## What this is

The system operates on **pre-aggregated velocity windows** rather than individual transactions. ksqlDB maintains four 1-hour tumbling aggregation tables — one each for IP, user, device, and merchant — and emits alerts when any dimension exceeds its threshold. The scoring pipeline consumes those alerts, not raw transactions.

This mirrors how production fraud systems work: flagging entities with abnormal velocity is more reliable than scoring each individual transaction in isolation.

The pipeline layers:

1. **VelocityAlertRule** — tiered severity per dimension. IP ≥60 txns/h triggers at severity 60; ≥80 at 80; ≥100 at 95. USER and DEVICE share the same tiers at lower thresholds (30/45/60). MERCHANT thresholds are higher (150/200/300).
2. **HighWindowAmountRule** — flags windows with total transaction amounts above $10k (severity 50), $20k (70), or $50k (90).
3. **BlacklistRule** — immediate severity 100 if the dimension key is on the blocklist.
4. **Isolation Forest** — anomaly score derived from window-level features (txn_count, total_amount, window duration, amount per txn). Auto-retrains when enough feedback accumulates.
5. **FraudGraph** — NetworkX graph linking users to shared devices and IPs. Three or more users sharing a resource form a fraud ring.

Scores from all layers aggregate via **probabilistic union** (1 − ∏(1 − sᵢ/100)), matching the production FED scoring formula. Final score is on a 0–100 integer scale. Above 80 → block. 30–80 → analyst review. Below 30 → allow.

Analyst verdicts feed back into automatic ML retraining. No manual steps.

---

## Stack

| Layer | Technology |
|---|---|
| Event streaming | Apache Kafka (Confluent 7.5) |
| Streaming SQL | ksqlDB 0.29 |
| Database | MySQL 8.0 |
| ML model | scikit-learn Isolation Forest |
| Graph detection | NetworkX |
| API | FastAPI |
| LLM (optional) | Azure OpenAI (gpt-4o) |
| Frontend | Vanilla JS dashboard |
| Infrastructure | Docker Compose (6 services) |

---

## Architecture

```
seed.py / SimulatedProducer
         |
         v
  Kafka topic: transactions
         |
         v
  ksqlDB 1h tumbling windows (4 dimensions)
         |
    +----+----+----+
    |    |    |    |
   IP  USER DEV MERCH    (FED_velocity_table_*_1h)
    |    |    |    |
  alert stream per dimension
  (threshold filters)
    |    |    |    |
    +----+----+----+
         |
         v
  FED_velocity_stream_alerts_all
  (fan-in via INSERT INTO)
         |
         v
  FraudConsumer
  (normalises ksqlDB UPPERCASE keys to lowercase)
         |
         v
  ScoringPipeline.score_alert()
         |
    +----+----+----+----+----+
    |                        |
  VelocityAlertRule        BlacklistRule
  HighWindowAmountRule     IsolationForest
                           FraudGraph
    |
    v
  probabilistic union  →  score 0-100
         |
    +---------+---------+
    |         |         |
  >=80      30-80      <30
  block    review     allow
    |         |
    v         v
  MySQL: fraud_results
         |
         v
  Analyst review → FeedbackStore → RetrainTrigger
  (fires at 100 labeled entries → new IsolationForest version)
```

---

## ksqlDB Velocity Windows

Four 1-hour tumbling aggregation tables run continuously:

| Table | Dimension | Alert thresholds (txn_count → severity) |
|---|---|---|
| `FED_velocity_table_ip_1h` | IP address | ≥60→60, ≥80→80, ≥100→95 |
| `FED_velocity_table_user_1h` | User ID | ≥30→60, ≥45→80, ≥60→95 |
| `FED_velocity_table_device_1h` | Device ID | ≥30→60, ≥45→80, ≥60→95 |
| `FED_velocity_table_merchant_1h` | Merchant ID | ≥150→60, ≥200→80, ≥300→95 |

Each table feeds a per-dimension alert stream. All four alert streams fan into `FED_velocity_stream_alerts_all` via `INSERT INTO` (ksqlDB's `UNION ALL` workaround). The `FraudConsumer` subscribes to this unified topic.

---

## Detection Rules

**VelocityAlertRule** — reads `dimension` and `txn_count` from the alert.

| Dimension | txn_count | Severity |
|---|---|---|
| IP | ≥ 100 | 95 |
| IP | ≥ 80 | 80 |
| IP | ≥ 60 | 60 |
| USER / DEVICE | ≥ 60 | 95 |
| USER / DEVICE | ≥ 45 | 80 |
| USER / DEVICE | ≥ 30 | 60 |
| MERCHANT | ≥ 300 | 95 |
| MERCHANT | ≥ 200 | 80 |
| MERCHANT | ≥ 150 | 60 |

**HighWindowAmountRule** — reads `total_amount` from the window.

| total_amount | Severity |
|---|---|
| ≥ $50,000 | 90 |
| ≥ $20,000 | 70 |
| ≥ $10,000 | 50 |

**BlacklistRule** — checks `dimension_key` against an in-memory set. Severity 100 on match. Add entries via `BlacklistRule.add("10.99.0.99")`.

**Score aggregation** — probabilistic union: `score = round((1 − ∏(1 − sᵢ/100)) × 100)`.

Two rules at severity 60 each → score 84. One rule at 95 → score 95.

---

## Services (docker-compose)

| Service | Port | Purpose |
|---|---|---|
| MySQL | 3306 | Transaction storage, feedback, experiments, model versions |
| Zookeeper | 2181 | Kafka coordination |
| Kafka | 9092 | Event backbone |
| ksqlDB | 8088 | Streaming SQL — 4-dimension velocity aggregation |
| Kafka UI | 8090 | Cluster monitoring |
| Fraud Engine | 8000 | FastAPI + all detection components |

---

## API Routes

| Route | Purpose |
|---|---|
| `GET /health` | Service health |
| `POST /transactions/score` | Score a single transaction (single-transaction estimate) |
| `GET /transactions/{id}` | Get stored transaction and fraud result |
| `GET /review/queue` | Pending analyst review items |
| `POST /review/{id}/feedback` | Submit analyst verdict |
| `GET /experiments` | List A/B experiments |
| `POST /experiments` | Create new experiment |
| `GET /metrics/summary` | Block/review/allow rates, queue depth |
| `GET /` | Live monitoring dashboard |

---

## Database Schema

Seven tables in MySQL:

- `transactions` — raw transaction records
- `fraud_results` — score (0-100), triggered rules, routing decision, model version
- `analyst_feedback` — true/false positives/negatives with analyst notes
- `ab_experiments` — control vs challenger model, traffic split, status
- `ab_metrics` — per-alert score, latency, correctness per experiment arm
- `model_versions` — training history, contamination param, active flag
- `fraud_rings` — detected rings with shared resource, user list, risk score, total amount

---

## Feedback Loop and Retraining

```
Analyst verdict (true_positive / false_positive / false_negative)
      |
      v
 FeedbackStore (Kafka + MySQL)
      |
      v
 RetrainTrigger
 (polls every 5 minutes, fires when feedback_count >= 100)
      |
      v
 IsolationForest.fit() on window-level alert features
 (txn_count, total_amount, duration_min, amount_per_txn)
      |
      v
 new model_version in MySQL, set is_active = TRUE
```

The old model continues scoring until the new version is live.

---

## A/B Testing

Create an experiment with a control and challenger model version. Set a traffic split (max 50%). `ABRouter` assigns each alert to an arm deterministically by hashing `dimension_key`. Scores, latency, and correctness are logged to `ab_metrics`.

---

## Quickstart

```bash
git clone https://github.com/langk1026/MySQL_Kafka_GNN_FED.git
cd MySQL_Kafka_GNN_FED

cp .env.example .env
# Set MYSQL_PASSWORD, MYSQL_ROOT_PASSWORD
# Optional: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY

docker compose up -d --build
docker compose logs -f fraud-engine
```

Dashboard at `http://localhost:8000`. Kafka UI at `http://localhost:8090`.

### Testing velocity alerts without Docker

```bash
# Preview transactions without producing
python seed.py --dry-run

# Produce continuously (triggers USER/DEVICE alerts in ~3 min)
python seed.py

# Faster — all 4 dimension alerts within ~5 min
python seed.py --rate 20 --interval 3
```

---

## Environment Variables

| Variable | Default | Required |
|---|---|---|
| `MYSQL_PASSWORD` | — | Yes |
| `MYSQL_ROOT_PASSWORD` | — | Yes |
| `MYSQL_DATABASE` | `fraud_db` | No |
| `AZURE_OPENAI_ENDPOINT` | — | No |
| `AZURE_OPENAI_API_KEY` | — | No |
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-4o` | No |
| `LLM_ENABLED` | `true` | No |
| `SCORE_THRESHOLD_FRAUD` | `80` | No |
| `SCORE_THRESHOLD_REVIEW` | `30` | No |
| `RETRAIN_FEEDBACK_THRESHOLD` | `100` | No |
| `FRAUD_RING_MIN_USERS` | `3` | No |

---

## Known Limitations

- Single Kafka broker — not suitable for production without replication factor > 1
- IsolationForest runs in-process; high throughput would need it as a separate service
- FraudGraph is in-memory and resets on restart — production would need a persistent graph store (Neo4j or similar)
- `POST /transactions/score` builds a synthetic single-transaction alert. Real scoring uses the ksqlDB velocity pipeline.
- BlacklistRule uses an in-memory set — entries are lost on restart without a backing store

---

## Roadmap

- [ ] Persist FraudGraph to Neo4j
- [ ] Replace IsolationForest with an online learning model (River)
- [ ] Add GNN layer using PyTorch Geometric on the fraud ring graph
- [ ] Kafka Schema Registry + Avro serialization
- [ ] Prometheus metrics endpoint + Grafana dashboard
- [ ] Persistent blacklist backed by Redis or MySQL
