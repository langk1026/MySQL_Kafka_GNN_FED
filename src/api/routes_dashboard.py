import logging

from fastapi import APIRouter

from src.db.connection import get_pool

logger = logging.getLogger(__name__)

router = APIRouter()

_deps: dict = {}


@router.get("/dashboard/data")
def dashboard_data():
    """Aggregate fraud detection data for the frontend dashboard."""
    try:
        pool = get_pool()
        conn = pool.get_connection()
    except Exception:
        return _empty_payload("Database not available")

    try:
        cursor = conn.cursor(dictionary=True)

        # --- KPIs ---
        cursor.execute("SELECT COUNT(*) AS cnt FROM transactions")
        total_scanned = (cursor.fetchone() or {}).get("cnt", 0)

        cursor.execute("SELECT COUNT(*) AS cnt FROM fraud_results WHERE is_fraud = 1")
        fraud_count = (cursor.fetchone() or {}).get("cnt", 0)

        cursor.execute("SELECT COUNT(*) AS cnt FROM fraud_results WHERE routed_to = 'human-review'")
        review_count = (cursor.fetchone() or {}).get("cnt", 0)

        cursor.execute("SELECT AVG(score) AS avg_score FROM fraud_results")
        avg_score = float((cursor.fetchone() or {}).get("avg_score") or 0)

        cursor.execute("SELECT COUNT(*) AS cnt FROM analyst_feedback")
        feedback_count = (cursor.fetchone() or {}).get("cnt", 0)

        high_risk_rate = (fraud_count / total_scanned * 100) if total_scanned > 0 else 0
        false_pos_proxy = ((review_count + fraud_count) / total_scanned * 100) if total_scanned > 0 else 0

        kpis = {
            "transactions_scanned": total_scanned,
            "high_risk_rate_pct": round(high_risk_rate, 2),
            "avg_model_score": round(avg_score, 4),
            "p95_latency_ms": 0,
            "false_positive_proxy_pct": round(false_pos_proxy, 2),
            "model_error_count": 0,
            "risk_threshold": 0.8,
        }

        # --- Score Distribution (10 buckets) ---
        cursor.execute("""
            SELECT
                FLOOR(score * 10) AS bucket,
                COUNT(*) AS cnt
            FROM fraud_results
            GROUP BY FLOOR(score * 10)
            ORDER BY bucket
        """)
        bucket_rows = cursor.fetchall()
        bucket_map = {int(r["bucket"]): int(r["cnt"]) for r in bucket_rows}
        score_distribution = []
        for i in range(10):
            lo = i / 10
            hi = (i + 1) / 10
            score_distribution.append({
                "bucket_label": f"{lo:.1f}-{hi:.1f}",
                "count": bucket_map.get(i, 0),
            })

        # --- Decision Mix ---
        cursor.execute("""
            SELECT routed_to, COUNT(*) AS cnt
            FROM fraud_results
            GROUP BY routed_to
        """)
        route_rows = cursor.fetchall()
        route_map = {r["routed_to"]: int(r["cnt"]) for r in route_rows}
        decision_mix = [
            {"action": "Allow", "count": route_map.get("approved-transactions", 0)},
            {"action": "Block", "count": route_map.get("fraud-alerts", 0)},
            {"action": "Challenge", "count": route_map.get("human-review", 0)},
        ]

        # --- Trend (last 20 minutes, per minute) ---
        cursor.execute("""
            SELECT
                DATE_FORMAT(t.timestamp, '%H:%i') AS minute_label,
                COUNT(*) AS scanned,
                SUM(CASE WHEN fr.is_fraud = 1 THEN 1 ELSE 0 END) AS flagged
            FROM transactions t
            LEFT JOIN fraud_results fr ON t.transaction_id = fr.transaction_id
            GROUP BY minute_label
            ORDER BY minute_label DESC
            LIMIT 20
        """)
        trend_rows = list(reversed(cursor.fetchall()))
        trend = {
            "timestamps": [r["minute_label"] for r in trend_rows],
            "scanned": [int(r["scanned"]) for r in trend_rows],
            "flagged": [int(r["flagged"] or 0) for r in trend_rows],
        }

        # --- Channel Matrix (location as channel proxy) ---
        cursor.execute("""
            SELECT
                t.location AS channel,
                SUM(CASE WHEN fr.routed_to = 'approved-transactions' THEN 1 ELSE 0 END) AS `Allow`,
                SUM(CASE WHEN fr.routed_to = 'fraud-alerts' THEN 1 ELSE 0 END) AS `Block`,
                SUM(CASE WHEN fr.routed_to = 'human-review' THEN 1 ELSE 0 END) AS `Challenge`,
                COUNT(*) AS total
            FROM transactions t
            JOIN fraud_results fr ON t.transaction_id = fr.transaction_id
            GROUP BY t.location
            ORDER BY total DESC
            LIMIT 10
        """)
        channel_matrix = []
        for r in cursor.fetchall():
            channel_matrix.append({
                "channel": r["channel"],
                "Allow": int(r["Allow"]),
                "Block": int(r["Block"]),
                "Challenge": int(r["Challenge"]),
                "total": int(r["total"]),
            })

        # --- Top Risky Merchants ---
        cursor.execute("""
            SELECT
                t.merchant_id AS merchant,
                COUNT(*) AS flagged_count,
                AVG(fr.score) AS avg_score,
                (SUM(CASE WHEN fr.is_fraud = 1 THEN 1 ELSE 0 END) / COUNT(*) * 100) AS high_risk_rate_pct
            FROM transactions t
            JOIN fraud_results fr ON t.transaction_id = fr.transaction_id
            WHERE fr.score >= 0.3
            GROUP BY t.merchant_id
            ORDER BY flagged_count DESC
            LIMIT 10
        """)
        top_merchants = []
        for r in cursor.fetchall():
            top_merchants.append({
                "merchant": r["merchant"],
                "flagged_count": int(r["flagged_count"]),
                "avg_score": round(float(r["avg_score"]), 4),
                "high_risk_rate_pct": round(float(r["high_risk_rate_pct"]), 2),
            })

        # --- Recent Flagged Transactions ---
        cursor.execute("""
            SELECT
                t.timestamp AS event_time,
                t.transaction_id AS tranID,
                t.merchant_id AS merchant,
                t.location AS channel,
                CASE
                    WHEN fr.routed_to = 'fraud-alerts' THEN 'Block'
                    WHEN fr.routed_to = 'human-review' THEN 'Challenge'
                    ELSE 'Allow'
                END AS action,
                fr.score,
                0 AS latency_ms
            FROM transactions t
            JOIN fraud_results fr ON t.transaction_id = fr.transaction_id
            WHERE fr.score >= 0.3
            ORDER BY t.timestamp DESC
            LIMIT 20
        """)
        recent_flagged = []
        for r in cursor.fetchall():
            recent_flagged.append({
                "event_time": str(r["event_time"]),
                "tranID": r["tranID"][:12] + "...",
                "merchant": r["merchant"],
                "channel": r["channel"],
                "action": r["action"],
                "score": round(float(r["score"]), 4),
                "latency_ms": 0,
            })

        cursor.close()
        conn.close()

        from datetime import datetime, timezone
        return {
            "status": "ok",
            "refreshed_at_local": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "kpis": kpis,
            "trend": trend,
            "score_distribution": score_distribution,
            "decision_mix": decision_mix,
            "channel_matrix": channel_matrix,
            "top_risky_merchants": top_merchants,
            "recent_flagged_transactions": recent_flagged,
            "state_note": f"{feedback_count} analyst feedback entries recorded" if feedback_count > 0 else None,
        }

    except Exception as exc:
        logger.exception("Failed to build dashboard data")
        conn.close()
        return _empty_payload(str(exc))


def _empty_payload(error_msg: str) -> dict:
    from datetime import datetime, timezone
    return {
        "status": "error",
        "error_message": error_msg,
        "refreshed_at_local": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "kpis": {},
        "trend": {},
        "score_distribution": [],
        "decision_mix": [],
        "channel_matrix": [],
        "top_risky_merchants": [],
        "recent_flagged_transactions": [],
    }
