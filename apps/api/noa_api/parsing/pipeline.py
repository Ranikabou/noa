"""
Full floorplan parsing pipeline — GPT-4o primary + OpenCV refinement.

Architecture (high-accuracy path):
  1. Normalize image (deskew, CLAHE, denoise, adaptive threshold)
  2. OCR (Tesseract) for dimension text extraction
  3. GPT-4o Vision: extract rooms, doors, windows as normalized 0-100 coords
  4. OpenCV Hough: detect raw wall lines for vertex snapping
  5. Snap GPT-4o polygon vertices to Hough line intersections (pixel precision)
  6. Reconstruct walls from room polygon boundaries (topology-correct)
  7. Place openings from GPT-4o positions, supplement with CV gap detection
  8. Scale detection from OCR + GPT dimension text + room area
  9. Confidence scoring

Fallback (when GPT-4o geometry is unavailable):
  Uses OpenCV-only path: Hough walls → Shapely polygonize → flood-fill rooms
  → gap-scan openings.
"""
import base64
import json
import logging
import os
from typing import Callable

from openai import OpenAI

from noa_api.parsing.normalizer import normalize
from noa_api.parsing.wall_detector import detect_walls, detect_hough_lines_raw
from noa_api.parsing.room_segmenter import segment_rooms
from noa_api.parsing.opening_detector import detect_openings, filter_openings_by_scale
from noa_api.parsing.scale_detector import detect_scale_from_text, detect_scale_from_rooms
from noa_api.parsing.dimension_ocr import extract_from_image as ocr_extract
from noa_api.parsing.gpt_geometry_extractor import (
    extract_geometry_with_gpt,
    rooms_from_gpt_geometry,
    walls_from_room_polygons,
    openings_from_gpt_geometry,
    merge_openings,
)

logger = logging.getLogger("noa.parsing.pipeline")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_VISION_MODEL", "gpt-4o")

# Fallback label prompt (used when GPT geometry path is unavailable)
_LABEL_PROMPT = """You are analyzing an architectural floorplan. I have detected room regions at the following pixel centroids. Assign a label to each. Also extract any dimension text visible.

Detected rooms:
{room_list}

Return ONLY valid JSON:
{{
  "room_labels": {{"room-1": "Bedroom", "room-2": "Kitchen"}},
  "dimension_text": "all dimension text as a single string",
  "sqft": null,
  "ceiling_height_text": null
}}"""


def _call_gpt_for_labels(image_bytes: bytes, mime_type: str, rooms: list) -> dict:
    """GPT-4o fallback: room labeling only (no geometry)."""
    empty = {"room_labels": {}, "dimension_text": "", "sqft": None, "ceiling_height_text": None}
    if not OPENAI_API_KEY:
        return empty

    room_list = ""
    for room in rooms:
        geo = room.get("geometry", [])
        if geo:
            cx = sum(p[0] for p in geo) / len(geo)
            cy = sum(p[1] for p in geo) / len(geo)
            room_list += f"  {room['id']}: centroid ({int(cx)},{int(cy)}), area={room.get('area_px', 0):.0f}px²\n"

    client = OpenAI(api_key=OPENAI_API_KEY)
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    media_type = mime_type if mime_type.startswith("image/") else "image/png"

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": _LABEL_PROMPT.format(room_list=room_list)},
                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}", "detail": "high"}},
            ]}],
            max_tokens=1024,
            temperature=0.1,
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = lines[1:] if lines[0].startswith("```") else lines
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines)
        return json.loads(raw)
    except Exception as e:
        logger.warning("GPT labeling failed: %s", e)
        return empty


def parse_floorplan(
    image_bytes: bytes,
    mime_type: str,
    progress_callback: Callable[[str, float], None] | None = None,
) -> dict:
    """
    Full parsing pipeline. Returns a ParsedPlan dict.

    progress_callback(stage, 0.0-1.0) is called as each stage completes
    so the async job can emit SSE progress events in real time.
    """
    def _progress(stage: str, pct: float):
        if progress_callback:
            try:
                progress_callback(stage, pct)
            except Exception:
                pass

    # ── Stage 1: Normalize ──────────────────────────────────────────
    _progress("normalizing", 0.06)
    norm = normalize(image_bytes)
    img_bin = norm["image_bin"]
    img_gray = norm.get("image_gray", img_bin)
    img_w, img_h = norm["dimensions_px"]
    bounding_box = {"min_x": 0, "min_y": 0, "max_x": img_w, "max_y": img_h}
    logger.info("Normalized: %dx%d, rotation=%.1f°, flags=%s",
                img_w, img_h, norm["rotation_degrees"], norm["quality_flags"])

    # ── Stage 1b: OCR ───────────────────────────────────────────────
    _progress("ocr_extraction", 0.11)
    ocr_result = ocr_extract(img_gray)
    dimension_text_ocr = ocr_result.get("dimension_text", "")
    sqft_ocr = ocr_result.get("sqft")
    ceiling_height_ocr = ocr_result.get("ceiling_height_m")

    # ── Stage 2: GPT-4o Primary Geometry ────────────────────────────
    _progress("gpt_geometry_extraction", 0.20)
    gpt_geo = extract_geometry_with_gpt(image_bytes, mime_type, img_w, img_h)
    use_gpt = gpt_geo is not None and len(gpt_geo.get("rooms", [])) >= 2

    # ── Stage 3: OpenCV Hough Wall Lines (for snapping + fallback) ──
    _progress("detecting_walls", 0.35)
    hough_walls = detect_walls(img_bin)
    hough_lines_raw = detect_hough_lines_raw(img_bin)
    logger.info("Hough walls: %d detected", len(hough_walls))

    # ── Stage 4: Room Polygons ───────────────────────────────────────
    _progress("building_rooms", 0.48)
    if use_gpt:
        rooms = rooms_from_gpt_geometry(gpt_geo, img_w, img_h, hough_lines_raw)
        walls = walls_from_room_polygons(rooms, img_w, img_h)
        # Keep any long Hough walls not covered by room boundaries
        walls = _supplement_walls(walls, hough_walls)
        logger.info("GPT-4o path: %d rooms, %d walls", len(rooms), len(walls))
    else:
        logger.info("GPT-4o geometry unavailable — OpenCV fallback")
        rooms = segment_rooms(img_bin, hough_walls)
        walls = hough_walls

    # ── Stage 5: Openings ───────────────────────────────────────────
    _progress("detecting_openings", 0.62)
    if use_gpt:
        gpt_openings = openings_from_gpt_geometry(gpt_geo, img_w, img_h, walls)
        cv_openings = detect_openings(img_bin, walls)
        openings = merge_openings(gpt_openings, cv_openings, merge_radius_px=22.0)
    else:
        openings = detect_openings(img_bin, walls)

    # ── Stage 6: Room Labels ─────────────────────────────────────────
    _progress("labeling_rooms", 0.74)
    dimension_text_gpt = ""
    sqft_gpt = None
    if use_gpt:
        # Labels already extracted in GPT geometry step
        label_map = {r["id"]: r.get("label", "") for r in gpt_geo.get("rooms", [])}
        for room in rooms:
            if room["id"] in label_map and label_map[room["id"]]:
                room["label"] = label_map[room["id"]]
        dimension_text_gpt = gpt_geo.get("dimension_text", "")
        sqft_gpt = gpt_geo.get("sqft_total")
    else:
        gpt_labels = _call_gpt_for_labels(image_bytes, mime_type, rooms)
        label_map = gpt_labels.get("room_labels", {})
        for room in rooms:
            if room["id"] in label_map:
                room["label"] = label_map[room["id"]]
        dimension_text_gpt = gpt_labels.get("dimension_text", "")
        sqft_gpt = gpt_labels.get("sqft")

    # ── Stage 7: Scale Detection ─────────────────────────────────────
    _progress("detecting_scale", 0.82)
    scale_hint = gpt_geo.get("scale_text", "") if gpt_geo else ""
    dimension_text = " ".join(filter(None, [
        dimension_text_ocr, dimension_text_gpt, scale_hint,
    ]))
    sqft_raw = sqft_gpt or sqft_ocr

    scale_from_text = detect_scale_from_text(dimension_text, rooms, bounding_box)
    if scale_from_text["confidence"] < 0.4:
        assumed_sqm = (sqft_raw * 0.0929) if sqft_raw else None
        scale_from_rooms = detect_scale_from_rooms(rooms, bounding_box, assumed_sqm)
        scale_info = (
            scale_from_rooms
            if scale_from_rooms["confidence"] > scale_from_text["confidence"]
            else scale_from_text
        )
    else:
        scale_info = scale_from_text

    ch_text = gpt_geo.get("ceiling_height_text") if gpt_geo else None
    if ceiling_height_ocr is not None:
        scale_info.setdefault("details", {})["ceiling_height_m"] = ceiling_height_ocr
    elif ch_text:
        scale_info.setdefault("details", {})["ceiling_height_text"] = ch_text

    px_per_m = scale_info.get("px_per_meter") or 0
    if px_per_m > 0:
        openings = filter_openings_by_scale(
            openings, px_per_m, min_width_m=0.5, max_width_m=2.5
        )

    logger.info("Scale: %.1f px/m (conf=%.2f, method=%s)",
                scale_info.get("px_per_meter", 0),
                scale_info["confidence"],
                scale_info["method"])

    # ── Stage 8: Confidence & Flags ─────────────────────────────────
    _progress("computing_confidence", 0.89)
    ambiguity_flags = list(norm.get("quality_flags", []))

    if not use_gpt:
        ambiguity_flags.append("gpt_geometry_unavailable")
    if scale_info["confidence"] < 0.5:
        ambiguity_flags.append("scale_uncertain")

    open_rooms = [r for r in rooms if r.get("open_boundary")]
    if open_rooms:
        ambiguity_flags.append(f"{len(open_rooms)}_rooms_have_open_boundaries")

    wall_confs = [w["confidence"] for w in walls]
    room_confs = [r["confidence"] for r in rooms]
    all_confs = wall_confs + room_confs
    conf_overall = float(sum(all_confs) / max(len(all_confs), 1))

    # GPT geometry is inherently higher quality
    if use_gpt:
        conf_overall = min(conf_overall * 1.12, 1.0)

    if len(walls) < 3:
        ambiguity_flags.append("very_few_walls")
        conf_overall *= 0.7
    if not rooms:
        ambiguity_flags.append("no_rooms_detected")
        conf_overall *= 0.5

    # ── Strip internal fields ────────────────────────────────────────
    clean_walls = [{
        "id": w["id"],
        "geometry": w["geometry"],
        "thickness_px": w.get("thickness_px"),
        "wall_type": w.get("wall_type"),
        "confidence": w["confidence"],
        "observation_type": w["observation_type"],
    } for w in walls]

    clean_rooms = [{
        "id": r["id"],
        "label": r.get("label"),
        "geometry": r["geometry"],
        "area_px": r.get("area_px"),
        "confidence": r["confidence"],
        "observation_type": r["observation_type"],
    } for r in rooms]

    clean_openings = [{
        "id": o["id"],
        "wall_id": o.get("wall_id"),
        "opening_type": o.get("opening_type", "door"),
        "geometry": o["geometry"],
        "position_on_wall": o.get("position_on_wall"),
        "width_px": o.get("width_px"),
        "confidence": o["confidence"],
        "observation_type": o["observation_type"],
    } for o in openings]

    ceiling_height_m = ceiling_height_ocr
    if ceiling_height_m is None:
        ceiling_height_m = scale_info.get("details", {}).get("ceiling_height_m")

    _progress("finalizing", 0.95)
    return {
        "confidence_overall": round(min(conf_overall, 1.0), 2),
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


def _supplement_walls(room_walls: list, hough_walls: list,
                       min_len_px: float = 40.0,
                       proximity_px: float = 8.0) -> list:
    """
    Add Hough-detected walls that are far from all room-boundary walls.
    This catches structural walls (like staircase dividers) that GPT may miss.
    """
    combined = list(room_walls)
    existing_mids = []
    for w in room_walls:
        pts = w.get("geometry", [])
        if len(pts) >= 2:
            mx = (pts[0][0] + pts[1][0]) / 2
            my = (pts[0][1] + pts[1][1]) / 2
            existing_mids.append((mx, my))

    r2 = proximity_px * proximity_px
    for hw in hough_walls:
        pts = hw.get("geometry", [])
        if len(pts) < 2:
            continue
        length = ((pts[1][0] - pts[0][0]) ** 2 + (pts[1][1] - pts[0][1]) ** 2) ** 0.5
        if length < min_len_px:
            continue
        mx = (pts[0][0] + pts[1][0]) / 2
        my = (pts[0][1] + pts[1][1]) / 2
        near = any((mx - ex) ** 2 + (my - ey) ** 2 < r2 for ex, ey in existing_mids)
        if not near:
            combined.append(hw)

    return combined
