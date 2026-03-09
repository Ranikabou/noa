"""Style profile + geometry rule set endpoints."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from noa_api.db.models import (
    GeometryRuleSet as RuleSetModel,
    InspirationBoard as BoardModel,
    Project as ProjectModel,
    StyleProfile as StyleProfileModel,
)
from noa_api.db.session import get_db

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _profile_to_contract(row: StyleProfileModel) -> dict:
    return {
        "schema_version": "1.0",
        "id": row.id,
        "inspiration_board_id": row.inspiration_board_id,
        "inference_job_id": row.inference_job_id,
        "embedding_vector": [],
        "style_signals": row.style_signals or {},
        "confidence_per_signal": row.confidence_per_signal or {},
        "source_image_ids": row.source_image_ids or [],
        "created_at": row.created_at.isoformat() if row.created_at else _now(),
    }


def _ruleset_to_contract(row: RuleSetModel) -> dict:
    return {
        "schema_version": "1.0",
        "id": row.id,
        "style_profile_id": row.style_profile_id,
        "derived_at": row.derived_at.isoformat() if row.derived_at else _now(),
        "confidence_overall": row.confidence_overall,
        "rules": row.rules or [],
    }


@router.post("/{project_id}/style/infer", status_code=202)
async def trigger_style_inference(project_id: str, db: Session = Depends(get_db)):
    """Trigger style inference from the primary inspiration board."""
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.inspiration_board_id:
        raise HTTPException(status_code=400, detail="No inspiration board yet")

    board = db.query(BoardModel).filter(BoardModel.id == project.inspiration_board_id).first()
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")
    if (board.item_count or 0) == 0:
        raise HTTPException(status_code=400, detail="Board has no images. Upload inspiration images first.")

    from noa_api.worker import enqueue_style_inference
    job_id = await enqueue_style_inference(board.id, project_id)
    return {"status": "accepted", "job_id": job_id, "board_id": board.id}


@router.get("/{project_id}/style")
async def get_style_profile(project_id: str, db: Session = Depends(get_db)):
    """Get the latest style profile for a project's primary board."""
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.inspiration_board_id:
        raise HTTPException(status_code=404, detail="No inspiration board")

    board = db.query(BoardModel).filter(BoardModel.id == project.inspiration_board_id).first()
    if not board or not board.style_profile_id:
        raise HTTPException(status_code=404, detail="No style profile yet. Trigger style inference first.")

    profile = db.query(StyleProfileModel).filter(StyleProfileModel.id == board.style_profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Style profile not found")

    return _profile_to_contract(profile)


@router.post("/{project_id}/geometry-rules/generate", status_code=202)
async def trigger_geometry_rules(project_id: str, db: Session = Depends(get_db)):
    """Generate geometry rules from style profile + parsed plan."""
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.inspiration_board_id:
        raise HTTPException(status_code=400, detail="No inspiration board")

    board = db.query(BoardModel).filter(BoardModel.id == project.inspiration_board_id).first()
    if not board or not board.style_profile_id:
        raise HTTPException(status_code=400, detail="No style profile yet. Run style inference first.")

    from noa_api.worker import enqueue_geometry_rules
    job_id = await enqueue_geometry_rules(board.style_profile_id, project_id)
    return {"status": "accepted", "job_id": job_id, "style_profile_id": board.style_profile_id}


@router.get("/{project_id}/geometry-rules")
async def get_geometry_rules(project_id: str, db: Session = Depends(get_db)):
    """Get the latest geometry rule set for a project."""
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.inspiration_board_id:
        raise HTTPException(status_code=404, detail="No inspiration board")

    board = db.query(BoardModel).filter(BoardModel.id == project.inspiration_board_id).first()
    if not board or not board.style_profile_id:
        raise HTTPException(status_code=404, detail="No style profile yet")

    ruleset = (
        db.query(RuleSetModel)
        .filter(RuleSetModel.style_profile_id == board.style_profile_id)
        .order_by(RuleSetModel.created_at.desc())
        .first()
    )
    if not ruleset:
        raise HTTPException(status_code=404, detail="No geometry rules yet. Generate them first.")

    return _ruleset_to_contract(ruleset)
