import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.models import Transaction

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level dependencies dict populated by main.py during startup.
_deps: dict = {}


class TransactionRequest(BaseModel):
    transaction_id: str
    user_id: str
    amount: float
    currency: str = "USD"
    merchant_id: str
    location: str
    device_id: str
    ip_address: str
    timestamp: str | None = None


@router.post("/")
def submit_transaction(req: TransactionRequest):
    """Submit a transaction directly, invoke scoring pipeline, return FraudResult."""
    tx_repo = _deps.get("tx_repo")
    pipeline = _deps.get("pipeline")

    if tx_repo is None:
        raise HTTPException(status_code=503, detail="Transaction repository not available")

    timestamp = req.timestamp or datetime.now(timezone.utc).isoformat()
    tx = Transaction(
        transaction_id=req.transaction_id,
        user_id=req.user_id,
        amount=req.amount,
        currency=req.currency,
        timestamp=timestamp,
        merchant_id=req.merchant_id,
        location=req.location,
        device_id=req.device_id,
        ip_address=req.ip_address,
    )

    try:
        # Persist transaction
        tx_repo.insert_transaction(tx)

        # Score through pipeline if available
        if pipeline is not None:
            result = pipeline.score(tx)
            tx_repo.insert_fraud_result(result)
            return result.to_dict()
        else:
            return {"transaction_id": tx.transaction_id, "status": "stored", "note": "Pipeline not available"}
    except Exception as exc:
        logger.exception("Failed to process transaction %s", req.transaction_id)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{transaction_id}")
def get_transaction(transaction_id: str):
    """Get stored transaction and fraud result from DB."""
    tx_repo = _deps.get("tx_repo")
    if tx_repo is None:
        raise HTTPException(status_code=503, detail="Transaction repository not available")

    try:
        tx = tx_repo.get_transaction(transaction_id)
        if tx is None:
            raise HTTPException(status_code=404, detail="Transaction not found")

        fraud_result = tx_repo.get_fraud_result(transaction_id)
        response = {
            "transaction": tx.to_dict(),
            "fraud_result": fraud_result.to_dict() if fraud_result else None,
        }
        return response
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to get transaction %s", transaction_id)
        raise HTTPException(status_code=500, detail=str(exc))
