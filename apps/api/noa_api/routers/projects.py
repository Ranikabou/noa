"""Project CRUD. Uses canonical Project contract and Postgres."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from noa_api.db.models import Project as ProjectModel
from noa_api.db.session import get_db

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _project_to_contract(row: ProjectModel) -> dict:
    return {
        "schema_version": "1.0",
        "id": row.id,
        "name": row.name,
        "owner_id": row.owner_id,
        "status": row.status,
        "floorplan_asset_id": row.floorplan_asset_id,
        "inspiration_board_id": row.inspiration_board_id,
        "canonical_model_id": row.canonical_model_id,
        "metadata": row.metadata_ or {},
        "created_at": row.created_at.isoformat() if row.created_at else _now(),
        "updated_at": row.updated_at.isoformat() if row.updated_at else _now(),
    }


@router.get("")
async def list_projects(db: Session = Depends(get_db)):
    """List all projects. Returns Project[]."""
    rows = db.query(ProjectModel).order_by(ProjectModel.created_at.desc()).all()
    return [_project_to_contract(r) for r in rows]


@router.post("", status_code=201)
async def create_project(name: str, owner_id: str, db: Session = Depends(get_db)):
    """Create a new project. Returns Project contract."""
    row = ProjectModel(
        name=name,
        owner_id=owner_id,
        status="draft",
        floorplan_asset_id=None,
        inspiration_board_id=None,
        canonical_model_id=None,
        metadata_={},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _project_to_contract(row)


@router.get("/{project_id}")
async def get_project(project_id: str, db: Session = Depends(get_db)):
    """Get project by ID. Returns Project contract."""
    row = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return _project_to_contract(row)
