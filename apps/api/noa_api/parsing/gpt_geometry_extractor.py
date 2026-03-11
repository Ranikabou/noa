"""
GPT-4o Vision primary geometry extractor for floorplans.

Uses GPT-4o Vision as the primary semantic engine to extract rooms,
doors, and windows from a floorplan image. Returns normalized 0-100
coordinates that are then snapped to OpenCV-detected wall line intersections
for pixel-level precision.

This replaces brittle Hough+Shapely room segmentation with a model that
actually understands architectural drawings.
"""
import base64
import json
import logging
import os

import numpy as np

logger = logging.getLogger("noa.parsing.gpt_geometry")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_VISION_MODEL", "gpt-4o")

GEOMETRY_PROMPT = """You are an expert architectural drawing interpreter.
Analyze this floorplan image and extract the COMPLETE geometric layout.

COORDINATE SYSTEM:
- The image maps to a 0-100 grid: (0,0) = TOP-LEFT, (100,100) = BOTTOM-RIGHT
- x increases left→right, y increases top→bottom

Return ONLY valid JSON (no markdown, no explanation):
{
  "rooms": [
    {
      "id": "room-1",
      "label": "Master Bedroom",
      "type": "bedroom",
      "polygon_pct": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    }
  ],
  "doors": [
    {
      "id": "door-1",
      "center_pct": [cx, cy],
      "width_pct": 3.5,
      "wall_vec_pct": [[wx1,wy1],[wx2,wy2]]
    }
  ],
  "windows": [
    {
      "id": "window-1",
      "center_pct": [cx, cy],
      "width_pct": 5.0,
      "wall_vec_pct": [[wx1,wy1],[wx2,wy2]]
    }
  ],
  "dimension_text": "all dimension annotations as one string",
  "sqft_total": null,
  "scale_text": null,
  "ceiling_height_text": null
}

RULES — read carefully:
1. Include EVERY enclosed space: bedrooms, bathrooms, kitchen, living, dining,
   garage, storage, deck, porch, covered porch, closets, hallways, staircase area,
   laundry, utility. If it has walls, include it.
2. Room polygons: minimum 4 vertices, trace the ACTUAL shape.
   For rectangular rooms: 4 corner points in clockwise order.
   For L-shaped or irregular rooms: use 6-8 vertices following the real outline.
3. Adjacent rooms MUST share wall coordinates at their common boundary
   (same coordinate values where rooms touch).
4. Doors: identified by quarter-circle arc symbol.
   center_pct = midpoint of the door opening gap.
   wall_vec_pct = the two endpoints of the wall segment containing the door.
5. Windows: identified by parallel lines / notch symbol on a wall.
   center_pct = midpoint of the window. wall_vec_pct = wall segment endpoints.
6. All coordinates are PERCENTAGES of image dimensions (0.0 to 100.0).
7. Extract ALL visible dimension text, sqft numbers, scale ratios.
8. Every room polygon must be a CLOSED shape (last vertex connects back to first).
"""


def extract_geometry_with_gpt(image_bytes: bytes, mime_type: str,
                               img_w: int, img_h: int) -> dict | None:
    """
    Primary geometry extraction using GPT-4o Vision.

    Returns normalized geometry dict with:
      - rooms: list of {id, label, type, polygon_pct}
      - doors: list of {id, center_pct, width_pct, wall_vec_pct}
      - windows: list of {id, center_pct, width_pct, wall_vec_pct}
      - dimension_text, sqft_total, scale_text, ceiling_height_text

    All polygon/position coordinates are in 0-100 normalized space
    (percent of image width/height).
    """
    if not OPENAI_API_KEY:
        logger.warning("No OPENAI_API_KEY — skipping GPT-4o geometry extraction")
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
    except ImportError:
        logger.warning("openai package not available")
        return None

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    media_type = mime_type if mime_type.startswith("image/") else "image/png"

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": GEOMETRY_PROMPT},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{media_type};base64,{b64}",
                        "detail": "high",
                    }},
                ],
            }],
            max_tokens=4096,
            temperature=0.0,
        )

        raw = response.choices[0].message.content.strip()
        raw = _clean_json_response(raw)
        geo = json.loads(raw)
        geo = _validate_and_normalize(geo)

        logger.info(
            "GPT-4o geometry: %d rooms, %d doors, %d windows",
            len(geo.get("rooms", [])),
            len(geo.get("doors", [])),
            len(geo.get("windows", [])),
        )
        return geo

    except json.JSONDecodeError as e:
        logger.warning("GPT-4o geometry JSON parse failed: %s", e)
        return None
    except Exception as e:
        logger.warning("GPT-4o geometry extraction failed: %s", e)
        return None


def _clean_json_response(raw: str) -> str:
    """Strip markdown code fences from a JSON response."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = lines[1:] if lines[0].startswith("```") else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    return raw


def _validate_and_normalize(geo: dict) -> dict:
    """Validate structure, clamp coords to 0-100, discard degenerate entries."""
    out = {
        "rooms": [],
        "doors": [],
        "windows": [],
        "dimension_text": str(geo.get("dimension_text", "") or ""),
        "sqft_total": _safe_int(geo.get("sqft_total")),
        "scale_text": geo.get("scale_text"),
        "ceiling_height_text": geo.get("ceiling_height_text"),
    }

    for i, room in enumerate(geo.get("rooms", [])):
        poly = room.get("polygon_pct", [])
        if not poly or len(poly) < 3:
            continue
        try:
            clamped = [[_clamp(float(p[0])), _clamp(float(p[1]))] for p in poly]
        except (TypeError, ValueError, IndexError):
            continue
        # Discard degenerate (all points identical)
        xs = [p[0] for p in clamped]
        ys = [p[1] for p in clamped]
        if max(xs) - min(xs) < 0.5 and max(ys) - min(ys) < 0.5:
            continue
        out["rooms"].append({
            "id": room.get("id") or f"room-{i + 1}",
            "label": str(room.get("label", f"Room {i + 1}")),
            "type": str(room.get("type", "unknown")),
            "polygon_pct": clamped,
        })

    for i, door in enumerate(geo.get("doors", [])):
        center = door.get("center_pct", [])
        if not center or len(center) < 2:
            continue
        try:
            cx, cy = _clamp(float(center[0])), _clamp(float(center[1]))
            width = max(0.5, min(15.0, float(door.get("width_pct", 3.0))))
        except (TypeError, ValueError):
            continue
        wall_vec = door.get("wall_vec_pct", [])
        if wall_vec and len(wall_vec) >= 2:
            try:
                wall_vec = [[_clamp(float(p[0])), _clamp(float(p[1]))] for p in wall_vec[:2]]
            except (TypeError, ValueError, IndexError):
                wall_vec = []
        out["doors"].append({
            "id": door.get("id") or f"door-{i + 1}",
            "center_pct": [cx, cy],
            "width_pct": width,
            "wall_vec_pct": wall_vec,
        })

    for i, win in enumerate(geo.get("windows", [])):
        center = win.get("center_pct", [])
        if not center or len(center) < 2:
            continue
        try:
            cx, cy = _clamp(float(center[0])), _clamp(float(center[1]))
            width = max(0.5, min(25.0, float(win.get("width_pct", 5.0))))
        except (TypeError, ValueError):
            continue
        wall_vec = win.get("wall_vec_pct", [])
        if wall_vec and len(wall_vec) >= 2:
            try:
                wall_vec = [[_clamp(float(p[0])), _clamp(float(p[1]))] for p in wall_vec[:2]]
            except (TypeError, ValueError, IndexError):
                wall_vec = []
        out["windows"].append({
            "id": win.get("id") or f"window-{i + 1}",
            "center_pct": [cx, cy],
            "width_pct": width,
            "wall_vec_pct": wall_vec,
        })

    return out


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def _safe_int(v) -> int | None:
    try:
        iv = int(v)
        return iv if 50 < iv < 100_000 else None
    except (TypeError, ValueError):
        return None


# ─── Coordinate Conversion ────────────────────────────────────────


def pct_to_px(pct_coord: list, img_w: int, img_h: int) -> list:
    """Convert a 0-100 normalized coordinate to pixel coordinates."""
    return [pct_coord[0] / 100.0 * img_w, pct_coord[1] / 100.0 * img_h]


def polygon_pct_to_px(polygon_pct: list, img_w: int, img_h: int) -> list:
    """Convert a list of 0-100 polygon vertices to pixel coordinates."""
    return [pct_to_px(p, img_w, img_h) for p in polygon_pct]


# ─── Vertex Snapping ─────────────────────────────────────────────


def snap_polygon_to_walls(polygon_px: list, hough_lines: list,
                           snap_radius_px: float = 14.0) -> list:
    """
    Snap each polygon vertex to the nearest Hough line intersection within
    snap_radius_px. This corrects GPT-4o's approximate coordinates to actual
    wall line intersection points detected by OpenCV.

    Vertices with no nearby intersection are kept at their original position.
    """
    if not hough_lines or not polygon_px:
        return polygon_px

    intersections = _compute_intersections(hough_lines)
    if not intersections:
        return polygon_px

    snapped = []
    for vertex in polygon_px:
        best_pt = vertex
        best_dist_sq = snap_radius_px * snap_radius_px
        for ix, iy in intersections:
            dx = ix - vertex[0]
            dy = iy - vertex[1]
            dist_sq = dx * dx + dy * dy
            if dist_sq < best_dist_sq:
                best_dist_sq = dist_sq
                best_pt = [ix, iy]
        snapped.append(best_pt)
    return snapped


def _compute_intersections(hough_lines: list) -> list[tuple[float, float]]:
    """Compute pairwise intersections of wall centerlines for snap targets."""
    segments = []
    for w in hough_lines:
        pts = w.get("geometry", [])
        if len(pts) >= 2:
            segments.append((
                float(pts[0][0]), float(pts[0][1]),
                float(pts[1][0]), float(pts[1][1]),
            ))

    intersections = []
    for i in range(len(segments)):
        for j in range(i + 1, len(segments)):
            pt = _segment_intersection(segments[i], segments[j])
            if pt is not None:
                intersections.append(pt)
    return intersections


def _segment_intersection(l1: tuple, l2: tuple) -> tuple[float, float] | None:
    """Compute intersection of two lines (as infinite lines through their segment endpoints)."""
    x1, y1, x2, y2 = l1
    x3, y3, x4, y4 = l2

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-8:
        return None  # parallel

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    ix = x1 + t * (x2 - x1)
    iy = y1 + t * (y2 - y1)
    return (ix, iy)


# ─── Wall Reconstruction from Room Polygons ───────────────────────


def walls_from_room_polygons(rooms: list, img_w: int, img_h: int,
                              min_wall_len_px: float = 10.0) -> list:
    """
    Extract wall segments from the boundaries of room polygons.

    Strategy:
    - Every room edge is a candidate wall segment.
    - Edges shared between two rooms become interior walls (thinner).
    - Edges not shared with any other room become exterior walls (thicker).
    - Deduplicate by merging segments closer than 3px.
    """
    from shapely.geometry import LineString

    # Collect all edges with their room IDs
    edge_map: dict[tuple, list[str]] = {}  # (rounded_key) -> [room_ids]

    def _edge_key(p1, p2):
        # Normalize direction so (A→B) and (B→A) hash the same
        a = (round(p1[0], 1), round(p1[1], 1))
        b = (round(p2[0], 1), round(p2[1], 1))
        return (min(a, b), max(a, b))

    for room in rooms:
        poly = room.get("geometry", [])
        rid = room["id"]
        n = len(poly)
        for i in range(n):
            p1 = poly[i]
            p2 = poly[(i + 1) % n]
            key = _edge_key(p1, p2)
            if key not in edge_map:
                edge_map[key] = []
            edge_map[key].append(rid)

    walls = []
    for idx, (key, room_ids) in enumerate(edge_map.items()):
        p1 = list(key[0])
        p2 = list(key[1])
        length = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
        if length < min_wall_len_px:
            continue

        is_shared = len(room_ids) >= 2
        wall_type = "interior" if is_shared else "exterior"
        thickness = 8 if is_shared else 15  # px estimate

        walls.append({
            "id": f"wall-{idx}",
            "geometry": [p1, p2],
            "thickness_px": thickness,
            "wall_type": wall_type,
            "confidence": 0.93 if is_shared else 0.88,
            "observation_type": "observed",
        })

    logger.info(
        "Wall reconstruction from rooms: %d total (%d interior, %d exterior)",
        len(walls),
        sum(1 for w in walls if w["wall_type"] == "interior"),
        sum(1 for w in walls if w["wall_type"] == "exterior"),
    )
    return walls


def openings_from_gpt_geometry(gpt_geo: dict, img_w: int, img_h: int,
                                walls: list) -> list:
    """
    Convert GPT-4o door/window data to ParsedOpening dicts with pixel geometry.

    GPT gives center_pct + width_pct; we build a 2-point geometry segment
    perpendicular to the wall vector (or horizontal if wall_vec not given).
    """
    openings = []
    opening_idx = 0

    def _make_opening(center_pct, width_pct, wall_vec_pct, opening_type):
        nonlocal opening_idx
        cx = center_pct[0] / 100.0 * img_w
        cy = center_pct[1] / 100.0 * img_h
        width_px = width_pct / 100.0 * img_w

        if wall_vec_pct and len(wall_vec_pct) >= 2:
            wx1 = wall_vec_pct[0][0] / 100.0 * img_w
            wy1 = wall_vec_pct[0][1] / 100.0 * img_h
            wx2 = wall_vec_pct[1][0] / 100.0 * img_w
            wy2 = wall_vec_pct[1][1] / 100.0 * img_h
            dx = wx2 - wx1
            dy = wy2 - wy1
            wlen = (dx * dx + dy * dy) ** 0.5 or 1.0
            ux, uy = dx / wlen, dy / wlen  # unit vector along wall
        else:
            # Fall back: guess horizontal or vertical from center position
            ux, uy = 1.0, 0.0

        half = width_px / 2.0
        p1 = [cx - ux * half, cy - uy * half]
        p2 = [cx + ux * half, cy + uy * half]

        # Find closest wall for wall_id
        wall_id = _find_closest_wall_id(cx, cy, walls)

        opening_idx += 1
        return {
            "id": f"opening-gpt-{opening_idx}",
            "wall_id": wall_id,
            "opening_type": opening_type,
            "geometry": [p1, p2],
            "position_on_wall": None,
            "width_px": width_px,
            "confidence": 0.88,
            "observation_type": "observed",
        }

    for door in gpt_geo.get("doors", []):
        o = _make_opening(
            door["center_pct"],
            door["width_pct"],
            door.get("wall_vec_pct", []),
            "door",
        )
        openings.append(o)

    for win in gpt_geo.get("windows", []):
        o = _make_opening(
            win["center_pct"],
            win["width_pct"],
            win.get("wall_vec_pct", []),
            "window",
        )
        openings.append(o)

    logger.info(
        "GPT openings placed: %d doors, %d windows",
        sum(1 for o in openings if o["opening_type"] == "door"),
        sum(1 for o in openings if o["opening_type"] == "window"),
    )
    return openings


def _find_closest_wall_id(cx: float, cy: float, walls: list) -> str | None:
    """Return the ID of the wall whose midpoint is nearest to (cx, cy)."""
    best_id = None
    best_dist = float("inf")
    for wall in walls:
        pts = wall.get("geometry", [])
        if len(pts) < 2:
            continue
        mx = (pts[0][0] + pts[1][0]) / 2
        my = (pts[0][1] + pts[1][1]) / 2
        dist = (mx - cx) ** 2 + (my - cy) ** 2
        if dist < best_dist:
            best_dist = dist
            best_id = wall["id"]
    return best_id


def merge_openings(gpt_openings: list, cv_openings: list,
                   merge_radius_px: float = 25.0) -> list:
    """
    Merge GPT-4o openings and CV-detected openings.

    GPT openings take precedence; CV openings that don't overlap any GPT
    opening within merge_radius_px are appended (as supplemental detections).
    """
    merged = list(gpt_openings)
    r2 = merge_radius_px * merge_radius_px

    def _center(o):
        geo = o.get("geometry", [])
        if not geo:
            return None
        if len(geo) >= 2:
            return ((geo[0][0] + geo[1][0]) / 2, (geo[0][1] + geo[1][1]) / 2)
        return (geo[0][0], geo[0][1])

    gpt_centers = [_center(o) for o in gpt_openings]

    for cv_o in cv_openings:
        cv_c = _center(cv_o)
        if cv_c is None:
            continue
        too_close = False
        for gc in gpt_centers:
            if gc is None:
                continue
            dx = cv_c[0] - gc[0]
            dy = cv_c[1] - gc[1]
            if dx * dx + dy * dy < r2:
                too_close = True
                break
        if not too_close:
            merged.append(cv_o)

    return merged


def rooms_from_gpt_geometry(gpt_geo: dict, img_w: int, img_h: int,
                             hough_walls: list) -> list:
    """
    Convert GPT-4o room data to ParsedRoom dicts with pixel polygon geometry.

    1. Converts 0-100 polygon_pct → pixel coordinates
    2. Snaps vertices to Hough line intersections (improves precision)
    3. Computes area_px using Shoelace formula
    4. Assigns confidence based on polygon quality
    """
    rooms = []
    for room in gpt_geo.get("rooms", []):
        poly_pct = room.get("polygon_pct", [])
        if len(poly_pct) < 3:
            continue

        # Convert to pixels
        poly_px = polygon_pct_to_px(poly_pct, img_w, img_h)

        # Snap to Hough intersections for pixel precision
        poly_px = snap_polygon_to_walls(poly_px, hough_walls, snap_radius_px=14.0)

        # Compute area
        area = _shoelace_area(poly_px)
        if area < 100:  # skip tiny polygons (< 100 px²)
            continue

        rooms.append({
            "id": room["id"],
            "label": room.get("label"),
            "geometry": poly_px,
            "area_px": area,
            "confidence": 0.92,
            "observation_type": "observed",
        })

    logger.info("GPT rooms → %d valid room polygons", len(rooms))
    return rooms


def _shoelace_area(pts: list) -> float:
    """Compute polygon area in pixels using the Shoelace formula."""
    n = len(pts)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1]
        area -= pts[j][0] * pts[i][0]  # intentional: Shoelace
    # Correct Shoelace:
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1]
        area -= pts[j][0] * pts[i][1]
    return abs(area) / 2.0
