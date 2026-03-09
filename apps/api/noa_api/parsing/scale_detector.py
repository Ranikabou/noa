"""Scale detection: dimension text OCR + known element sizing."""
import re
import logging
import numpy as np

logger = logging.getLogger("noa.parsing.scale_detector")

DIMENSION_PATTERNS = [
    # Imperial: 11'4" × 10'7"  or  11'4" x 10'7"
    (r"(\d+)\s*['\u2018\u2019]\s*(\d+)\s*[\"\u201C\u201D]?\s*[x×X\u00D7]\s*(\d+)\s*['\u2018\u2019]\s*(\d+)\s*[\"\u201C\u201D]?",
     "imperial_room"),
    # Imperial single: 11'4"
    (r"(\d+)\s*['\u2018\u2019]\s*(\d+)\s*[\"\u201C\u201D]?", "imperial_dim"),
    # Metric: 5.2m or 5.2 m
    (r"(\d+\.?\d*)\s*m(?:\b|$)", "metric"),
    # SQFT / sqft
    (r"(?:SQFT|sqft|SQ\s*FT|sq\s*ft)\s*(\d+)", "sqft"),
    (r"(\d+)\s*(?:SQFT|sqft|SQ\s*FT|sq\s*ft)", "sqft"),
    # Ceiling height: 9'11"
    (r"(?:CEILING\s*HEIGHT|ceiling\s*height)\s*(\d+)\s*['\u2018\u2019]\s*(\d+)\s*[\"\u201C\u201D]?",
     "ceiling_height"),
    # Scale notation: 1:50
    (r"1\s*:\s*(\d+)", "scale_ratio"),
]


def _imperial_to_meters(feet: int, inches: int) -> float:
    return (feet * 12 + inches) * 0.0254


def detect_scale_from_text(text_content: str, rooms: list, bounding_box: dict) -> dict:
    """
    Try to determine px_per_meter from text annotations on the plan.
    Uses room dimension labels matched to room polygon sizes.
    """
    results = {
        "px_per_meter": None,
        "confidence": 0.0,
        "method": "none",
        "details": {},
    }

    if not text_content:
        return results

    # Try to find SQFT
    sqft_match = None
    for pattern, ptype in DIMENSION_PATTERNS:
        for m in re.finditer(pattern, text_content, re.IGNORECASE):
            if ptype == "sqft":
                try:
                    sqft = int(m.group(1))
                    if 50 < sqft < 50000:
                        sqft_match = sqft
                        results["details"]["sqft"] = sqft
                except (ValueError, IndexError):
                    pass

    # Try to find room dimensions in imperial
    room_dims_m = []
    for pattern, ptype in DIMENSION_PATTERNS:
        if ptype != "imperial_room":
            continue
        for m in re.finditer(pattern, text_content, re.IGNORECASE):
            try:
                w_m = _imperial_to_meters(int(m.group(1)), int(m.group(2)))
                h_m = _imperial_to_meters(int(m.group(3)), int(m.group(4)))
                if 1.0 < w_m < 20.0 and 1.0 < h_m < 20.0:
                    room_dims_m.append((w_m, h_m, w_m * h_m))
            except (ValueError, IndexError):
                pass

    # Try ceiling height
    for pattern, ptype in DIMENSION_PATTERNS:
        if ptype != "ceiling_height":
            continue
        for m in re.finditer(pattern, text_content, re.IGNORECASE):
            try:
                ch = _imperial_to_meters(int(m.group(1)), int(m.group(2)))
                if 2.0 < ch < 6.0:
                    results["details"]["ceiling_height_m"] = round(ch, 2)
            except (ValueError, IndexError):
                pass

    # Method 1: use sqft + bounding box to estimate scale
    if sqft_match and bounding_box:
        total_sqm = sqft_match * 0.0929
        bbox_w = bounding_box.get("max_x", 0) - bounding_box.get("min_x", 0)
        bbox_h = bounding_box.get("max_y", 0) - bounding_box.get("min_y", 0)
        bbox_area_px = bbox_w * bbox_h
        if bbox_area_px > 0:
            # Assume rooms fill ~60-80% of bounding box
            fill_ratio = 0.7
            room_area_px = bbox_area_px * fill_ratio
            px_per_sqm = room_area_px / total_sqm
            results["px_per_meter"] = float(np.sqrt(px_per_sqm))
            results["confidence"] = 0.65
            results["method"] = "sqft_bbox"

    # Method 2: match room dimensions to room polygons
    if room_dims_m and rooms:
        # Sort both by area for matching
        room_dims_m.sort(key=lambda x: x[2], reverse=True)
        rooms_by_area = sorted(rooms, key=lambda r: r.get("area_px", 0), reverse=True)

        scales = []
        for dim, room in zip(room_dims_m, rooms_by_area):
            real_area = dim[2]
            px_area = room.get("area_px", 0)
            if px_area > 0 and real_area > 0:
                scale = float(np.sqrt(px_area / real_area))
                scales.append(scale)

        if scales:
            median_scale = float(np.median(scales))
            results["px_per_meter"] = median_scale
            results["confidence"] = min(0.8, 0.5 + 0.1 * len(scales))
            results["method"] = "room_dim_matching"

    return results


def detect_scale_from_rooms(rooms: list, bounding_box: dict,
                            assumed_total_sqm: float | None = None) -> dict:
    """
    Fallback scale estimation from room areas.
    If assumed_total_sqm is provided (e.g., from SQFT annotation), use it.
    Otherwise estimate from typical building size.
    """
    total_room_area_px = sum(r.get("area_px", 0) for r in rooms)
    if total_room_area_px < 100:
        bbox_w = bounding_box.get("max_x", 0) - bounding_box.get("min_x", 0)
        bbox_h = bounding_box.get("max_y", 0) - bounding_box.get("min_y", 0)
        total_room_area_px = bbox_w * bbox_h * 0.6

    if assumed_total_sqm:
        real_area = assumed_total_sqm
    else:
        real_area = max(total_room_area_px * (15.0 / max(
            bounding_box.get("max_x", 1) - bounding_box.get("min_x", 0),
            bounding_box.get("max_y", 1) - bounding_box.get("min_y", 0),
        )) ** 2, 20.0)

    if total_room_area_px > 0 and real_area > 0:
        px_per_meter = float(np.sqrt(total_room_area_px / real_area))
        return {
            "px_per_meter": px_per_meter,
            "confidence": 0.35,
            "method": "area_estimation",
            "details": {"assumed_sqm": round(real_area, 1)},
        }

    return {
        "px_per_meter": 50.0,
        "confidence": 0.1,
        "method": "fallback",
        "details": {},
    }
