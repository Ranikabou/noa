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
from noa_api.parsing.normalizer import normalize
from noa_api.parsing.wall_detector import detect_walls
from noa_api.parsing.room_segmenter import segment_rooms
from noa_api.parsing.opening_detector import detect_openings, filter_openings_by_scale
from noa_api.parsing.scale_detector import detect_scale_from_text, detect_scale_from_rooms
from noa_api.parsing.dimension_ocr import extract_from_image as ocr_extract
from noa_api.parsing.pipeline import _call_gpt_for_labels

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
    parsed_plan_id = str(uuid4())

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

        norm = normalize(image_bytes)
        img_bin = norm["image_bin"]
        img_w, img_h = norm["dimensions_px"]
        logger.info("Normalized: %dx%d, rotation=%.1f°, flags=%s",
                    img_w, img_h, norm["rotation_degrees"], norm["quality_flags"])

        bounding_box = {"min_x": 0, "min_y": 0, "max_x": img_w, "max_y": img_h}

        # OCR for dimensions and labels (improves scale and ceiling)
        ocr_result = ocr_extract(norm.get("image_gray", img_bin))
        dimension_text_ocr = ocr_result.get("dimension_text", "")
        sqft_ocr = ocr_result.get("sqft")
        ceiling_height_ocr = ocr_result.get("ceiling_height_m")

        # Stage: detecting walls
        emit_project_event(project_id, "job_update", {
            "job_id": parse_job_id, "job_type": "floorplan_parse",
            "status": "running", "progress": 0.25,
            "stage": "detecting_walls",
            "error": None, "timestamp": _now(),
        })

        walls = detect_walls(img_bin)
        logger.info("Detected %d walls", len(walls))

        # Stage: segmenting rooms
        emit_project_event(project_id, "job_update", {
            "job_id": parse_job_id, "job_type": "floorplan_parse",
            "status": "running", "progress": 0.45,
            "stage": "segmenting_rooms",
            "error": None, "timestamp": _now(),
        })

        rooms = segment_rooms(img_bin, walls)
        logger.info("Segmented %d rooms", len(rooms))

        # Stage: detecting openings
        emit_project_event(project_id, "job_update", {
            "job_id": parse_job_id, "job_type": "floorplan_parse",
            "status": "running", "progress": 0.60,
            "stage": "detecting_openings",
            "error": None, "timestamp": _now(),
        })

        openings = detect_openings(img_bin, walls)
        logger.info("Detected %d openings", len(openings))

        # Stage: labeling rooms (GPT-4o for room labels + dimension text)
        emit_project_event(project_id, "job_update", {
            "job_id": parse_job_id, "job_type": "floorplan_parse",
            "status": "running", "progress": 0.75,
            "stage": "labeling_rooms",
            "error": None, "timestamp": _now(),
        })

        labels = _call_gpt_for_labels(image_bytes, mime_type, rooms)
        room_labels = labels.get("room_labels", {})
        for room in rooms:
            if room["id"] in room_labels:
                room["label"] = room_labels[room["id"]]

        # Merge OCR + GPT dimension text for scale
        dimension_text_gpt = labels.get("dimension_text", "")
        dimension_text = " ".join(filter(None, [dimension_text_ocr, dimension_text_gpt]))
        sqft_raw = labels.get("sqft") or sqft_ocr

        # Scale detection
        scale_from_text = detect_scale_from_text(dimension_text, rooms, bounding_box)
        if scale_from_text["confidence"] < 0.4:
            assumed_sqm = (sqft_raw * 0.0929) if sqft_raw else None
            scale_from_rooms = detect_scale_from_rooms(rooms, bounding_box, assumed_sqm)
            if scale_from_rooms["confidence"] > scale_from_text["confidence"]:
                scale_info = scale_from_rooms
            else:
                scale_info = scale_from_text
        else:
            scale_info = scale_from_text

        if ceiling_height_ocr is not None:
            scale_info.setdefault("details", {})["ceiling_height_m"] = ceiling_height_ocr

        px_per_m = scale_info.get("px_per_meter") or 0
        if px_per_m > 0:
            openings = filter_openings_by_scale(openings, px_per_m, min_width_m=0.5, max_width_m=2.5)

        logger.info("Scale: %.1f px/m (confidence=%.2f, method=%s)",
                    scale_info.get("px_per_meter", 0),
                    scale_info["confidence"],
                    scale_info["method"])

        # Compute confidence
        ambiguity_flags = list(norm.get("quality_flags", []))
        if scale_info["confidence"] < 0.5:
            ambiguity_flags.append("scale_uncertain")
        open_rooms = [r for r in rooms if r.get("open_boundary")]
        if open_rooms:
            ambiguity_flags.append(f"{len(open_rooms)}_rooms_have_open_boundaries")
        wall_confidences = [w["confidence"] for w in walls]
        room_confidences = [r["confidence"] for r in rooms]
        all_confidences = wall_confidences + room_confidences
        confidence_overall = float(sum(all_confidences) / max(len(all_confidences), 1))
        if len(walls) < 3:
            ambiguity_flags.append("very_few_walls")
            confidence_overall *= 0.7
        if len(rooms) < 1:
            ambiguity_flags.append("no_rooms_detected")
            confidence_overall *= 0.5

        # Strip internal-only fields
        clean_walls = [{
            "id": w["id"], "geometry": w["geometry"],
            "thickness_px": w.get("thickness_px"), "wall_type": w.get("wall_type"),
            "confidence": w["confidence"], "observation_type": w["observation_type"],
        } for w in walls]

        clean_rooms = [{
            "id": r["id"], "label": r.get("label"), "geometry": r["geometry"],
            "area_px": r.get("area_px"), "confidence": r["confidence"],
            "observation_type": r["observation_type"],
        } for r in rooms]

        clean_openings = [{
            "id": o["id"], "wall_id": o.get("wall_id"),
            "opening_type": o.get("opening_type", "door"), "geometry": o["geometry"],
            "position_on_wall": o.get("position_on_wall"), "width_px": o.get("width_px"),
            "confidence": o["confidence"], "observation_type": o["observation_type"],
        } for o in openings]

        ceiling_height_m = ceiling_height_ocr
        if ceiling_height_m is None:
            ceiling_height_m = scale_info.get("details", {}).get("ceiling_height_m")

        parsed = {
            "confidence_overall": round(min(confidence_overall, 1.0), 2),
            "walls": clean_walls,
            "rooms": clean_rooms,
            "openings": clean_openings,
            "stairs": [],
            "columns": [],
            "annotations": [],
            "ambiguity_flags": ambiguity_flags,
            "bounding_box_px": bounding_box,
            "scale_info": scale_info,
            "ceiling_height_m": ceiling_height_m,
            "dimension_text": dimension_text,
        }

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
            "result_ref": parsed_plan_id,
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
        return parsed_plan_id

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
