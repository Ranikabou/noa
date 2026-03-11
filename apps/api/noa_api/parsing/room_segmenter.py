"""
Room segmentation: exterior-boundary primary + planar-graph + flood-fill fallback.

For open commercial floor plans (single large space + small enclosed rooms),
the standard Shapely polygonize approach fails because the main space has no
interior walls closing it off. We fix this by:

1. Primary: find the exterior floor plan boundary via RETR_EXTERNAL contour —
   this gives the overall building footprint as the "main area" polygon.
2. Secondary: find interior rooms by looking for large closed contours inside
   that exterior boundary (restrooms, storage, offices).
3. Fallback: Shapely planar graph (polygonize) for residential plans where
   every room is fully enclosed by wall centerlines.
4. Last resort: flood fill on inverted wall mask.
"""
import cv2
import numpy as np
import logging
from shapely.geometry import Polygon as ShapelyPoly, LineString, MultiLineString
from shapely.ops import polygonize

logger = logging.getLogger("noa.parsing.room_segmenter")

MIN_ROOM_AREA_PX = 400   # smaller rooms (compact restrooms) can be < 800px²
MAX_ROOM_AREA_RATIO = 0.90  # raised: main area can be most of the plan
SNAP_PX = 5
MIN_WALLS_FOR_GRAPH = 6


def _build_wall_mask(img_shape: tuple, walls: list, expansion: int = 2) -> np.ndarray:
    """Create binary mask where walls are white (255)."""
    mask = np.zeros(img_shape[:2], dtype=np.uint8)

    for wall in walls:
        poly = wall.get("polygon_px", [])
        if len(poly) >= 3:
            pts = np.array(poly, dtype=np.int32)
            cv2.fillPoly(mask, [pts], 255)
        else:
            g = wall.get("geometry", [])
            if len(g) >= 2:
                t = max(int(wall.get("thickness_px", 6)), 4)
                cv2.line(mask, tuple(g[0]), tuple(g[1]), 255, t)

    # Dilate slightly to close small gaps between wall ends
    if expansion > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (expansion * 2 + 1, expansion * 2 + 1))
        mask = cv2.dilate(mask, kernel, iterations=1)

    return mask


def _flood_fill_rooms(wall_mask: np.ndarray) -> list[np.ndarray]:
    """Flood fill on inverted wall mask to find room regions."""
    inverted = cv2.bitwise_not(wall_mask)

    # Label connected components
    num_labels, labels = cv2.connectedComponents(inverted)

    regions = []
    total_area = inverted.shape[0] * inverted.shape[1]

    for label_id in range(1, num_labels):
        region_mask = (labels == label_id).astype(np.uint8) * 255
        area = int(np.sum(region_mask > 0))

        if area < MIN_ROOM_AREA_PX:
            continue
        if area > total_area * MAX_ROOM_AREA_RATIO:
            continue  # likely the exterior

        regions.append(region_mask)

    # Sort by area descending
    regions.sort(key=lambda r: np.sum(r > 0), reverse=True)
    return regions


def _region_to_polygon(region_mask: np.ndarray) -> list[list[int]] | None:
    """Extract the largest contour from a region mask as a polygon."""
    contours, _ = cv2.findContours(region_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)

    # Simplify contour to reduce point count
    epsilon = 0.01 * cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, epsilon, True)

    if len(approx) < 3:
        return None

    return [[int(p[0][0]), int(p[0][1])] for p in approx]


def _check_open_boundary(polygon: list, wall_mask: np.ndarray) -> bool:
    """Check if a room has unclosed wall segments (gaps in boundary)."""
    if len(polygon) < 3:
        return True

    for i in range(len(polygon)):
        p1 = polygon[i]
        p2 = polygon[(i + 1) % len(polygon)]

        # Sample points along boundary segment
        n_samples = max(int(np.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) / 5), 3)
        wall_count = 0
        for t in np.linspace(0, 1, n_samples):
            px = int(p1[0] + t * (p2[0] - p1[0]))
            py = int(p1[1] + t * (p2[1] - p1[1]))
            if 0 <= py < wall_mask.shape[0] and 0 <= px < wall_mask.shape[1]:
                if wall_mask[py, px] > 0:
                    wall_count += 1

        # If less than 30% of boundary is wall, it's open
        if wall_count < n_samples * 0.3:
            return True

    return False


def _snap_pt(pt: tuple[float, float], grid: float) -> tuple[float, float]:
    return (round(pt[0] / grid) * grid, round(pt[1] / grid) * grid)


def _rooms_from_planar_graph(walls: list, img_shape: tuple) -> list[dict] | None:
    """
    Build rooms from wall centerlines using Shapely polygonize (planar graph).
    Returns list of room dicts or None if graph yields too few valid rooms.
    """
    if len(walls) < MIN_WALLS_FOR_GRAPH:
        return None

    segments = []
    for w in walls:
        g = w.get("geometry", [])
        if len(g) < 2:
            continue
        p1 = _snap_pt((float(g[0][0]), float(g[0][1])), SNAP_PX)
        p2 = _snap_pt((float(g[1][0]), float(g[1][1])), SNAP_PX)
        if abs(p1[0] - p2[0]) < 1e-6 and abs(p1[1] - p2[1]) < 1e-6:
            continue
        segments.append(LineString([p1, p2]))

    if len(segments) < 3:
        return None

    try:
        ml = MultiLineString(segments)
        polys = list(polygonize(ml.geoms))
    except Exception as e:
        logger.debug("Planar polygonize failed: %s", e)
        return None

    h, w = img_shape[:2]
    total_px = h * w
    rooms = []
    for i, poly in enumerate(polys):
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or poly.area < MIN_ROOM_AREA_PX:
            continue
        if poly.area > total_px * MAX_ROOM_AREA_RATIO:
            continue  # exterior
        coords = list(poly.exterior.coords[:-1])  # closed ring, drop duplicate end
        polygon = [[int(round(c[0])), int(round(c[1]))] for c in coords]
        if len(polygon) < 3:
            continue
        rooms.append({
            "id": f"room-{i + 1}",
            "label": None,
            "geometry": polygon,
            "area_px": round(poly.area, 1),
            "confidence": 0.9,  # graph-derived rooms share edges, higher confidence
            "observation_type": "observed",
            "open_boundary": False,
        })

    if len(rooms) >= 2:
        rooms.sort(key=lambda r: r["area_px"], reverse=True)
        logger.info("Planar graph: %d rooms from polygonize", len(rooms))
        return rooms
    return None


def _find_exterior_boundary(img_bin: np.ndarray) -> list[list[int]] | None:
    """
    Find the exterior boundary polygon of the floor plan.

    Dilates the binary image to fill small gaps between wall segments, then
    finds the outermost contour. This gives the overall building footprint
    even when the main space has no interior walls (open commercial plans).
    """
    # Dilate aggressively to merge all wall pixels into one exterior blob
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    dilated = cv2.dilate(img_bin, kernel, iterations=3)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Largest contour = floor plan boundary
    main = max(contours, key=cv2.contourArea)
    total_area = img_bin.shape[0] * img_bin.shape[1]

    if cv2.contourArea(main) < total_area * 0.01:
        return None

    # Simplify to reduce noise while preserving shape
    epsilon = 0.005 * cv2.arcLength(main, True)
    approx = cv2.approxPolyDP(main, epsilon, True)

    if len(approx) < 3:
        return None

    return [[int(p[0][0]), int(p[0][1])] for p in approx]


def _find_interior_rooms(img_bin: np.ndarray,
                          exterior_polygon: list | None,
                          min_area_px: int) -> list[dict]:
    """
    Find enclosed rooms inside the floor plan.

    Looks for closed contours in the binary image that are:
    - Significantly smaller than the exterior boundary
    - Have high solidity (area / convex_hull_area > 0.6) — filters out
      noise and partial shapes
    - Approximately rectangular or regular in shape
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    dilated = cv2.dilate(img_bin, kernel, iterations=2)

    contours, hierarchy = cv2.findContours(
        dilated, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return []

    total_area = img_bin.shape[0] * img_bin.shape[1]
    rooms = []

    for i, cnt in enumerate(contours):
        area = cv2.contourArea(cnt)
        if area < min_area_px:
            continue
        # Skip if it's the exterior boundary (> 40% of image)
        if area > total_area * 0.40:
            continue

        # Solidity check: real rooms are compact
        hull = cv2.convexHull(cnt)
        hull_area = cv2.contourArea(hull)
        if hull_area < 1:
            continue
        solidity = area / hull_area
        if solidity < 0.45:
            continue  # very irregular — likely noise or furniture cluster

        epsilon = 0.01 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        if len(approx) < 3:
            continue

        polygon = [[int(p[0][0]), int(p[0][1])] for p in approx]

        rooms.append({
            "polygon": polygon,
            "area_px": float(area),
            "solidity": solidity,
        })

    # Sort by area descending
    rooms.sort(key=lambda r: r["area_px"], reverse=True)
    return rooms


def segment_rooms(img_bin: np.ndarray, walls: list) -> list[dict]:
    """
    Full room segmentation pipeline.

    Priority order:
    1. Planar-graph (polygonize) — best for residential plans where every room
       has fully-closed wall centerlines.
    2. Exterior boundary + interior rooms — best for open commercial plans.
    3. Flood fill fallback.
    """
    h, w = img_bin.shape[:2]
    img_shape = (h, w)
    total_area = h * w

    # ── Strategy 1: Planar graph (residential/fully enclosed rooms) ──
    graph_rooms = _rooms_from_planar_graph(walls, img_shape)
    if graph_rooms is not None and len(graph_rooms) >= 2:
        return graph_rooms

    # ── Strategy 2: Exterior boundary + interior rooms ───────────────
    exterior_poly = _find_exterior_boundary(img_bin)
    interior_rooms_raw = _find_interior_rooms(img_bin, exterior_poly, MIN_ROOM_AREA_PX)

    cv_rooms = []
    room_idx = 1

    # Add the main exterior space as the primary room
    if exterior_poly and len(exterior_poly) >= 4:
        ext_area = cv2.contourArea(np.array(exterior_poly, dtype=np.int32))
        if ext_area > total_area * 0.01:
            cv_rooms.append({
                "id": f"room-{room_idx}",
                "label": None,
                "geometry": exterior_poly,
                "area_px": round(float(ext_area), 1),
                "confidence": 0.88,
                "observation_type": "observed",
                "open_boundary": False,
            })
            room_idx += 1

    # Add interior enclosed rooms (these become separate rooms inside the main space)
    wall_mask = _build_wall_mask(img_shape, walls)
    for r in interior_rooms_raw:
        poly = r["polygon"]
        area = r["area_px"]

        # Skip if it's nearly as large as the exterior (it IS the exterior)
        if exterior_poly:
            ext_area = cv_rooms[0]["area_px"] if cv_rooms else total_area
            if area > ext_area * 0.70:
                continue

        open_boundary = _check_open_boundary(poly, wall_mask)
        cv_rooms.append({
            "id": f"room-{room_idx}",
            "label": None,
            "geometry": poly,
            "area_px": round(area, 1),
            "confidence": 0.80 if open_boundary else 0.87,
            "observation_type": "observed",
            "open_boundary": open_boundary,
        })
        room_idx += 1

    if len(cv_rooms) >= 1:
        logger.info("Exterior+interior segmentation: %d rooms", len(cv_rooms))
        return cv_rooms

    # ── Strategy 3: Flood fill fallback ─────────────────────────────
    wall_mask = _build_wall_mask(img_shape, walls)
    combined_mask = cv2.bitwise_or(wall_mask, img_bin)
    regions = _flood_fill_rooms(combined_mask)
    logger.info("Flood fill: %d candidate room regions", len(regions))

    rooms = []
    for i, region in enumerate(regions):
        polygon = _region_to_polygon(region)
        if polygon is None or len(polygon) < 3:
            continue

        try:
            shapely_poly = ShapelyPoly(polygon)
            if not shapely_poly.is_valid:
                shapely_poly = shapely_poly.buffer(0)
            area_px = shapely_poly.area
        except Exception:
            area_px = cv2.contourArea(np.array(polygon))

        if area_px < MIN_ROOM_AREA_PX:
            continue

        open_boundary = _check_open_boundary(polygon, wall_mask)
        rooms.append({
            "id": f"room-{i + 1}",
            "label": None,
            "geometry": polygon,
            "area_px": round(area_px, 1),
            "confidence": 0.75 if open_boundary else 0.85,
            "observation_type": "observed",
            "open_boundary": open_boundary,
        })

    logger.info("Segmented %d rooms (flood fill)", len(rooms))
    return rooms
