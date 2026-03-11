import logging

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level dependencies dict populated by main.py during startup.
_deps: dict = {}


@router.get("/metrics")
def get_metrics():
    """
    Simple JSON metrics endpoint.
    Returns: total_transactions, fraud_count, review_count, approved_count,
             feedback_count, active_experiments
    """
    tx_repo = _deps.get("tx_repo")
    feedback_store = _deps.get("feedback_store")
    review_queue = _deps.get("review_queue")
    exp_repo = _deps.get("exp_repo")

    metrics = {
        "total_transactions": 0,
        "fraud_count": 0,
        "review_count": 0,
        "approved_count": 0,
        "feedback_count": 0,
        "active_experiments": 0,
    }

    try:
        if tx_repo is not None:
            from src.db.connection import get_pool
            pool = get_pool()
            conn = pool.get_connection()
            try:
                cursor = conn.cursor()

                cursor.execute("SELECT COUNT(*) FROM transactions")
                row = cursor.fetchone()
                metrics["total_transactions"] = row[0] if row else 0

                cursor.execute("SELECT COUNT(*) FROM fraud_results WHERE is_fraud = 1")
                row = cursor.fetchone()
                metrics["fraud_count"] = row[0] if row else 0

                cursor.execute("SELECT COUNT(*) FROM fraud_results WHERE routed_to = 'human-review'")
                row = cursor.fetchone()
                metrics["review_count"] = row[0] if row else 0

                cursor.execute("SELECT COUNT(*) FROM fraud_results WHERE routed_to = 'approved-transactions'")
                row = cursor.fetchone()
                metrics["approved_count"] = row[0] if row else 0

                cursor.close()
            finally:
                conn.close()

        if feedback_store is not None:
            try:
                metrics["feedback_count"] = feedback_store.get_feedback_count_since("1970-01-01T00:00:00")
            except Exception:
                logger.warning("Failed to get feedback count", exc_info=True)

        if exp_repo is not None:
            try:
                active = exp_repo.list_active()
                metrics["active_experiments"] = len(active)
            except Exception:
                logger.warning("Failed to get active experiments count", exc_info=True)

    except Exception as exc:
        logger.exception("Failed to collect metrics")
        raise HTTPException(status_code=500, detail=str(exc))

    return metrics
