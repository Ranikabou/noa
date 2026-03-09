"""
OCR-based dimension and label extraction for floorplans.

Extracts dimension strings (11'4" x 10'7", SQFT 572, CEILING HEIGHT 9'11"),
room labels, and bounding boxes. Used to calibrate scale and ceiling height.

Requires: system Tesseract (e.g. `brew install tesseract` on macOS).
If pytesseract/PIL unavailable (or e.g. NumPy 2 vs pandas/pyarrow conflict),
OCR is skipped and scale uses GPT dimension text + room-area fallback only.
Import is lazy so the parse pipeline loads even when OCR deps fail.
"""
import re
import logging
from typing import Any

import numpy as np

logger = logging.getLogger("noa.parsing.dimension_ocr")


# Imperial dimension: 11'4" x 10'7" or 11'4 x 10'7
DIMENSION_ROOM_PATTERN = re.compile(
    r"(\d+)\s*['\u2018\u2019\-]?\s*(\d+)?\s*[\"\u201C\u201D″]?\s*[xX×]\s*(\d+)\s*['\u2018\u2019\-]?\s*(\d+)?\s*[\"\u201C\u201D″]?",
    re.IGNORECASE,
)
# SQFT 572 or 572 SQFT
SQFT_PATTERN = re.compile(r"(?:SQFT|sqft|SQ\s*FT|sq\s*ft)\s*(\d+)|(\d+)\s*(?:SQFT|sqft|SQ\s*FT|sq\s*ft)", re.IGNORECASE)
# CEILING HEIGHT 9'11" or 9'11
CEILING_PATTERN = re.compile(
    r"(?:CEILING\s*HEIGHT|ceiling\s*height)\s*(\d+)\s*['\u2018\u2019\-]?\s*(\d+)?\s*[\"\u201C\u201D″]?",
    re.IGNORECASE,
)


def _imperial_to_meters(feet: int, inches: int) -> float:
    return (feet * 12 + inches) * 0.0254


def _parse_dimension_string(text: str) -> dict | None:
    """Parse '11'4" x 10'7"' into width_m, height_m (meters)."""
    m = DIMENSION_ROOM_PATTERN.search(text)
    if not m:
        return None
    try:
        f1, i1 = int(m.group(1)), int(m.group(2) or 0)
        f2, i2 = int(m.group(3)), int(m.group(4) or 0)
        w_m = _imperial_to_meters(f1, i1)
        h_m = _imperial_to_meters(f2, i2)
        if 1.0 < w_m < 25.0 and 1.0 < h_m < 25.0:
            return {"width_m": w_m, "height_m": h_m, "area_m2": w_m * h_m, "raw": text.strip()}
    except (ValueError, TypeError):
        pass
    return None


def _parse_sqft(text: str) -> int | None:
    m = SQFT_PATTERN.search(text)
    if m:
        g = m.group(1) or m.group(2)
        if g:
            v = int(g)
            if 50 < v < 50000:
                return v
    return None


def _parse_ceiling_height(text: str) -> float | None:
    m = CEILING_PATTERN.search(text)
    if m:
        try:
            f, i = int(m.group(1)), int(m.group(2) or 0)
            h_m = _imperial_to_meters(f, i)
            if 2.0 < h_m < 6.0:
                return round(h_m, 2)
        except (ValueError, TypeError):
            pass
    return None


def _identify_room_type(text: str) -> str:
    t = text.lower().strip()
    if "bed" in t:
        return "bedroom"
    if "bath" in t:
        return "bathroom"
    if "kitchenette" in t:
        return "kitchenette"
    if "kitchen" in t:
        return "kitchen"
    if "living" in t and "dining" in t:
        return "living_dining"
    if "dining" in t:
        return "dining_room"
    if "living" in t:
        return "living_room"
    if "foyer" in t or "entry" in t:
        return "foyer"
    if t == "cl" or "closet" in t:
        return "closet"
    if "hwh" in t or "water heater" in t:
        return "hwh"
    if "w/d" in t or "washer" in t:
        return "wd"
    if t == "ref" or "refrigerator" in t:
        return "ref"
    if "dw" in t or "dishwasher" in t:
        return "dw"
    return "unknown"


def extract_from_image(img_array: np.ndarray) -> dict[str, Any]:
    """
    Run Tesseract OCR on a grayscale or binary image.
    Returns:
      - full_text: raw OCR text
      - dimension_text: concatenated lines that look like dimensions
      - room_labels: list of { name, room_type, bbox, dimensions? }
      - sqft: int or None
      - ceiling_height_m: float or None
      - dimension_pairs: list of { width_m, height_m, area_m2, raw } from room dims
    """
    result = {
        "full_text": "",
        "dimension_text": "",
        "room_labels": [],
        "sqft": None,
        "ceiling_height_m": None,
        "dimension_pairs": [],
    }

    # Lazy import so API/worker start even when pytesseract or pandas/pyarrow (NumPy 2) fail
    try:
        import pytesseract
        from PIL import Image
    except Exception as e:
        logger.debug("OCR deps unavailable (pytesseract/PIL or NumPy conflict): %s", e)
        return result

    try:
        if img_array.dtype != np.uint8:
            img_array = (img_array * 255).astype(np.uint8) if img_array.max() <= 1.0 else img_array.astype(np.uint8)
        pil_img = Image.fromarray(img_array)
        data = pytesseract.image_to_data(pil_img, output_type=pytesseract.Output.DICT)
    except Exception as e:
        logger.warning("Tesseract OCR failed: %s", e)
        return result

    n_boxes = len(data["text"])
    lines: list[dict] = []
    current_line: list[tuple[str, int, int, int, int]] = []
    last_y = -1
    line_height = 20

    for i in range(n_boxes):
        text = (data["text"][i] or "").strip()
        if not text:
            continue
        x = data["left"][i]
        y = data["top"][i]
        w = data["width"][i]
        h = data["height"][i]

        if current_line and abs(y - last_y) > line_height:
            if current_line:
                lines.append(_line_from_words(current_line))
            current_line = []
        current_line.append((text, x, y, w, h))
        last_y = y

    if current_line:
        lines.append(_line_from_words(current_line))

    dim_lines = []
    for line in lines:
        text = line["text"]
        result["full_text"] += text + "\n"

        dim = _parse_dimension_string(text)
        if dim:
            result["dimension_pairs"].append(dim)
            dim_lines.append(text)

        sqft = _parse_sqft(text)
        if sqft is not None:
            result["sqft"] = sqft

        ch = _parse_ceiling_height(text)
        if ch is not None:
            result["ceiling_height_m"] = ch

        room_type = _identify_room_type(text)
        if room_type != "unknown" or dim or re.search(r"\d+['\"]", text):
            result["room_labels"].append({
                "name": text[:80],
                "room_type": room_type,
                "bbox": {"x": line["x"], "y": line["y"], "width": line["w"], "height": line["h"]},
                "dimensions": dim,
            })

    result["dimension_text"] = " ".join(dim_lines)
    logger.info("OCR: %d lines, %d dimension pairs, sqft=%s, ceiling=%s",
                len(lines), len(result["dimension_pairs"]), result["sqft"], result["ceiling_height_m"])
    return result


def _line_from_words(words: list[tuple[str, int, int, int, int]]) -> dict:
    if not words:
        return {"text": "", "x": 0, "y": 0, "w": 0, "h": 0}
    text = " ".join(w[0] for w in words)
    xs = [w[1] for w in words]
    ys = [w[2] for w in words]
    ws = [w[3] for w in words]
    hs = [w[4] for w in words]
    return {
        "text": text,
        "x": min(xs),
        "y": min(ys),
        "w": max(x + w for x, w in zip(xs, ws)) - min(xs),
        "h": max(y + h for y, h in zip(ys, hs)) - min(ys),
    }
