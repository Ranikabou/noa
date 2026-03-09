"""PDF→PNG rasterizer ARQ job. Converts PDF floorplans to PNG at 150dpi."""
import io
import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.config import Config
from pdf2image import convert_from_bytes
from PIL import Image
from sqlalchemy import text
from sqlalchemy.orm import Session

from noa_api.db.session import SessionLocal
from noa_api.events import emit_project_event

logger = logging.getLogger("noa.jobs.pdf_rasterize")

BUCKET = os.environ.get("S3_BUCKET_ASSETS", "noa-assets")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT_URL")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
DPI = 150


def _s3_client():
    kwargs = {"region_name": AWS_REGION}
    if S3_ENDPOINT:
        kwargs["endpoint_url"] = S3_ENDPOINT
    return boto3.client("s3", config=Config(signature_version="s3v4"), **kwargs)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


async def pdf_rasterize(ctx: dict, asset_id: str) -> str | None:
    """
    ARQ job: Download PDF from S3, convert to PNG, upload first page, update FloorplanAsset.
    Returns asset_id on success.
    """
    s3 = _s3_client()
    db = SessionLocal()

    try:
        # Fetch asset
        r = db.execute(
            text(
                "SELECT id, project_id, storage_key, mime_type FROM floorplan_assets WHERE id = :aid"
            ),
            {"aid": asset_id},
        )
        row = r.fetchone()
        if not row:
            logger.error("Asset not found: %s", asset_id)
            return None

        project_id = row[1]
        storage_key = row[2]
        mime_type = row[3]

        if mime_type != "application/pdf":
            # Already an image; mark ready
            db.execute(
                text(
                    "UPDATE floorplan_assets SET upload_status = 'ready' WHERE id = :aid"
                ),
                {"aid": asset_id},
            )
            db.commit()
            emit_project_event(
                project_id,
                "job_update",
                {
                    "job_id": asset_id,
                    "job_type": "pdf_rasterize",
                    "status": "complete",
                    "retry_count": 0,
                    "progress": 1.0,
                    "stage": "skip_not_pdf",
                    "result_ref": asset_id,
                    "error": None,
                    "timestamp": _now(),
                },
            )
            return asset_id

        # Download PDF
        buf = io.BytesIO()
        s3.download_fileobj(BUCKET, storage_key, buf)
        pdf_bytes = buf.getvalue()

        # Convert to PNG (first page at 150dpi)
        images = convert_from_bytes(pdf_bytes, dpi=DPI, first_page=1, last_page=1)
        if not images:
            raise ValueError("No pages in PDF")

        img = images[0]
        png_buf = io.BytesIO()
        img.save(png_buf, format="PNG")
        png_buf.seek(0)

        # Upload PNG (replace extension in key)
        png_key = storage_key.rsplit(".", 1)[0] + "_page1.png" if "." in storage_key else storage_key + "_page1.png"
        s3.upload_fileobj(
            png_buf,
            BUCKET,
            png_key,
            ExtraArgs={"ContentType": "image/png"},
        )

        # Update asset: dimensions, page_count, upload_status
        dims = json.dumps({"width": img.width, "height": img.height})
        db.execute(
            text(
                """
                UPDATE floorplan_assets
                SET dimensions_px = CAST(:dims AS jsonb), page_count = 1, upload_status = 'ready'
                WHERE id = :aid
                """
            ),
            {"aid": asset_id, "dims": dims},
        )
        db.commit()

        emit_project_event(
            project_id,
            "job_update",
            {
                "job_id": asset_id,
                "job_type": "pdf_rasterize",
                "status": "complete",
                "retry_count": 0,
                "progress": 1.0,
                "stage": "rasterize_complete",
                "result_ref": asset_id,
                "error": None,
                "timestamp": _now(),
            },
        )

        # Auto-trigger AI floorplan parsing after rasterization
        from noa_api.worker import enqueue_floorplan_parse
        await enqueue_floorplan_parse(asset_id)

        return asset_id

    except Exception as e:
        logger.exception("pdf_rasterize failed: %s", e)
        db.rollback()
        # Emit failure event if we have project_id
        try:
            r = db.execute(
                text("SELECT project_id FROM floorplan_assets WHERE id = :aid"),
                {"aid": asset_id},
            )
            row = r.fetchone()
            if row:
                emit_project_event(
                    row[0],
                    "job_update",
                    {
                        "job_id": asset_id,
                        "job_type": "pdf_rasterize",
                        "status": "failed",
                        "retry_count": 0,
                        "progress": 0,
                        "stage": None,
                        "result_ref": None,
                        "error": {"code": "RASTERIZE_FAILED", "message": str(e)},
                        "timestamp": _now(),
                    },
                )
        except Exception:
            pass
        raise
    finally:
        db.close()
