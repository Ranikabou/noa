"""Inspiration board + item endpoints. Upload reference images for style extraction."""
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from noa_api.db.models import (
    InspirationBoard as BoardModel,
    InspirationItem as ItemModel,
    Project as ProjectModel,
)
from noa_api.db.session import get_db
from noa_api.storage.s3 import _client as s3_client

import os

BUCKET = os.environ.get("S3_BUCKET_ASSETS", "noa-assets")

router = APIRouter()

ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_SIZE = 20 * 1024 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _board_to_contract(row: BoardModel) -> dict:
    return {
        "schema_version": "1.0",
        "id": row.id,
        "project_id": row.project_id,
        "name": row.name,
        "description": row.description,
        "item_count": row.item_count,
        "is_primary": row.is_primary,
        "style_profile_id": row.style_profile_id,
        "style_inference_status": row.style_inference_status,
        "created_at": row.created_at.isoformat() if row.created_at else _now(),
        "updated_at": row.updated_at.isoformat() if row.updated_at else _now(),
    }


def _item_to_contract(row: ItemModel) -> dict:
    return {
        "schema_version": "1.0",
        "id": row.id,
        "board_id": row.board_id,
        "source_type": row.source_type,
        "storage_key": row.storage_key,
        "source_url": row.source_url,
        "thumbnail_key": row.thumbnail_key,
        "embedding": None,
        "embedding_model": None,
        "weight": row.weight,
        "sentiment": row.sentiment,
        "annotations": row.annotations or [],
        "highlighted_elements": row.highlighted_elements or [],
        "rejected_elements": row.rejected_elements or [],
        "upload_status": row.upload_status,
        "created_at": row.created_at.isoformat() if row.created_at else _now(),
    }


@router.post("/{project_id}/boards", status_code=201)
async def create_board(
    project_id: str,
    name: str = "My Board",
    db: Session = Depends(get_db),
):
    """Create an inspiration board for a project."""
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    has_primary = db.query(BoardModel).filter(
        BoardModel.project_id == project_id, BoardModel.is_primary == True
    ).first()

    board = BoardModel(
        project_id=project_id,
        name=name,
        is_primary=not has_primary,
    )
    db.add(board)
    db.commit()
    db.refresh(board)

    if board.is_primary:
        project.inspiration_board_id = board.id
        db.commit()

    return _board_to_contract(board)


@router.get("/{project_id}/boards")
async def list_boards(project_id: str, db: Session = Depends(get_db)):
    """List all inspiration boards for a project."""
    boards = (
        db.query(BoardModel)
        .filter(BoardModel.project_id == project_id)
        .order_by(BoardModel.created_at)
        .all()
    )
    return [_board_to_contract(b) for b in boards]


@router.get("/{project_id}/boards/{board_id}")
async def get_board(project_id: str, board_id: str, db: Session = Depends(get_db)):
    """Get a specific inspiration board."""
    board = db.query(BoardModel).filter(
        BoardModel.id == board_id, BoardModel.project_id == project_id
    ).first()
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")
    return _board_to_contract(board)


@router.get("/{project_id}/boards/{board_id}/items")
async def list_items(project_id: str, board_id: str, db: Session = Depends(get_db)):
    """List all items in an inspiration board."""
    items = (
        db.query(ItemModel)
        .filter(ItemModel.board_id == board_id)
        .order_by(ItemModel.created_at)
        .all()
    )
    return [_item_to_contract(i) for i in items]


@router.post("/{project_id}/boards/{board_id}/items", status_code=201)
async def upload_item(
    project_id: str,
    board_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload an inspiration image to a board."""
    board = db.query(BoardModel).filter(
        BoardModel.id == board_id, BoardModel.project_id == project_id
    ).first()
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")

    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_IMAGE_MIME:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, WebP images allowed")

    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")

    from uuid import uuid4
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in (file.filename or "upload"))[:64]
    key = f"inspiration/{board_id}/{uuid4().hex}_{safe_name}"

    client = s3_client()
    client.upload_fileobj(
        io.BytesIO(data),
        BUCKET,
        key,
        ExtraArgs={"ContentType": content_type},
    )

    item = ItemModel(
        board_id=board_id,
        source_type="upload",
        storage_key=key,
        upload_status="ready",
    )
    db.add(item)
    board.item_count = (board.item_count or 0) + 1
    db.commit()
    db.refresh(item)

    # Auto-trigger style inference when board has images
    if (board.item_count or 0) >= 1:
        from noa_api.worker import enqueue_style_inference
        await enqueue_style_inference(board_id, project_id)

    return _item_to_contract(item)
