"""Style inference ARQ job. Analyzes inspiration board images via GPT-4o Vision → StyleProfile."""
import base64
import io
import json
import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

import boto3
from botocore.config import Config
from openai import OpenAI
from sqlalchemy import text

from noa_api.db.session import SessionLocal
from noa_api.events import emit_project_event

logger = logging.getLogger("noa.jobs.style_inference")

BUCKET = os.environ.get("S3_BUCKET_ASSETS", "noa-assets")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT_URL")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_VISION_MODEL", "gpt-4o")


def _s3_client():
    kwargs = {"region_name": AWS_REGION}
    if S3_ENDPOINT:
        kwargs["endpoint_url"] = S3_ENDPOINT
        kwargs["aws_access_key_id"] = os.environ.get("AWS_ACCESS_KEY_ID", "test")
        kwargs["aws_secret_access_key"] = os.environ.get("AWS_SECRET_ACCESS_KEY", "test")
    return boto3.client("s3", config=Config(signature_version="s3v4"), **kwargs)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


SYSTEM_PROMPT = """You are an expert interior designer and architectural style analyst. Given one or more inspiration images, analyze the visual style and return ONLY valid JSON matching this exact schema:

{
  "style_signals": {
    "massing_tendency": "<compact|elongated|fragmented|monolithic|layered>",
    "facade_rhythm": "<regular|syncopated|random|modular>",
    "material_palette": [
      {"name": "material_name", "category": "wood|stone|metal|glass|concrete|fabric|ceramic|other", "finish": "matte|glossy|textured|natural", "color_hex": "#RRGGBB", "usage": "where this material is used"}
    ],
    "lighting_mood": "<warm_ambient|cool_minimal|dramatic|natural_diffused|layered_accent>",
    "surface_language": "<rough_tactile|smooth_minimal|mixed_texture|ornate_detailed>",
    "compositional_balance": "symmetric|asymmetric|dynamic",
    "emotional_tone": ["up to 5 adjectives describing the mood, e.g. serene, bold, cozy"],
    "negative_preferences": ["things to avoid based on the style, e.g. industrial pipes, neon colors"],
    "roof_tendency": "<flat|shed|gabled|hipped|butterfly|not_visible>",
    "glazing_ratio": <float 0-1, proportion of glass to wall>,
    "overhang_tendency": "deep|minimal|none"
  },
  "confidence_per_signal": {
    "massing_tendency": <float 0-1>,
    "facade_rhythm": <float 0-1>,
    "material_palette": <float 0-1>,
    "lighting_mood": <float 0-1>,
    "surface_language": <float 0-1>,
    "compositional_balance": <float 0-1>,
    "emotional_tone": <float 0-1>,
    "roof_tendency": <float 0-1>,
    "glazing_ratio": <float 0-1>,
    "overhang_tendency": <float 0-1>
  }
}

Rules:
- Analyze ALL images together as a cohesive style direction
- material_palette should have 3-8 entries covering primary and accent materials
- confidence reflects how clearly each signal is expressed across images
- Return ONLY the JSON object, no markdown, no explanation"""


def _call_style_api(image_data_list: list[tuple[bytes, str]]) -> dict:
    """Send multiple inspiration images to GPT-4o Vision for style analysis."""
    client = OpenAI(api_key=OPENAI_API_KEY)

    content = [
        {
            "type": "text",
            "text": f"Analyze these {len(image_data_list)} inspiration images as a cohesive style direction. Extract the architectural and interior design style signals. Return the JSON.",
        }
    ]

    for img_bytes, mime in image_data_list:
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        media = mime if mime.startswith("image/") else "image/jpeg"
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{media};base64,{b64}", "detail": "low"},
        })

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        max_tokens=4096,
        temperature=0.2,
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = lines[1:] if lines[0].startswith("```") else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)

    return json.loads(raw)


async def style_inference(ctx: dict, board_id: str, project_id: str) -> str | None:
    """
    ARQ job: Download all inspiration images from a board, send to GPT-4o Vision,
    create StyleProfile record. Returns style_profile_id on success.
    """
    s3 = _s3_client()
    db = SessionLocal()
    job_id = str(uuid4())

    try:
        emit_project_event(
            project_id,
            "job_update",
            {
                "job_id": job_id,
                "job_type": "style_inference",
                "status": "running",
                "retry_count": 0,
                "progress": 0.1,
                "stage": "loading_images",
                "result_ref": None,
                "error": None,
                "timestamp": _now(),
            },
        )

        # Update board status
        db.execute(
            text("UPDATE inspiration_boards SET style_inference_status = 'running' WHERE id = :bid"),
            {"bid": board_id},
        )
        db.commit()

        # Fetch all items from the board
        r = db.execute(
            text(
                "SELECT id, storage_key FROM inspiration_items "
                "WHERE board_id = :bid AND upload_status = 'ready' AND storage_key IS NOT NULL"
            ),
            {"bid": board_id},
        )
        items = r.fetchall()
        if not items:
            raise ValueError("No ready images in board")

        image_data_list = []
        item_ids = []
        for item_id, storage_key in items:
            buf = io.BytesIO()
            s3.download_fileobj(BUCKET, storage_key, buf)
            image_data_list.append((buf.getvalue(), "image/jpeg"))
            item_ids.append(str(item_id))

        emit_project_event(
            project_id,
            "job_update",
            {
                "job_id": job_id,
                "job_type": "style_inference",
                "status": "running",
                "retry_count": 0,
                "progress": 0.4,
                "stage": "analyzing_style",
                "result_ref": None,
                "error": None,
                "timestamp": _now(),
            },
        )

        result = _call_style_api(image_data_list)

        style_signals = result.get("style_signals", {})
        confidence = result.get("confidence_per_signal", {})

        # Placeholder embedding (768-dim zero vector — real embeddings would come from CLIP)
        embedding = [0.0] * 768

        profile_id = str(uuid4())
        db.execute(
            text(
                """
                INSERT INTO style_profiles
                    (id, inspiration_board_id, inference_job_id,
                     style_signals, confidence_per_signal, source_image_ids)
                VALUES
                    (:id, :bid, :jid,
                     CAST(:signals AS jsonb), CAST(:conf AS jsonb), CAST(:imgs AS uuid[]))
                """
            ),
            {
                "id": profile_id,
                "bid": board_id,
                "jid": job_id,
                "signals": json.dumps(style_signals),
                "conf": json.dumps(confidence),
                "imgs": "{" + ",".join(item_ids) + "}",
            },
        )

        # Link profile back to the board
        db.execute(
            text(
                "UPDATE inspiration_boards "
                "SET style_profile_id = :pid, style_inference_status = 'ready' "
                "WHERE id = :bid"
            ),
            {"pid": profile_id, "bid": board_id},
        )
        db.commit()

        emit_project_event(
            project_id,
            "job_update",
            {
                "job_id": job_id,
                "job_type": "style_inference",
                "status": "complete",
                "retry_count": 0,
                "progress": 1.0,
                "stage": "style_complete",
                "result_ref": profile_id,
                "error": None,
                "timestamp": _now(),
            },
        )

        logger.info(
            "Style inference for board %s: %d materials, tones=%s",
            board_id,
            len(style_signals.get("material_palette", [])),
            style_signals.get("emotional_tone", []),
        )

        # Auto-trigger geometry rules generation
        from noa_api.worker import enqueue_geometry_rules
        await enqueue_geometry_rules(profile_id, project_id)

        return profile_id

    except Exception as e:
        logger.exception("style_inference failed: %s", e)
        db.rollback()
        db.execute(
            text("UPDATE inspiration_boards SET style_inference_status = 'failed' WHERE id = :bid"),
            {"bid": board_id},
        )
        db.commit()
        try:
            emit_project_event(
                project_id,
                "job_update",
                {
                    "job_id": job_id,
                    "job_type": "style_inference",
                    "status": "failed",
                    "retry_count": 0,
                    "progress": 0,
                    "stage": None,
                    "result_ref": None,
                    "error": {"code": "STYLE_INFERENCE_FAILED", "message": str(e)},
                    "timestamp": _now(),
                },
            )
        except Exception:
            pass
        raise
    finally:
        db.close()
