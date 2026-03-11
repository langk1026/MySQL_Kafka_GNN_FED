import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.models import AnalystFeedback

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level dependencies dict populated by main.py during startup.
_deps: dict = {}


class FeedbackRequest(BaseModel):
    analyst_id: str
    verdict: str  # "true_positive" | "false_positive" | "false_negative"
    notes: str = ""


@router.get("/")
def list_pending_reviews(limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    """Paginated pending review items."""
    review_queue = _deps.get("review_queue")
    if review_queue is None:
        raise HTTPException(status_code=503, detail="Review queue not available")

    try:
        items = review_queue.get_pending(limit=limit, offset=offset)
        return {
            "items": [item.to_dict() for item in items],
            "count": len(items),
            "limit": limit,
            "offset": offset,
        }
    except Exception as exc:
        logger.exception("Failed to list pending reviews")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{transaction_id}")
def get_review_item(transaction_id: str):
    """Get a single review item."""
    review_queue = _deps.get("review_queue")
    if review_queue is None:
        raise HTTPException(status_code=503, detail="Review queue not available")

    try:
        item = review_queue.get_item(transaction_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Review item not found")
        return item.to_dict()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to get review item %s", transaction_id)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{transaction_id}/feedback")
def submit_feedback(transaction_id: str, req: FeedbackRequest):
    """Submit analyst verdict for a review item."""
    feedback_store = _deps.get("feedback_store")
    review_queue = _deps.get("review_queue")
    tx_repo = _deps.get("tx_repo")

    if feedback_store is None:
        raise HTTPException(status_code=503, detail="Feedback store not available")

    valid_verdicts = {"true_positive", "false_positive", "false_negative"}
    if req.verdict not in valid_verdicts:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid verdict '{req.verdict}'. Must be one of: {valid_verdicts}",
        )

    try:
        # Look up the original fraud result to capture the original score/model
        original_score = 0.0
        original_model_version = "unknown"
        if tx_repo is not None:
            fraud_result = tx_repo.get_fraud_result(transaction_id)
            if fraud_result is not None:
                original_score = fraud_result.score
                original_model_version = fraud_result.model_version

        feedback = AnalystFeedback(
            feedback_id=str(uuid.uuid4()),
            transaction_id=transaction_id,
            analyst_id=req.analyst_id,
            verdict=req.verdict,
            notes=req.notes,
            original_score=original_score,
            original_model_version=original_model_version,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        feedback_store.submit_feedback(feedback)

        # Mark as reviewed in the queue
        if review_queue is not None:
            review_queue.mark_reviewed(transaction_id)

        logger.info(
            "Feedback submitted for tx %s by analyst %s: %s",
            transaction_id, req.analyst_id, req.verdict,
        )
        return {"status": "ok", "feedback_id": feedback.feedback_id}
    except Exception as exc:
        logger.exception("Failed to submit feedback for %s", transaction_id)
        raise HTTPException(status_code=500, detail=str(exc))
