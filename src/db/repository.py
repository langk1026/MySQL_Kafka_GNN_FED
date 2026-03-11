import json
import logging

from src.db.connection import get_pool
from src.models import Transaction, FraudResult, AnalystFeedback, ABExperiment

logger = logging.getLogger(__name__)


class TransactionRepo:
    """Repository for transactions and fraud results."""

    def insert_transaction(self, tx: Transaction) -> None:
        pool = get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO transactions
                    (transaction_id, user_id, amount, currency, timestamp,
                     merchant_id, location, device_id, ip_address)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    user_id = VALUES(user_id),
                    amount = VALUES(amount)
                """,
                (
                    tx.transaction_id,
                    tx.user_id,
                    tx.amount,
                    tx.currency,
                    tx.timestamp,
                    tx.merchant_id,
                    tx.location,
                    tx.device_id,
                    tx.ip_address,
                ),
            )
            conn.commit()
            logger.debug("Inserted transaction %s", tx.transaction_id)
        except Exception:
            conn.rollback()
            logger.exception("Failed to insert transaction %s", tx.transaction_id)
            raise
        finally:
            cursor.close()
            conn.close()

    def insert_fraud_result(self, result: FraudResult) -> None:
        pool = get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO fraud_results
                    (transaction_id, is_fraud, score, reasons, rule_triggered,
                     model_version, fraud_ring_id, llm_summary, routed_to, scored_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    is_fraud = VALUES(is_fraud),
                    score = VALUES(score),
                    reasons = VALUES(reasons),
                    routed_to = VALUES(routed_to)
                """,
                (
                    result.transaction_id,
                    result.is_fraud,
                    result.score,
                    json.dumps(result.reasons),
                    result.rule_triggered,
                    result.model_version,
                    result.fraud_ring_id,
                    result.llm_summary,
                    result.routed_to,
                    result.scored_at,
                ),
            )
            conn.commit()
            logger.debug("Inserted fraud result for %s", result.transaction_id)
        except Exception:
            conn.rollback()
            logger.exception("Failed to insert fraud result for %s", result.transaction_id)
            raise
        finally:
            cursor.close()
            conn.close()

    def get_transaction(self, transaction_id: str) -> Transaction | None:
        pool = get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM transactions WHERE transaction_id = %s",
                (transaction_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return Transaction(
                transaction_id=row["transaction_id"],
                user_id=row["user_id"],
                amount=float(row["amount"]),
                currency=row["currency"],
                timestamp=str(row["timestamp"]),
                merchant_id=row["merchant_id"],
                location=row["location"],
                device_id=row["device_id"],
                ip_address=row["ip_address"],
            )
        except Exception:
            logger.exception("Failed to get transaction %s", transaction_id)
            raise
        finally:
            cursor.close()
            conn.close()

    def get_fraud_result(self, transaction_id: str) -> FraudResult | None:
        pool = get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM fraud_results WHERE transaction_id = %s",
                (transaction_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            reasons = row["reasons"]
            if isinstance(reasons, str):
                reasons = json.loads(reasons)
            return FraudResult(
                transaction_id=row["transaction_id"],
                is_fraud=bool(row["is_fraud"]),
                score=float(row["score"]),
                reasons=reasons,
                rule_triggered=row.get("rule_triggered"),
                model_version=row["model_version"],
                fraud_ring_id=row.get("fraud_ring_id"),
                llm_summary=row.get("llm_summary"),
                routed_to=row["routed_to"],
                scored_at=str(row["scored_at"]),
            )
        except Exception:
            logger.exception("Failed to get fraud result for %s", transaction_id)
            raise
        finally:
            cursor.close()
            conn.close()

    def get_user_history(self, user_id: str, limit: int = 100) -> list[Transaction]:
        pool = get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM transactions WHERE user_id = %s ORDER BY timestamp DESC LIMIT %s",
                (user_id, limit),
            )
            rows = cursor.fetchall()
            return [
                Transaction(
                    transaction_id=row["transaction_id"],
                    user_id=row["user_id"],
                    amount=float(row["amount"]),
                    currency=row["currency"],
                    timestamp=str(row["timestamp"]),
                    merchant_id=row["merchant_id"],
                    location=row["location"],
                    device_id=row["device_id"],
                    ip_address=row["ip_address"],
                )
                for row in rows
            ]
        except Exception:
            logger.exception("Failed to get user history for %s", user_id)
            raise
        finally:
            cursor.close()
            conn.close()


class FeedbackRepo:
    """Repository for analyst feedback."""

    def insert_feedback(self, feedback: AnalystFeedback) -> None:
        pool = get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO analyst_feedback
                    (feedback_id, transaction_id, analyst_id, verdict, notes,
                     original_score, original_model_version, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    feedback.feedback_id,
                    feedback.transaction_id,
                    feedback.analyst_id,
                    feedback.verdict,
                    feedback.notes,
                    feedback.original_score,
                    feedback.original_model_version,
                    feedback.created_at,
                ),
            )
            conn.commit()
            logger.debug("Inserted feedback %s", feedback.feedback_id)
        except Exception:
            conn.rollback()
            logger.exception("Failed to insert feedback %s", feedback.feedback_id)
            raise
        finally:
            cursor.close()
            conn.close()

    def count_feedback_since(self, since: str) -> int:
        pool = get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM analyst_feedback WHERE created_at >= %s",
                (since,),
            )
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception:
            logger.exception("Failed to count feedback since %s", since)
            raise
        finally:
            cursor.close()
            conn.close()

    def get_labeled_data_since(self, since: str) -> list[tuple[Transaction, bool]]:
        """
        Join analyst_feedback with transactions.
        true_positive / false_negative -> label True (is fraud)
        false_positive -> label False (not fraud)
        """
        pool = get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT t.*, af.verdict
                FROM analyst_feedback af
                JOIN transactions t ON af.transaction_id = t.transaction_id
                WHERE af.created_at >= %s
                """,
                (since,),
            )
            rows = cursor.fetchall()
            results: list[tuple[Transaction, bool]] = []
            for row in rows:
                tx = Transaction(
                    transaction_id=row["transaction_id"],
                    user_id=row["user_id"],
                    amount=float(row["amount"]),
                    currency=row["currency"],
                    timestamp=str(row["timestamp"]),
                    merchant_id=row["merchant_id"],
                    location=row["location"],
                    device_id=row["device_id"],
                    ip_address=row["ip_address"],
                )
                is_fraud = row["verdict"] in ("true_positive", "false_negative")
                results.append((tx, is_fraud))
            return results
        except Exception:
            logger.exception("Failed to get labeled data since %s", since)
            raise
        finally:
            cursor.close()
            conn.close()


class ExperimentRepo:
    """Repository for A/B experiments and metrics."""

    def insert_experiment(self, exp: ABExperiment) -> None:
        pool = get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO ab_experiments
                    (experiment_id, name, control_model_version, challenger_model_version,
                     traffic_split, status, start_date, end_date, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    exp.experiment_id,
                    exp.name,
                    exp.control_model_version,
                    exp.challenger_model_version,
                    exp.traffic_split,
                    exp.status,
                    exp.start_date,
                    exp.end_date,
                    exp.created_at,
                ),
            )
            conn.commit()
            logger.debug("Inserted experiment %s", exp.experiment_id)
        except Exception:
            conn.rollback()
            logger.exception("Failed to insert experiment %s", exp.experiment_id)
            raise
        finally:
            cursor.close()
            conn.close()

    def get_experiment(self, experiment_id: str) -> ABExperiment | None:
        pool = get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM ab_experiments WHERE experiment_id = %s",
                (experiment_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return ABExperiment(
                experiment_id=row["experiment_id"],
                name=row["name"],
                control_model_version=row["control_model_version"],
                challenger_model_version=row["challenger_model_version"],
                traffic_split=float(row["traffic_split"]),
                status=row["status"],
                start_date=str(row["start_date"]),
                end_date=str(row["end_date"]) if row["end_date"] else None,
                created_at=str(row["created_at"]),
            )
        except Exception:
            logger.exception("Failed to get experiment %s", experiment_id)
            raise
        finally:
            cursor.close()
            conn.close()

    def list_active(self) -> list[ABExperiment]:
        pool = get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM ab_experiments WHERE status = %s", ("active",))
            rows = cursor.fetchall()
            return [
                ABExperiment(
                    experiment_id=row["experiment_id"],
                    name=row["name"],
                    control_model_version=row["control_model_version"],
                    challenger_model_version=row["challenger_model_version"],
                    traffic_split=float(row["traffic_split"]),
                    status=row["status"],
                    start_date=str(row["start_date"]),
                    end_date=str(row["end_date"]) if row["end_date"] else None,
                    created_at=str(row["created_at"]),
                )
                for row in rows
            ]
        except Exception:
            logger.exception("Failed to list active experiments")
            raise
        finally:
            cursor.close()
            conn.close()

    def update_status(self, experiment_id: str, status: str) -> None:
        pool = get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE ab_experiments SET status = %s WHERE experiment_id = %s",
                (status, experiment_id),
            )
            conn.commit()
            logger.info("Updated experiment %s status to %s", experiment_id, status)
        except Exception:
            conn.rollback()
            logger.exception("Failed to update experiment %s status", experiment_id)
            raise
        finally:
            cursor.close()
            conn.close()

    def insert_metric(
        self,
        experiment_id: str,
        model_version: str,
        transaction_id: str,
        score: float,
        latency_ms: float,
    ) -> None:
        pool = get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO ab_metrics
                    (experiment_id, model_version, transaction_id, score, latency_ms)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (experiment_id, model_version, transaction_id, score, latency_ms),
            )
            conn.commit()
            logger.debug(
                "Inserted metric for experiment %s, model %s, tx %s",
                experiment_id, model_version, transaction_id,
            )
        except Exception:
            conn.rollback()
            logger.exception("Failed to insert metric for experiment %s", experiment_id)
            raise
        finally:
            cursor.close()
            conn.close()

    def update_metric_correctness(self, transaction_id: str, was_correct: bool) -> None:
        pool = get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE ab_metrics SET was_correct = %s WHERE transaction_id = %s",
                (was_correct, transaction_id),
            )
            conn.commit()
            logger.debug(
                "Updated correctness for tx %s: %s", transaction_id, was_correct
            )
        except Exception:
            conn.rollback()
            logger.exception(
                "Failed to update metric correctness for tx %s", transaction_id
            )
            raise
        finally:
            cursor.close()
            conn.close()

    def get_metrics(self, experiment_id: str) -> dict:
        """
        Aggregate per model_version: total, correct count, avg latency.
        Return {control: {...}, challenger: {...}}
        """
        pool = get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT
                    m.model_version,
                    COUNT(*) AS total,
                    SUM(CASE WHEN m.was_correct = 1 THEN 1 ELSE 0 END) AS correct_count,
                    AVG(m.latency_ms) AS avg_latency_ms
                FROM ab_metrics m
                WHERE m.experiment_id = %s
                GROUP BY m.model_version
                """,
                (experiment_id,),
            )
            rows = cursor.fetchall()

            # Also get the experiment to map model versions to control/challenger
            cursor.execute(
                "SELECT control_model_version, challenger_model_version FROM ab_experiments WHERE experiment_id = %s",
                (experiment_id,),
            )
            exp_row = cursor.fetchone()
            if exp_row is None:
                return {"control": {}, "challenger": {}}

            control_version = exp_row["control_model_version"]
            challenger_version = exp_row["challenger_model_version"]

            result: dict = {"control": {}, "challenger": {}}
            for row in rows:
                version = row["model_version"]
                stats = {
                    "model_version": version,
                    "total": row["total"],
                    "correct_count": int(row["correct_count"] or 0),
                    "avg_latency_ms": float(row["avg_latency_ms"] or 0),
                }
                if version == control_version:
                    result["control"] = stats
                elif version == challenger_version:
                    result["challenger"] = stats

            return result
        except Exception:
            logger.exception("Failed to get metrics for experiment %s", experiment_id)
            raise
        finally:
            cursor.close()
            conn.close()
