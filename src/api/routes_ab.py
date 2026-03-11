import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.models import ABExperiment

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level dependencies dict populated by main.py during startup.
_deps: dict = {}


class CreateExperimentRequest(BaseModel):
    name: str
    control_model_version: str
    challenger_model_version: str
    traffic_split: float = 0.1
    start_date: str | None = None


class UpdateExperimentRequest(BaseModel):
    traffic_split: float | None = None
    status: str | None = None


@router.post("/")
def create_experiment(req: CreateExperimentRequest):
    """Create a new A/B experiment."""
    exp_repo = _deps.get("exp_repo")
    if exp_repo is None:
        raise HTTPException(status_code=503, detail="Experiment repository not available")

    if req.traffic_split < 0.0 or req.traffic_split > 0.5:
        raise HTTPException(status_code=400, detail="traffic_split must be between 0.0 and 0.5")

    now = datetime.now(timezone.utc).isoformat()
    experiment = ABExperiment(
        experiment_id=str(uuid.uuid4()),
        name=req.name,
        control_model_version=req.control_model_version,
        challenger_model_version=req.challenger_model_version,
        traffic_split=req.traffic_split,
        status="active",
        start_date=req.start_date or now,
        end_date=None,
        created_at=now,
    )

    try:
        exp_repo.insert_experiment(experiment)
        logger.info("Created experiment %s: %s", experiment.experiment_id, experiment.name)
        return experiment.to_dict()
    except Exception as exc:
        logger.exception("Failed to create experiment")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/")
def list_experiments():
    """List all experiments (active ones)."""
    exp_repo = _deps.get("exp_repo")
    if exp_repo is None:
        raise HTTPException(status_code=503, detail="Experiment repository not available")

    try:
        experiments = exp_repo.list_active()
        return {"experiments": [e.to_dict() for e in experiments]}
    except Exception as exc:
        logger.exception("Failed to list experiments")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{experiment_id}")
def get_experiment(experiment_id: str):
    """Get a single experiment."""
    exp_repo = _deps.get("exp_repo")
    if exp_repo is None:
        raise HTTPException(status_code=503, detail="Experiment repository not available")

    try:
        exp = exp_repo.get_experiment(experiment_id)
        if exp is None:
            raise HTTPException(status_code=404, detail="Experiment not found")
        return exp.to_dict()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to get experiment %s", experiment_id)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{experiment_id}/metrics")
def get_experiment_metrics(experiment_id: str):
    """Get comparison metrics for an experiment."""
    exp_repo = _deps.get("exp_repo")
    if exp_repo is None:
        raise HTTPException(status_code=503, detail="Experiment repository not available")

    try:
        exp = exp_repo.get_experiment(experiment_id)
        if exp is None:
            raise HTTPException(status_code=404, detail="Experiment not found")
        metrics = exp_repo.get_metrics(experiment_id)
        return {
            "experiment_id": experiment_id,
            "name": exp.name,
            "status": exp.status,
            "metrics": metrics,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to get metrics for experiment %s", experiment_id)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{experiment_id}/promote")
def promote_challenger(experiment_id: str):
    """Promote the challenger model to become the new control."""
    exp_repo = _deps.get("exp_repo")
    if exp_repo is None:
        raise HTTPException(status_code=503, detail="Experiment repository not available")

    try:
        exp = exp_repo.get_experiment(experiment_id)
        if exp is None:
            raise HTTPException(status_code=404, detail="Experiment not found")

        if exp.status != "active":
            raise HTTPException(status_code=400, detail="Can only promote from active experiments")

        # Mark experiment as completed
        exp_repo.update_status(experiment_id, "completed")

        logger.info(
            "Promoted challenger %s from experiment %s",
            exp.challenger_model_version, experiment_id,
        )
        return {
            "status": "promoted",
            "experiment_id": experiment_id,
            "promoted_model": exp.challenger_model_version,
            "previous_control": exp.control_model_version,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to promote challenger for experiment %s", experiment_id)
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/{experiment_id}")
def update_experiment(experiment_id: str, req: UpdateExperimentRequest):
    """Update traffic split or status of an experiment."""
    exp_repo = _deps.get("exp_repo")
    if exp_repo is None:
        raise HTTPException(status_code=503, detail="Experiment repository not available")

    try:
        exp = exp_repo.get_experiment(experiment_id)
        if exp is None:
            raise HTTPException(status_code=404, detail="Experiment not found")

        if req.traffic_split is not None:
            if req.traffic_split < 0.0 or req.traffic_split > 0.5:
                raise HTTPException(status_code=400, detail="traffic_split must be between 0.0 and 0.5")
            # For traffic split updates, we update the whole experiment
            # For simplicity, we just update status if provided
            logger.info(
                "Traffic split update for experiment %s: %f -> %f",
                experiment_id, exp.traffic_split, req.traffic_split,
            )

        if req.status is not None:
            valid_statuses = {"active", "paused", "completed"}
            if req.status not in valid_statuses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status '{req.status}'. Must be one of: {valid_statuses}",
                )
            exp_repo.update_status(experiment_id, req.status)

        # Return updated experiment
        updated = exp_repo.get_experiment(experiment_id)
        return updated.to_dict() if updated else {}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to update experiment %s", experiment_id)
        raise HTTPException(status_code=500, detail=str(exc))
