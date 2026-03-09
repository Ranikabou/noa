"""Room segmentation: planar-graph (Shapely polygonize) with flood-fill fallback."""
import cv2
import numpy as np
import logging
from shapely.geometry import Polygon as ShapelyPoly, LineString, MultiLineString
from shapely.ops import polygonize

logger = logging.getLogger("noa.parsing.room_segmenter")

MIN_ROOM_AREA_PX = 800  # below this = not a real room (closet/duct at most)
MAX_ROOM_AREA_RATIO = 0.45  # room can't be > 45% of total plan area (excludes exterior)
SNAP_PX = 5  # snap wall endpoints within this distance for planar graph
MIN_WALLS_FOR_GRAPH = 6  # need enough walls to form closed loops


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


def segment_rooms(img_bin: np.ndarray, walls: list) -> list[dict]:
    """Full room segmentation: try planar-graph (polygonize) first, then flood fill."""
    h, w = img_bin.shape[:2]
    img_shape = (h, w)

    # Try planar-graph extraction first (non-overlapping, shared-edge rooms)
    graph_rooms = _rooms_from_planar_graph(walls, img_shape)
    if graph_rooms is not None and len(graph_rooms) >= 2:
        return graph_rooms

    # Fallback: wall mask + flood fill
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

    logger.info("Segmented %d rooms", len(rooms))
    return rooms
