"""
Floorplan parsing ARQ job.

Downloads the floorplan image from S3, runs the full parse pipeline
(GPT-4o primary geometry + OpenCV refinement), and stores the result
in the parsed_plans table.

Progress events are emitted in real time as each pipeline stage completes
via the progress_callback passed to parse_floorplan().
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
    ARQ job: Download floorplan image → parse → store ParsedPlan.
    Returns parsed_plan_id on success.
    """
    s3 = _s3_client()
    db = SessionLocal()
    parse_job_id = str(uuid4())
    parsed_plan_id = str(uuid4())

    project_id: str | None = None

    try:
        # ── Load asset metadata ──────────────────────────────────────
        row = db.execute(
            text(
                "SELECT id, project_id, storage_key, mime_type "
                "FROM floorplan_assets WHERE id = :aid"
            ),
            {"aid": asset_id},
        ).fetchone()

        if not row:
            logger.error("Asset not found: %s", asset_id)
            return None

        project_id = row[1]
        storage_key = row[2]
        mime_type = row[3]

        # PDFs were rasterized to PNG by pdf_rasterize job
        if mime_type == "application/pdf":
            base = storage_key.rsplit(".", 1)[0] if "." in storage_key else storage_key
            storage_key = base + "_page1.png"
            mime_type = "image/png"

        # ── Download image ───────────────────────────────────────────
        emit_project_event(project_id, "job_update", {
            "job_id": parse_job_id, "job_type": "floorplan_parse",
            "status": "running", "progress": 0.03,
            "stage": "downloading_image",
            "result_ref": None, "error": None, "timestamp": _now(),
        })

        buf = io.BytesIO()
        s3.download_fileobj(BUCKET, storage_key, buf)
        image_bytes = buf.getvalue()
        logger.info("Downloaded %d bytes from s3://%s/%s", len(image_bytes), BUCKET, storage_key)

        # ── Run the parse pipeline with real-time progress ───────────
        # The pipeline calls progress_callback(stage, 0-1) as each stage
        # completes, so we emit SSE events in sync with actual work.

        def _on_progress(stage: str, pct: float):
            # Map pipeline's 0-1 range → job 0.05-0.90 range
            job_pct = 0.05 + pct * 0.85
            emit_project_event(project_id, "job_update", {
                "job_id": parse_job_id, "job_type": "floorplan_parse",
                "status": "running", "progress": round(job_pct, 2),
                "stage": stage,
                "result_ref": None, "error": None, "timestamp": _now(),
            })

        parsed = parse_floorplan(image_bytes, mime_type, progress_callback=_on_progress)

        # ── Save results ─────────────────────────────────────────────
        emit_project_event(project_id, "job_update", {
            "job_id": parse_job_id, "job_type": "floorplan_parse",
            "status": "running", "progress": 0.91,
            "stage": "saving_results",
            "result_ref": None, "error": None, "timestamp": _now(),
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
                "id": parsed_plan_id,
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
                    "x": 0,
                    "y": 0,
                    "scale_info": parsed.get("scale_info"),
                    "ceiling_height_m": parsed.get("ceiling_height_m"),
                }),
            },
        )
        db.commit()

        emit_project_event(project_id, "job_update", {
            "job_id": parse_job_id, "job_type": "floorplan_parse",
            "status": "complete", "progress": 1.0,
            "stage": "parse_complete",
            "result_ref": parsed_plan_id,
            "error": None, "timestamp": _now(),
        })

        logger.info(
            "Parsed %s: %d walls, %d rooms, %d openings, conf=%.2f, flags=%s",
            asset_id,
            len(parsed.get("walls", [])),
            len(parsed.get("rooms", [])),
            len(parsed.get("openings", [])),
            parsed.get("confidence_overall", 0),
            parsed.get("ambiguity_flags", []),
        )
        return parsed_plan_id

    except Exception as e:
        logger.exception("floorplan_parse failed for %s: %s", asset_id, e)
        db.rollback()
        if project_id:
            try:
                emit_project_event(project_id, "job_update", {
                    "job_id": parse_job_id, "job_type": "floorplan_parse",
                    "status": "failed", "progress": 0,
                    "stage": None, "result_ref": None,
                    "error": {"code": "PARSE_FAILED", "message": str(e)},
                    "timestamp": _now(),
                })
            except Exception:
                pass
        raise
    finally:
        db.close()
