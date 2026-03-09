"""
Floorplan parsing ARQ job.

Uses OpenCV for geometry extraction (walls, rooms, openings from actual pixels)
and GPT-4o ONLY for semantic labeling (room names). No LLM-generated coordinates.
"""
import io
import json
import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

import boto3
from botocore.config import Config
from sqlalchemy import text

from noa_api.db.session import SessionLocal
from noa_api.events import emit_project_event
from noa_api.parsing.pipeline import parse_floorplan

logger = logging.getLogger("noa.jobs.floorplan_parse")

BUCKET = os.environ.get("S3_BUCKET_ASSETS", "noa-assets")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT_URL")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")


def _s3_client():
    kwargs = {"region_name": AWS_REGION}
    if S3_ENDPOINT:
        kwargs["endpoint_url"] = S3_ENDPOINT
        kwargs["aws_access_key_id"] = os.environ.get("AWS_ACCESS_KEY_ID", "test")
        kwargs["aws_secret_access_key"] = os.environ.get("AWS_SECRET_ACCESS_KEY", "test")
    return boto3.client("s3", config=Config(signature_version="s3v4"), **kwargs)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


async def floorplan_parse(ctx: dict, asset_id: str) -> str | None:
    """
    ARQ job: Download floorplan image, run CV-based parsing pipeline,
    create ParsedPlan record. Returns parsed_plan_id on success.
    """
    s3 = _s3_client()
    db = SessionLocal()
    parse_job_id = str(uuid4())

    try:
        r = db.execute(
            text(
                "SELECT id, project_id, storage_key, mime_type, dimensions_px "
                "FROM floorplan_assets WHERE id = :aid"
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
        dimensions = row[4]

        # For PDFs that were rasterized, find the PNG key
        if mime_type == "application/pdf":
            png_key = (
                storage_key.rsplit(".", 1)[0] + "_page1.png"
                if "." in storage_key
                else storage_key + "_page1.png"
            )
            storage_key = png_key
            mime_type = "image/png"

        # Stage: downloading
        emit_project_event(project_id, "job_update", {
            "job_id": parse_job_id, "job_type": "floorplan_parse",
            "status": "running", "progress": 0.05,
            "stage": "downloading_image",
            "error": None, "timestamp": _now(),
        })

        buf = io.BytesIO()
        s3.download_fileobj(BUCKET, storage_key, buf)
        image_bytes = buf.getvalue()
        logger.info("Downloaded %d bytes from %s", len(image_bytes), storage_key)

        # Stage: normalizing
        emit_project_event(project_id, "job_update", {
            "job_id": parse_job_id, "job_type": "floorplan_parse",
            "status": "running", "progress": 0.10,
            "stage": "normalizing",
            "error": None, "timestamp": _now(),
        })

        # Stage: detecting walls
        emit_project_event(project_id, "job_update", {
            "job_id": parse_job_id, "job_type": "floorplan_parse",
            "status": "running", "progress": 0.25,
            "stage": "detecting_walls",
            "error": None, "timestamp": _now(),
        })

        # Stage: segmenting rooms
        emit_project_event(project_id, "job_update", {
            "job_id": parse_job_id, "job_type": "floorplan_parse",
            "status": "running", "progress": 0.45,
            "stage": "segmenting_rooms",
            "error": None, "timestamp": _now(),
        })

        # Stage: detecting openings
        emit_project_event(project_id, "job_update", {
            "job_id": parse_job_id, "job_type": "floorplan_parse",
            "status": "running", "progress": 0.60,
            "stage": "detecting_openings",
            "error": None, "timestamp": _now(),
        })

        # Run the full CV pipeline (all stages above happen inside)
        parsed = parse_floorplan(image_bytes, mime_type)

        # Stage: labeling rooms
        emit_project_event(project_id, "job_update", {
            "job_id": parse_job_id, "job_type": "floorplan_parse",
            "status": "running", "progress": 0.80,
            "stage": "labeling_rooms",
            "error": None, "timestamp": _now(),
        })

        # Stage: saving results
        emit_project_event(project_id, "job_update", {
            "job_id": parse_job_id, "job_type": "floorplan_parse",
            "status": "running", "progress": 0.90,
            "stage": "saving_results",
            "error": None, "timestamp": _now(),
        })

        bbox = parsed.get("bounding_box_px", {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0})

        db.execute(
            text("""
                INSERT INTO parsed_plans
                    (id, floorplan_asset_id, parse_job_id, status,
                     confidence_overall, ambiguity_flags,
                     walls, openings, rooms, stairs, columns, annotations,
                     bounding_box_px, coordinate_origin)
                VALUES
                    (:id, :faid, :jid, 'complete',
                     :conf, CAST(:ambig AS jsonb),
                     CAST(:walls AS jsonb), CAST(:openings AS jsonb),
                     CAST(:rooms AS jsonb), CAST(:stairs AS jsonb),
                     CAST(:columns AS jsonb), CAST(:annotations AS jsonb),
                     CAST(:bbox AS jsonb), CAST(:origin AS jsonb))
            """),
            {
                "id": parse_job_id,
                "faid": asset_id,
                "jid": parse_job_id,
                "conf": parsed.get("confidence_overall", 0.0),
                "ambig": json.dumps(parsed.get("ambiguity_flags", [])),
                "walls": json.dumps(parsed.get("walls", [])),
                "openings": json.dumps(parsed.get("openings", [])),
                "rooms": json.dumps(parsed.get("rooms", [])),
                "stairs": json.dumps(parsed.get("stairs", [])),
                "columns": json.dumps(parsed.get("columns", [])),
                "annotations": json.dumps(parsed.get("annotations", [])),
                "bbox": json.dumps(bbox),
                "origin": json.dumps({
                    "x": 0, "y": 0,
                    "scale_info": parsed.get("scale_info"),
                    "ceiling_height_m": parsed.get("ceiling_height_m"),
                }),
            },
        )
        db.commit()

        # Complete
        emit_project_event(project_id, "job_update", {
            "job_id": parse_job_id, "job_type": "floorplan_parse",
            "status": "complete", "progress": 1.0,
            "stage": "parse_complete",
            "result_ref": parse_job_id,
            "error": None, "timestamp": _now(),
        })

        logger.info(
            "Parsed floorplan %s: %d walls, %d rooms, %d openings, confidence=%.2f, flags=%s",
            asset_id,
            len(parsed.get("walls", [])),
            len(parsed.get("rooms", [])),
            len(parsed.get("openings", [])),
            parsed.get("confidence_overall", 0),
            parsed.get("ambiguity_flags", []),
        )
        return parse_job_id

    except Exception as e:
        logger.exception("floorplan_parse failed: %s", e)
        db.rollback()
        try:
            r2 = db.execute(
                text("SELECT project_id FROM floorplan_assets WHERE id = :aid"),
                {"aid": asset_id},
            )
            row2 = r2.fetchone()
            if row2:
                emit_project_event(row2[0], "job_update", {
                    "job_id": parse_job_id, "job_type": "floorplan_parse",
                    "status": "failed", "progress": 0, "stage": None,
                    "result_ref": None,
                    "error": {"code": "PARSE_FAILED", "message": str(e)},
                    "timestamp": _now(),
                })
        except Exception:
            pass
        raise
    finally:
        db.close()
