import logging

from fastapi import APIRouter

from src.db.connection import get_pool

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ready")
def ready():
    status = {"status": "ready", "mysql": "unknown", "kafka": "unknown"}

    # Check MySQL
    try:
        pool = get_pool()
        conn = pool.get_connection()
        try:
            conn.ping(reconnect=True)
            status["mysql"] = "ok"
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("MySQL readiness check failed: %s", exc)
        status["mysql"] = f"error: {exc}"
        status["status"] = "degraded"

    # Check Kafka
    try:
        from confluent_kafka.admin import AdminClient
        from src.api.routes_transactions import _deps

        bootstrap_servers = _deps.get("bootstrap_servers", "")
        if bootstrap_servers:
            admin = AdminClient({"bootstrap.servers": bootstrap_servers})
            metadata = admin.list_topics(timeout=5)
            if metadata.topics:
                status["kafka"] = "ok"
            else:
                status["kafka"] = "no topics found"
                status["status"] = "degraded"
        else:
            status["kafka"] = "not configured"
            status["status"] = "degraded"
    except Exception as exc:
        logger.warning("Kafka readiness check failed: %s", exc)
        status["kafka"] = f"error: {exc}"
        status["status"] = "degraded"

    return status
