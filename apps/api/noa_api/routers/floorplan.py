"""Floorplan upload. Multipart → S3 → FloorplanAsset record."""
import io
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

logger = logging.getLogger("noa.routers.floorplan")
from PIL import Image
from sqlalchemy.orm import Session

from noa_api.db.models import FloorplanAsset as FloorplanAssetModel, Project as ProjectModel
from noa_api.db.session import get_db
from noa_api.events import emit_project_event
from noa_api.storage.s3 import upload_floorplan
from noa_contracts import FloorplanAsset

router = APIRouter()

ALLOWED_MIME = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
}
MAX_SIZE = 50 * 1024 * 1024  # 50MB


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _source_type_from_mime(mime: str) -> str:
    if mime == "application/pdf":
        return "pdf"
    if mime in ("image/jpeg", "image/png", "image/webp"):
        return "image"
    return "scan"


def _get_dimensions(data: bytes, mime: str) -> dict | None:
    """Extract width/height for images. PDF returns None (page_count handled separately)."""
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        return None
    try:
        img = Image.open(io.BytesIO(data))
        return {"width": img.width, "height": img.height}
    except Exception:
        return None


def _asset_to_contract(row: FloorplanAssetModel) -> dict:
    return {
        "schema_version": "1.0",
        "id": row.id,
        "project_id": row.project_id,
        "source_type": row.source_type,
        "storage_key": row.storage_key,
        "original_filename": row.original_filename,
        "mime_type": row.mime_type,
        "file_size_bytes": row.file_size_bytes,
        "dimensions_px": row.dimensions_px,
        "page_count": row.page_count,
        "detected_scale": row.detected_scale,
        "upload_status": row.upload_status,
        "ingestion_job_id": row.ingestion_job_id,
        "created_at": row.created_at.isoformat() if row.created_at else _now(),
    }


@router.get("/{project_id}/floorplan")
async def get_project_floorplan(
    project_id: str,
    db: Session = Depends(get_db),
):
    """Get the floorplan asset for a project."""
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project or not project.floorplan_asset_id:
        raise HTTPException(status_code=404, detail="No floorplan uploaded")
    asset = db.query(FloorplanAssetModel).filter(
        FloorplanAssetModel.id == project.floorplan_asset_id
    ).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return _asset_to_contract(asset)


@router.post("/{project_id}/floorplan", status_code=201)
async def upload_project_floorplan(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Multipart upload of floorplan (PDF or image).
    Uploads to S3, creates FloorplanAsset with upload_status=pending,
    enqueues PDF→PNG job if PDF. Returns FloorplanAsset.
    """
    # Validate project exists
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid MIME. Allowed: {', '.join(ALLOWED_MIME)}",
        )

    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large")

    # Upload to S3
    storage_key, file_size = upload_floorplan(
        project_id=project_id,
        file_obj=io.BytesIO(data),
        filename=file.filename or "upload",
        content_type=content_type,
    )

    # Dimensions for images
    dimensions = _get_dimensions(data, content_type)
    page_count = 1
    if content_type == "application/pdf":
        # PDF: page count from pdf2image would go here; for now assume 1
        page_count = 1

    source_type = _source_type_from_mime(content_type)

    asset = FloorplanAssetModel(
        project_id=project_id,
        source_type=source_type,
        storage_key=storage_key,
        original_filename=file.filename or "upload",
        mime_type=content_type,
        file_size_bytes=file_size,
        dimensions_px=dimensions,
        page_count=page_count,
        detected_scale=None,
        upload_status="pending",
        ingestion_job_id=None,
    )
    db.add(asset)
    db.flush()

    # Enqueue PDF→PNG rasterizer if PDF (before commit so we can set ingestion_job_id)
    ingestion_job_id = None
    if content_type == "application/pdf":
        from noa_api.worker import enqueue_pdf_rasterize

        ingestion_job_id = await enqueue_pdf_rasterize(asset.id)
        if ingestion_job_id:
            asset.ingestion_job_id = ingestion_job_id

    # Update project
    project.floorplan_asset_id = asset.id
    project.status = "processing"
    db.commit()
    db.refresh(asset)

    emit_project_event(
        project_id,
        "job_update",
        {
            "job_id": asset.id,
            "job_type": "floorplan_upload",
            "status": "complete",
            "retry_count": 0,
            "progress": 1.0,
            "stage": "upload_complete",
            "result_ref": asset.id,
            "error": None,
            "timestamp": _now(),
        },
    )

    # For images (non-PDF), auto-trigger AI parsing immediately
    if content_type != "application/pdf":
        try:
            from noa_api.worker import enqueue_floorplan_parse
            await enqueue_floorplan_parse(asset.id)
        except Exception as e:
            logger.warning("Failed to enqueue floorplan_parse (non-fatal): %s", e)

    return _asset_to_contract(asset)
