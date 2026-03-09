"""
Full floorplan parsing pipeline.

- OCR (pytesseract): dimension text, SQFT, ceiling height, room labels for scale.
- OpenCV: walls, rooms (planar-graph or flood fill), openings.
- GPT-4o: room labels only (geometry from pixels).
- Openings filtered by min/max width in meters once scale is known.
"""
import base64
import json
import logging
import os

from openai import OpenAI

from noa_api.parsing.normalizer import normalize
from noa_api.parsing.wall_detector import detect_walls
from noa_api.parsing.room_segmenter import segment_rooms
from noa_api.parsing.opening_detector import detect_openings, filter_openings_by_scale
from noa_api.parsing.scale_detector import detect_scale_from_text, detect_scale_from_rooms
from noa_api.parsing.dimension_ocr import extract_from_image as ocr_extract

logger = logging.getLogger("noa.parsing.pipeline")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_VISION_MODEL", "gpt-4o")


LABEL_PROMPT = """You are analyzing an architectural floorplan image. I have already detected room regions at the following pixel locations. Your job is ONLY to assign room labels (names) to each region. Do NOT change the geometry.

Detected rooms (by centroid position in pixels):
{room_list}

Looking at the floorplan image, assign a descriptive label to each room based on its position and any text visible in or near the room. Also extract any dimension text visible on the plan (like "11'4\" x 10'7\"" or "SQFT 572" or "CEILING HEIGHT 9'11\"").

Return ONLY valid JSON:
{{
  "room_labels": {{
    "room-1": "Bedroom",
    "room-2": "Kitchen",
    ...
  }},
  "dimension_text": "all dimension annotations you can read from the plan as a single string",
  "sqft": <integer or null if not visible>,
  "ceiling_height_text": "<text or null>"
}}"""


def _call_gpt_for_labels(image_bytes: bytes, mime_type: str,
                          rooms: list) -> dict:
    """Use GPT-4o ONLY for room labeling, NOT for geometry."""
    if not OPENAI_API_KEY:
        logger.warning("No OPENAI_API_KEY — returning unlabeled rooms")
        return {"room_labels": {}, "dimension_text": "", "sqft": None, "ceiling_height_text": None}

    room_list = ""
    for room in rooms:
        geo = room.get("geometry", [])
        if geo:
            cx = sum(p[0] for p in geo) / len(geo)
            cy = sum(p[1] for p in geo) / len(geo)
            room_list += f"  {room['id']}: centroid at ({int(cx)}, {int(cy)}), area={room.get('area_px', 0):.0f}px²\n"

    client = OpenAI(api_key=OPENAI_API_KEY)
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    media_type = mime_type if mime_type.startswith("image/") else "image/png"

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": LABEL_PROMPT.format(room_list=room_list)},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{media_type};base64,{b64}",
                        "detail": "high",
                    }},
                ],
            }],
            max_tokens=1024,
            temperature=0.1,
        )

        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = lines[1:] if lines[0].startswith("```") else lines
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines)

        return json.loads(raw)

    except Exception as e:
        logger.warning("GPT labeling failed (non-fatal): %s", e)
        return {"room_labels": {}, "dimension_text": "", "sqft": None, "ceiling_height_text": None}


def parse_floorplan(image_bytes: bytes, mime_type: str) -> dict:
    """
    Full CV-based parsing pipeline.

    Returns a complete ParsedPlan dict with walls, rooms, openings —
    all geometry from actual pixel measurements, not LLM guesses.
    """
    # Stage 1: Normalize
    logger.info("Stage 1: Normalizing image...")
    norm = normalize(image_bytes)
    img_bin = norm["image_bin"]
    img_w, img_h = norm["dimensions_px"]
    logger.info("Normalized: %dx%d, rotation=%.1f°, flags=%s",
                img_w, img_h, norm["rotation_degrees"], norm["quality_flags"])

    bounding_box = {"min_x": 0, "min_y": 0, "max_x": img_w, "max_y": img_h}

    # Stage 1b: OCR for dimensions and labels (improves scale and ceiling)
    ocr_result = ocr_extract(norm.get("image_gray", img_bin))
    dimension_text_ocr = ocr_result.get("dimension_text", "")
    sqft_ocr = ocr_result.get("sqft")
    ceiling_height_ocr = ocr_result.get("ceiling_height_m")

    # Stage 2: Detect walls
    logger.info("Stage 2: Detecting walls...")
    walls = detect_walls(img_bin)
    logger.info("Detected %d walls", len(walls))

    # Stage 3: Segment rooms
    logger.info("Stage 3: Segmenting rooms...")
    rooms = segment_rooms(img_bin, walls)
    logger.info("Segmented %d rooms", len(rooms))

    # Stage 4: Detect openings
    logger.info("Stage 4: Detecting openings...")
    openings = detect_openings(img_bin, walls)
    logger.info("Detected %d openings", len(openings))

    # Stage 5: GPT-4o for room labels + dimension text (geometry untouched)
    logger.info("Stage 5: GPT-4o room labeling...")
    labels = _call_gpt_for_labels(image_bytes, mime_type, rooms)

    room_labels = labels.get("room_labels", {})
    for room in rooms:
        if room["id"] in room_labels:
            room["label"] = room_labels[room["id"]]

    # Merge OCR + GPT dimension text for scale
    dimension_text_gpt = labels.get("dimension_text", "")
    dimension_text = " ".join(filter(None, [dimension_text_ocr, dimension_text_gpt]))
    sqft_raw = labels.get("sqft") or sqft_ocr

    # Stage 6: Scale detection (OCR + text regex + room-area matching)
    logger.info("Stage 6: Detecting scale...")
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

    # Prefer OCR ceiling height when available
    if ceiling_height_ocr is not None:
        scale_info.setdefault("details", {})["ceiling_height_m"] = ceiling_height_ocr

    # Stage 6b: Filter openings by plausible width in meters
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

    # Strip internal-only fields before returning
    clean_walls = []
    for w in walls:
        clean_walls.append({
            "id": w["id"],
            "geometry": w["geometry"],
            "thickness_px": w.get("thickness_px"),
            "wall_type": w.get("wall_type"),
            "confidence": w["confidence"],
            "observation_type": w["observation_type"],
        })

    clean_rooms = []
    for r in rooms:
        clean_rooms.append({
            "id": r["id"],
            "label": r.get("label"),
            "geometry": r["geometry"],
            "area_px": r.get("area_px"),
            "confidence": r["confidence"],
            "observation_type": r["observation_type"],
        })

    clean_openings = []
    for o in openings:
        clean_openings.append({
            "id": o["id"],
            "wall_id": o.get("wall_id"),
            "opening_type": o.get("opening_type", "door"),
            "geometry": o["geometry"],
            "position_on_wall": o.get("position_on_wall"),
            "width_px": o.get("width_px"),
            "confidence": o["confidence"],
            "observation_type": o["observation_type"],
        })

    ceiling_height_m = ceiling_height_ocr
    if ceiling_height_m is None:
        details = scale_info.get("details", {})
        ceiling_height_m = details.get("ceiling_height_m")

    return {
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
