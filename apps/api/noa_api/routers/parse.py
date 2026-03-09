"""Floorplan parsing endpoints. Trigger parse + fetch parsed plan."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from noa_api.db.models import (
    FloorplanAsset as FloorplanAssetModel,
    ParsedPlan as ParsedPlanModel,
    Project as ProjectModel,
)
from noa_api.db.session import get_db

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _plan_to_contract(row: ParsedPlanModel) -> dict:
    return {
        "schema_version": "1.0",
        "id": row.id,
        "floorplan_asset_id": row.floorplan_asset_id,
        "parse_job_id": row.parse_job_id,
        "status": row.status,
        "confidence_overall": row.confidence_overall,
        "ambiguity_flags": row.ambiguity_flags or [],
        "walls": row.walls or [],
        "openings": row.openings or [],
        "rooms": row.rooms or [],
        "stairs": row.stairs or [],
        "columns": row.columns or [],
        "annotations": row.annotations or [],
        "bounding_box_px": row.bounding_box_px or {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0},
        "coordinate_origin": row.coordinate_origin or {"x": 0, "y": 0},
        "created_at": row.created_at.isoformat() if row.created_at else _now(),
    }


@router.post("/{project_id}/parse", status_code=202)
async def trigger_parse(project_id: str, db: Session = Depends(get_db)):
    """Trigger AI floorplan parsing. Requires a floorplan to be uploaded first."""
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.floorplan_asset_id:
        raise HTTPException(status_code=400, detail="No floorplan uploaded yet")

    asset = db.query(FloorplanAssetModel).filter(
        FloorplanAssetModel.id == project.floorplan_asset_id
    ).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Floorplan asset not found")

    from noa_api.worker import enqueue_floorplan_parse

    job_id = await enqueue_floorplan_parse(asset.id)
    return {"status": "accepted", "job_id": job_id, "asset_id": asset.id}


@router.get("/{project_id}/parsed-plan")
async def get_parsed_plan(project_id: str, db: Session = Depends(get_db)):
    """Get the latest parsed plan for a project."""
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.floorplan_asset_id:
        raise HTTPException(status_code=404, detail="No floorplan uploaded")

    plan = (
        db.query(ParsedPlanModel)
        .filter(ParsedPlanModel.floorplan_asset_id == project.floorplan_asset_id)
        .order_by(ParsedPlanModel.created_at.desc())
        .first()
    )
    if not plan:
        raise HTTPException(status_code=404, detail="No parsed plan yet. Trigger parsing first.")

    return _plan_to_contract(plan)
