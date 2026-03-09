"""3D model build, exports, and download endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from noa_api.db.models import (
    CanonicalModel as ModelDB,
    ExportPackage as ExportDB,
    Project as ProjectDB,
)
from noa_api.db.session import get_db

router = APIRouter()


@router.post("/{project_id}/build", status_code=202)
async def trigger_build(project_id: str, db: Session = Depends(get_db)):
    """Trigger 3D model reconstruction from parsed plan + geometry rules."""
    project = db.query(ProjectDB).filter(ProjectDB.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.floorplan_asset_id:
        raise HTTPException(status_code=400, detail="Upload a floorplan first")

    from noa_api.worker import enqueue_model_reconstruct
    job_id = await enqueue_model_reconstruct(project_id)
    return {"status": "accepted", "job_id": job_id}


@router.get("/{project_id}/model")
async def get_model(project_id: str, db: Session = Depends(get_db)):
    """Get the canonical building model for a project."""
    project = db.query(ProjectDB).filter(ProjectDB.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.canonical_model_id:
        raise HTTPException(status_code=404, detail="No 3D model yet. Trigger a build first.")

    model = db.query(ModelDB).filter(ModelDB.id == project.canonical_model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    glb_key = None
    meshes = (model.geometry_layer or {}).get("meshes", [])
    if meshes:
        glb_key = meshes[0].get("storage_key")

    obs = model.observation_types or {}
    return {
        "id": model.id,
        "project_id": model.project_id,
        "style_profile_id": model.style_profile_id,
        "elements": model.elements,
        "geometry_layer": model.geometry_layer,
        "glb_storage_key": glb_key,
        "provenance": model.provenance,
        "fidelity_scores": obs.get("fidelity_scores"),
        "fidelity_hash": obs.get("fidelity_hash"),
        "coordinate_system": obs.get("coordinate_system"),
        "params_used": obs.get("params_used"),
        "version": model.version,
        "created_at": model.created_at.isoformat() if model.created_at else None,
    }


@router.get("/{project_id}/exports")
async def list_exports(project_id: str, db: Session = Depends(get_db)):
    """List all export packages for a project."""
    project = db.query(ProjectDB).filter(ProjectDB.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.canonical_model_id:
        raise HTTPException(status_code=404, detail="No model built yet")

    exports = (
        db.query(ExportDB)
        .filter(ExportDB.canonical_model_id == project.canonical_model_id)
        .order_by(ExportDB.created_at.desc())
        .all()
    )
    return [
        {
            "id": e.id,
            "format": e.format,
            "storage_key": e.storage_key,
            "geometry_fidelity": e.geometry_fidelity,
            "semantic_fidelity": e.semantic_fidelity,
            "supported_elements": e.supported_elements,
            "limitations": e.limitations,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in exports
    ]
