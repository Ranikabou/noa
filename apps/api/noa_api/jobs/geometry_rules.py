"""Geometry rules ARQ job. Combines StyleProfile + ParsedPlan → GeometryRuleSet via GPT-4o."""
import json
import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

from openai import OpenAI
from sqlalchemy import text

from noa_api.db.session import SessionLocal
from noa_api.events import emit_project_event

logger = logging.getLogger("noa.jobs.geometry_rules")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


SYSTEM_PROMPT = """You are an expert architectural geometry consultant. Given a style profile and a parsed floorplan, generate geometry rules that will guide 3D model generation. Return ONLY valid JSON matching this schema:

{
  "confidence_overall": <float 0-1>,
  "rules": [
    {
      "rule_type": "glazing_ratio",
      "target_ratio": <float 0-1>,
      "applies_to": "exterior_walls|all_walls",
      "confidence": <float 0-1>
    },
    {
      "rule_type": "roof_form",
      "form": "flat|shed|gabled|hipped|butterfly",
      "pitch_degrees": <number or null>,
      "confidence": <float 0-1>
    },
    {
      "rule_type": "floor_height",
      "height_meters": <float>,
      "applies_to": "all|ground_floor|upper_floors",
      "confidence": <float 0-1>
    },
    {
      "rule_type": "material_hint",
      "material": "<material name>",
      "target_surface": "walls|floors|ceiling|exterior|countertops|cabinetry",
      "room_ids": ["room-1", ...] or null for all rooms,
      "finish": "<finish description>",
      "color_hex": "#RRGGBB",
      "confidence": <float 0-1>
    },
    {
      "rule_type": "overhang",
      "depth_meters": <float>,
      "applies_to": "south|all|entrance",
      "confidence": <float 0-1>
    },
    {
      "rule_type": "facade_grid",
      "module_width_meters": <float>,
      "module_height_meters": <float>,
      "confidence": <float 0-1>
    }
  ]
}

Rules to generate:
- At least 1 glazing_ratio rule
- At least 1 roof_form rule
- At least 1 floor_height rule
- Multiple material_hint rules (one per major surface type, referencing room IDs from the parsed plan)
- Overhang and facade_grid rules if the style suggests them
- Material hints should be specific: reference actual room IDs from the parsed plan when possible
- All rules should be consistent with the style signals provided
- Return ONLY the JSON object, no markdown, no explanation"""


def _call_rules_api(style_signals: dict, rooms: list, confidence_per_signal: dict) -> dict:
    """Send style profile + room data to GPT-4o to generate geometry rules."""
    client = OpenAI(api_key=OPENAI_API_KEY)

    room_summary = []
    for room in rooms:
        room_summary.append({
            "id": room.get("id"),
            "label": room.get("label", "Unknown"),
            "confidence": room.get("confidence", 0),
        })

    user_msg = (
        f"Style signals:\n{json.dumps(style_signals, indent=2)}\n\n"
        f"Confidence per signal:\n{json.dumps(confidence_per_signal, indent=2)}\n\n"
        f"Detected rooms:\n{json.dumps(room_summary, indent=2)}\n\n"
        "Generate geometry rules for 3D model generation that match this style "
        "and these rooms. Return the JSON."
    )

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
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


async def geometry_rules(ctx: dict, style_profile_id: str, project_id: str) -> str | None:
    """
    ARQ job: Load StyleProfile + ParsedPlan, call GPT-4o to generate GeometryRuleSet.
    Returns rule_set_id on success.
    """
    db = SessionLocal()
    job_id = str(uuid4())

    try:
        emit_project_event(
            project_id,
            "job_update",
            {
                "job_id": job_id,
                "job_type": "geometry_rules",
                "status": "running",
                "retry_count": 0,
                "progress": 0.1,
                "stage": "loading_data",
                "result_ref": None,
                "error": None,
                "timestamp": _now(),
            },
        )

        # Load style profile
        r = db.execute(
            text("SELECT style_signals, confidence_per_signal FROM style_profiles WHERE id = :sid"),
            {"sid": style_profile_id},
        )
        sp_row = r.fetchone()
        if not sp_row:
            raise ValueError(f"StyleProfile not found: {style_profile_id}")

        style_signals = sp_row[0]
        confidence_per_signal = sp_row[1]

        # Load parsed plan rooms for this project
        r2 = db.execute(
            text(
                """
                SELECT pp.rooms FROM parsed_plans pp
                JOIN floorplan_assets fa ON fa.id = pp.floorplan_asset_id
                JOIN projects p ON p.floorplan_asset_id = fa.id
                WHERE p.id = :pid
                ORDER BY pp.created_at DESC LIMIT 1
                """
            ),
            {"pid": project_id},
        )
        pp_row = r2.fetchone()
        rooms = pp_row[0] if pp_row else []

        emit_project_event(
            project_id,
            "job_update",
            {
                "job_id": job_id,
                "job_type": "geometry_rules",
                "status": "running",
                "retry_count": 0,
                "progress": 0.4,
                "stage": "generating_rules",
                "result_ref": None,
                "error": None,
                "timestamp": _now(),
            },
        )

        result = _call_rules_api(style_signals, rooms, confidence_per_signal)

        rule_set_id = str(uuid4())
        db.execute(
            text(
                """
                INSERT INTO geometry_rule_sets
                    (id, style_profile_id, confidence_overall, rules)
                VALUES
                    (:id, :sid, :conf, CAST(:rules AS jsonb))
                """
            ),
            {
                "id": rule_set_id,
                "sid": style_profile_id,
                "conf": result.get("confidence_overall", 0.0),
                "rules": json.dumps(result.get("rules", [])),
            },
        )
        db.commit()

        emit_project_event(
            project_id,
            "job_update",
            {
                "job_id": job_id,
                "job_type": "geometry_rules",
                "status": "complete",
                "retry_count": 0,
                "progress": 1.0,
                "stage": "rules_complete",
                "result_ref": rule_set_id,
                "error": None,
                "timestamp": _now(),
            },
        )

        logger.info(
            "Geometry rules for profile %s: %d rules generated",
            style_profile_id,
            len(result.get("rules", [])),
        )
        # Auto-trigger 3D model reconstruction
        try:
            from noa_api.worker import enqueue_model_reconstruct
            await enqueue_model_reconstruct(project_id)
        except Exception as e2:
            logger.warning("Failed to enqueue model_reconstruct (non-fatal): %s", e2)

        return rule_set_id

    except Exception as e:
        logger.exception("geometry_rules failed: %s", e)
        db.rollback()
        try:
            emit_project_event(
                project_id,
                "job_update",
                {
                    "job_id": job_id,
                    "job_type": "geometry_rules",
                    "status": "failed",
                    "retry_count": 0,
                    "progress": 0,
                    "stage": None,
                    "result_ref": None,
                    "error": {"code": "GEOMETRY_RULES_FAILED", "message": str(e)},
                    "timestamp": _now(),
                },
            )
        except Exception:
            pass
        raise
    finally:
        db.close()
