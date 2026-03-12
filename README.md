# MySQL Kafka GNN FED

Real-time fraud detection platform. Transactions stream through Kafka, get scored by three detection layers in sequence, and land in MySQL — all within a single scoring call.

![fraud detector loading up](https://media.giphy.com/media/xT9IgzoKnwFNmISR8I/giphy.gif)

---

## What this is

A modular fraud detection backend that combines rules, machine learning, and graph analysis to score every transaction as it arrives. Analysts review borderline cases, and their feedback feeds directly back into model retraining. No manual retraining steps.

The three detection layers run in order for each transaction:

1. **Rules** — fast, deterministic checks: high amount thresholds, rapid location changes, and velocity counting via ksqlDB (5-minute tumbling window)
2. **Isolation Forest** — unsupervised ML model that flags statistical outliers, auto-retrains when enough analyst feedback accumulates
3. **Graph engine** — builds a NetworkX graph linking users to shared devices and IPs; flags fraud rings when three or more users share a resource

Scores from all three layers combine into a final score. Transactions above 0.8 go straight to block. Between 0.3 and 0.8 they go to the analyst review queue. Below 0.3 they pass through.

An optional Azure OpenAI layer can explain borderline decisions in plain text, but the system runs fine without it.

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
Simulated producer
      |
      v
 Kafka topic: transactions
      |
      +---> ksqlDB: user_velocity (5-min tumbling window)
      |
      v
 FraudConsumer
      |
      v
 ScoringPipeline
      |
      +--- HighAmountRule      (graduated: $2k=0.35, $5k=0.6, $10k=0.9)
      +--- LocationAnomalyRule (rapid location changes across recent history)
      +--- VelocityRule        (queries ksqlDB live per transaction)
      +--- IsolationForest     (ML anomaly score, auto-retrained on feedback)
      +--- FraudGraph          (NetworkX: users sharing device or IP)
      +--- LLMAnalyzer         (optional Azure OpenAI explanation)
      |
      v
  Final score
      |
      +--- > 0.8  --> Block (Kafka: fraud_alerts topic)
      +--- 0.3-0.8 -> Review queue (analyst inbox)
      +--- < 0.3  --> Allow
      |
      v
   MySQL: transactions, fraud_results, fraud_rings
      |
      v
   Analyst review --> feedback_store --> RetrainTrigger
      (100 feedback entries triggers a new IsolationForest fit)
```

---

## Services (docker-compose)

| Service | Port | Purpose |
|---|---|---|
| MySQL | 3306 | Transaction storage, feedback, experiments, model versions |
| Zookeeper | 2181 | Kafka coordination |
| Kafka | 9092 | Event backbone |
| ksqlDB | 8088 | Streaming SQL — velocity aggregation |
| Kafka UI | 8090 | Cluster monitoring |
| Fraud Engine | 8000 | FastAPI + all detection components |

---

## API Routes

| Route | Purpose |
|---|---|
| `GET /health` | Service health |
| `POST /transactions/score` | Score a single transaction |
| `GET /transactions/{id}` | Get transaction + fraud result |
| `GET /review/queue` | Pending analyst review items |
| `POST /review/{id}/feedback` | Submit analyst verdict |
| `GET /experiments` | List A/B experiments |
| `POST /experiments` | Create new experiment |
| `GET /metrics/summary` | Block/challenge/allow rates, queue depth |
| `GET /` | Live monitoring dashboard |

---

## Database Schema

Seven tables in MySQL:

- `transactions` — raw transaction records
- `fraud_results` — score, reasons, model version, LLM summary, routing decision
- `analyst_feedback` — true/false positives/negatives with analyst notes
- `ab_experiments` — control vs challenger model, traffic split, status
- `ab_metrics` — per-transaction score, latency, correctness for each experiment arm
- `model_versions` — training history, contamination param, active flag
- `fraud_rings` — detected rings with shared resource, user list, risk score, total amount

---

## Detection Rules

**HighAmountRule**

| Amount | Score |
|---|---|
| > $10,000 | 0.90 |
| > $5,000 | 0.60 |
| > $2,000 | 0.35 |

**LocationAnomalyRule** — Checks last 5 transactions per user. One location change scores 0.5. Three or more distinct locations in the window scores 0.7.

**VelocityRule** — Live ksqlDB query against a 5-minute tumbling window.

| txn_count | Score |
|---|---|
| 8 - 14 | 0.40 |
| 15 - 24 | 0.60 |
| 25+ | 0.85 |

**FraudGraph** — A user sharing a device or IP with 3+ other users forms a fraud ring. Risk score scales with ring size: `min(user_count / 10, 1.0)`.

---

## Feedback Loop and Retraining

Analysts review transactions in the queue and submit one of three verdicts: `true_positive`, `false_positive`, `false_negative`.

```
Analyst verdict
      |
      v
 feedback_store (Kafka + MySQL)
      |
      v
 RetrainTrigger
 (polls every 5 minutes, fires when feedback_count >= 100)
      |
      v
 IsolationForest.fit() on labeled data
      |
      v
 new model_version row in MySQL, set is_active = TRUE
```

The system keeps running during retraining. The old model continues scoring until the new version is live.

---

## A/B Testing

Create an experiment with a control model version and a challenger. Set a traffic split (max 50%). The `ABRouter` assigns each incoming transaction to an arm and logs score, latency, and correctness to `ab_metrics`. Compare results through the `/experiments` and `/metrics` routes.

---

## Quickstart

```bash
git clone https://github.com/langk1026/MySQL_Kafka_GNN_FED.git
cd MySQL_Kafka_GNN_FED

cp .env.example .env
# Fill in MYSQL_PASSWORD, MYSQL_ROOT_PASSWORD
# Optional: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY

docker compose up -d --build
docker compose logs -f fraud-engine
```

Dashboard available at `http://localhost:8000` once the fraud-engine service is healthy.

Kafka UI at `http://localhost:8090`.

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
| `SCORE_THRESHOLD_FRAUD` | `0.8` | No |
| `SCORE_THRESHOLD_REVIEW` | `0.3` | No |
| `RETRAIN_FEEDBACK_THRESHOLD` | `100` | No |
| `FRAUD_RING_MIN_USERS` | `3` | No |

---

## Known Limitations

- Single Kafka broker — not suitable for production without replication factor > 1
- IsolationForest runs in-process; a high-throughput deployment would want this as a separate service
- FraudGraph is in-memory and resets on restart — production would need a persistent graph store (e.g. Neo4j)
- LLM scoring adds 1-3 seconds per flagged transaction depending on Azure OpenAI latency

---

## Roadmap

- [ ] Persist FraudGraph to Neo4j
- [ ] Replace IsolationForest with an online learning model (e.g. River)
- [ ] Add GNN layer using PyTorch Geometric on the fraud ring graph
- [ ] Kafka Schema Registry + Avro serialization
- [ ] Prometheus metrics endpoint + Grafana dashboard

---
