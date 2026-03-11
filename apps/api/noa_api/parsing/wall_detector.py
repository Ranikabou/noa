"""Wall detection via Hough lines + parallel pair matching."""
import cv2
import numpy as np
import logging
from uuid import uuid4

logger = logging.getLogger("noa.parsing.wall_detector")

MIN_WALL_LENGTH_PX = 15
MIN_WALL_THICKNESS_PX = 3
MAX_WALL_THICKNESS_PX = 80
ANGLE_TOLERANCE_DEG = 3.0
MIN_OVERLAP_RATIO = 0.3


def _hough_lines(img_bin: np.ndarray) -> list:
    """Probabilistic Hough line detection."""
    lines = cv2.HoughLinesP(
        img_bin,
        rho=1,
        theta=np.pi / 180,
        threshold=40,
        minLineLength=MIN_WALL_LENGTH_PX,
        maxLineGap=8,
    )
    if lines is None:
        return []
    return [l[0] for l in lines]


def _line_angle(x1, y1, x2, y2) -> float:
    """Angle in degrees [0, 180)."""
    return float(np.degrees(np.arctan2(y2 - y1, x2 - x1)) % 180)


def _line_length(x1, y1, x2, y2) -> float:
    return float(np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2))


def _cluster_by_angle(lines: list) -> tuple[list, list, list]:
    """Cluster lines into horizontal (~0/180), vertical (~90), and other."""
    h_lines, v_lines, other = [], [], []
    for x1, y1, x2, y2 in lines:
        angle = _line_angle(x1, y1, x2, y2)
        if angle < ANGLE_TOLERANCE_DEG or angle > 180 - ANGLE_TOLERANCE_DEG:
            h_lines.append((x1, y1, x2, y2, angle))
        elif abs(angle - 90) < ANGLE_TOLERANCE_DEG:
            v_lines.append((x1, y1, x2, y2, angle))
        else:
            other.append((x1, y1, x2, y2, angle))
    return h_lines, v_lines, other


def _perp_distance_h(line_a, line_b) -> float:
    """Perpendicular distance between two horizontal-ish lines (Y difference)."""
    ya = (line_a[1] + line_a[3]) / 2
    yb = (line_b[1] + line_b[3]) / 2
    return abs(ya - yb)


def _perp_distance_v(line_a, line_b) -> float:
    """Perpendicular distance between two vertical-ish lines (X difference)."""
    xa = (line_a[0] + line_a[2]) / 2
    xb = (line_b[0] + line_b[2]) / 2
    return abs(xa - xb)


def _overlap_h(a, b) -> float:
    """Overlap ratio for horizontal lines (X extent)."""
    a_min = min(a[0], a[2])
    a_max = max(a[0], a[2])
    b_min = min(b[0], b[2])
    b_max = max(b[0], b[2])
    overlap = max(0, min(a_max, b_max) - max(a_min, b_min))
    extent = max(a_max - a_min, b_max - b_min, 1)
    return overlap / extent


def _overlap_v(a, b) -> float:
    """Overlap ratio for vertical lines (Y extent)."""
    a_min = min(a[1], a[3])
    a_max = max(a[1], a[3])
    b_min = min(b[1], b[3])
    b_max = max(b[1], b[3])
    overlap = max(0, min(a_max, b_max) - max(a_min, b_min))
    extent = max(a_max - a_min, b_max - b_min, 1)
    return overlap / extent


def _find_parallel_pairs(lines: list, is_horizontal: bool) -> list:
    """Find pairs of parallel lines within wall thickness range."""
    pairs = []
    used = set()

    perp_fn = _perp_distance_h if is_horizontal else _perp_distance_v
    overlap_fn = _overlap_h if is_horizontal else _overlap_v

    # Sort by perpendicular position for efficient pairing
    if is_horizontal:
        lines_sorted = sorted(lines, key=lambda l: (l[1] + l[3]) / 2)
    else:
        lines_sorted = sorted(lines, key=lambda l: (l[0] + l[2]) / 2)

    for i, la in enumerate(lines_sorted):
        if i in used:
            continue
        best_j = None
        best_dist = float('inf')
        for j, lb in enumerate(lines_sorted[i + 1:], start=i + 1):
            if j in used:
                continue
            dist = perp_fn(la, lb)
            if dist < MIN_WALL_THICKNESS_PX:
                continue
            if dist > MAX_WALL_THICKNESS_PX:
                break  # sorted, so all further will be farther
            overlap = overlap_fn(la, lb)
            if overlap < MIN_OVERLAP_RATIO:
                continue
            if dist < best_dist:
                best_dist = dist
                best_j = j

        if best_j is not None:
            pairs.append((la, lines_sorted[best_j], best_dist))
            used.add(i)
            used.add(best_j)

    return pairs


def _pair_to_wall(line_a, line_b, thickness_px: float, is_horizontal: bool) -> dict:
    """Convert a line pair to a wall record with pixel polygon."""
    if is_horizontal:
        x_min = min(line_a[0], line_a[2], line_b[0], line_b[2])
        x_max = max(line_a[0], line_a[2], line_b[0], line_b[2])
        ya = (line_a[1] + line_a[3]) / 2
        yb = (line_b[1] + line_b[3]) / 2
        y_min = min(ya, yb)
        y_max = max(ya, yb)
        # Wall segment as centerline
        center_y = (y_min + y_max) / 2
        geometry = [[int(x_min), int(center_y)], [int(x_max), int(center_y)]]
        polygon = [
            [int(x_min), int(y_min)],
            [int(x_max), int(y_min)],
            [int(x_max), int(y_max)],
            [int(x_min), int(y_max)],
        ]
    else:
        y_min = min(line_a[1], line_a[3], line_b[1], line_b[3])
        y_max = max(line_a[1], line_a[3], line_b[1], line_b[3])
        xa = (line_a[0] + line_a[2]) / 2
        xb = (line_b[0] + line_b[2]) / 2
        x_min = min(xa, xb)
        x_max = max(xa, xb)
        center_x = (x_min + x_max) / 2
        geometry = [[int(center_x), int(y_min)], [int(center_x), int(y_max)]]
        polygon = [
            [int(x_min), int(y_min)],
            [int(x_max), int(y_min)],
            [int(x_max), int(y_max)],
            [int(x_min), int(y_max)],
        ]

    length = _line_length(*geometry[0], *geometry[1])
    wall_type = "exterior" if thickness_px >= 15 else "interior"

    return {
        "id": f"wall-{uuid4().hex[:6]}",
        "geometry": geometry,
        "polygon_px": polygon,
        "thickness_px": round(thickness_px, 1),
        "wall_type": wall_type,
        "orientation": "horizontal" if is_horizontal else "vertical",
        "length_px": round(length, 1),
        "confidence": 0.85,
        "observation_type": "observed",
    }


def _merge_collinear_walls(walls: list, tolerance_px: float = 10) -> list:
    """Merge walls that are collinear and nearly touching."""
    merged = []
    used = set()

    for i, wa in enumerate(walls):
        if i in used:
            continue
        current = wa.copy()
        used.add(i)

        for j, wb in enumerate(walls):
            if j in used or j == i:
                continue
            if wa["orientation"] != wb["orientation"]:
                continue

            g_a = current["geometry"]
            g_b = wb["geometry"]

            if wa["orientation"] == "horizontal":
                # Same Y level?
                cy_a = (g_a[0][1] + g_a[1][1]) / 2
                cy_b = (g_b[0][1] + g_b[1][1]) / 2
                if abs(cy_a - cy_b) > tolerance_px:
                    continue
                # Adjacent or overlapping in X?
                xa_min, xa_max = min(g_a[0][0], g_a[1][0]), max(g_a[0][0], g_a[1][0])
                xb_min, xb_max = min(g_b[0][0], g_b[1][0]), max(g_b[0][0], g_b[1][0])
                gap = max(xb_min - xa_max, xa_min - xb_max)
                if gap > tolerance_px:
                    continue
                new_x_min = min(xa_min, xb_min)
                new_x_max = max(xa_max, xb_max)
                cy = int((cy_a + cy_b) / 2)
                current["geometry"] = [[int(new_x_min), cy], [int(new_x_max), cy]]
                current["length_px"] = new_x_max - new_x_min
                used.add(j)
            else:
                cy_a = (g_a[0][0] + g_a[1][0]) / 2
                cy_b = (g_b[0][0] + g_b[1][0]) / 2
                if abs(cy_a - cy_b) > tolerance_px:
                    continue
                ya_min, ya_max = min(g_a[0][1], g_a[1][1]), max(g_a[0][1], g_a[1][1])
                yb_min, yb_max = min(g_b[0][1], g_b[1][1]), max(g_b[0][1], g_b[1][1])
                gap = max(yb_min - ya_max, ya_min - yb_max)
                if gap > tolerance_px:
                    continue
                new_y_min = min(ya_min, yb_min)
                new_y_max = max(ya_max, yb_max)
                cx = int((cy_a + cy_b) / 2)
                current["geometry"] = [[cx, int(new_y_min)], [cx, int(new_y_max)]]
                current["length_px"] = new_y_max - new_y_min
                used.add(j)

        merged.append(current)

    return merged


def _add_contour_walls(img_bin: np.ndarray, existing_walls: list) -> list:
    """Find large contours that might be thick walls not caught by Hough pairs."""
    contours, _ = cv2.findContours(img_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    extra_walls = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 200:
            continue

        x, y, w, h = cv2.boundingRect(cnt)
        aspect = max(w, h) / max(min(w, h), 1)

        # Wall-like: long and thin
        if aspect < 3:
            continue
        if min(w, h) > MAX_WALL_THICKNESS_PX:
            continue
        if max(w, h) < MIN_WALL_LENGTH_PX:
            continue

        thickness = min(w, h)
        is_h = w > h

        if is_h:
            cy = y + h // 2
            geometry = [[x, cy], [x + w, cy]]
        else:
            cx = x + w // 2
            geometry = [[cx, y], [cx, y + h]]

        # Check overlap with existing walls to avoid duplicates
        is_dup = False
        for ew in existing_walls:
            eg = ew["geometry"]
            if is_h and ew["orientation"] == "horizontal":
                ecy = (eg[0][1] + eg[1][1]) / 2
                if abs(ecy - geometry[0][1]) < 15:
                    ex_min = min(eg[0][0], eg[1][0])
                    ex_max = max(eg[0][0], eg[1][0])
                    overlap = max(0, min(ex_max, geometry[1][0]) - max(ex_min, geometry[0][0]))
                    if overlap > 0.3 * max(w, ex_max - ex_min, 1):
                        is_dup = True
                        break
            elif not is_h and ew["orientation"] == "vertical":
                ecx = (eg[0][0] + eg[1][0]) / 2
                if abs(ecx - geometry[0][0]) < 15:
                    ey_min = min(eg[0][1], eg[1][1])
                    ey_max = max(eg[0][1], eg[1][1])
                    overlap = max(0, min(ey_max, geometry[1][1]) - max(ey_min, geometry[0][1]))
                    if overlap > 0.3 * max(h, ey_max - ey_min, 1):
                        is_dup = True
                        break

        if not is_dup:
            extra_walls.append({
                "id": f"wall-{uuid4().hex[:6]}",
                "geometry": geometry,
                "polygon_px": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
                "thickness_px": float(thickness),
                "wall_type": "exterior" if thickness >= 15 else "interior",
                "orientation": "horizontal" if is_h else "vertical",
                "length_px": float(max(w, h)),
                "confidence": 0.70,
                "observation_type": "observed",
            })

    return extra_walls


def _deduplicate_walls(walls: list) -> list:
    """Remove walls that overlap significantly (same position)."""
    keep = []
    used = set()

    for i, wa in enumerate(walls):
        if i in used:
            continue
        best = wa
        for j, wb in enumerate(walls):
            if j <= i or j in used:
                continue
            if wa["orientation"] != wb["orientation"]:
                continue

            ga = wa["geometry"]
            gb = wb["geometry"]

            if wa["orientation"] == "horizontal":
                cy_a = (ga[0][1] + ga[1][1]) / 2
                cy_b = (gb[0][1] + gb[1][1]) / 2
                if abs(cy_a - cy_b) > 25:
                    continue
                xa = (min(ga[0][0], ga[1][0]), max(ga[0][0], ga[1][0]))
                xb = (min(gb[0][0], gb[1][0]), max(gb[0][0], gb[1][0]))
                overlap = max(0, min(xa[1], xb[1]) - max(xa[0], xb[0]))
                max_len = max(xa[1] - xa[0], xb[1] - xb[0], 1)
                if overlap / max_len > 0.4:
                    used.add(j)
                    if wb.get("thickness_px", 0) > best.get("thickness_px", 0):
                        best = wb
            else:
                cx_a = (ga[0][0] + ga[1][0]) / 2
                cx_b = (gb[0][0] + gb[1][0]) / 2
                if abs(cx_a - cx_b) > 25:
                    continue
                ya = (min(ga[0][1], ga[1][1]), max(ga[0][1], ga[1][1]))
                yb = (min(gb[0][1], gb[1][1]), max(gb[0][1], gb[1][1]))
                overlap = max(0, min(ya[1], yb[1]) - max(ya[0], yb[0]))
                max_len = max(ya[1] - ya[0], yb[1] - yb[0], 1)
                if overlap / max_len > 0.4:
                    used.add(j)
                    if wb.get("thickness_px", 0) > best.get("thickness_px", 0):
                        best = wb

        keep.append(best)
        used.add(i)

    return keep


def detect_walls(img_bin: np.ndarray) -> list[dict]:
    """Full wall detection pipeline: Hough + pair matching + contour fallback + merging."""
    lines = _hough_lines(img_bin)
    logger.info("Hough detected %d line segments", len(lines))

    h_lines, v_lines, other = _cluster_by_angle(lines)
    logger.info("Clustered: %d horizontal, %d vertical, %d other", len(h_lines), len(v_lines), len(other))

    walls = []
    h_pairs = _find_parallel_pairs(h_lines, is_horizontal=True)
    for la, lb, dist in h_pairs:
        walls.append(_pair_to_wall(la, lb, dist, is_horizontal=True))

    v_pairs = _find_parallel_pairs(v_lines, is_horizontal=False)
    for la, lb, dist in v_pairs:
        walls.append(_pair_to_wall(la, lb, dist, is_horizontal=False))

    logger.info("Parallel pair walls: %d", len(walls))

    # Add contour-based walls for thick/prominent walls
    extra = _add_contour_walls(img_bin, walls)
    walls.extend(extra)
    logger.info("After contour addition: %d walls", len(walls))

    # Merge collinear segments
    walls = _merge_collinear_walls(walls)
    logger.info("After merging: %d walls", len(walls))

    # Recompute length_px for all walls after merging
    for w in walls:
        g = w["geometry"]
        if len(g) >= 2:
            w["length_px"] = round(_line_length(g[0][0], g[0][1], g[1][0], g[1][1]), 1)

    # Remove very short walls (likely noise)
    walls = [w for w in walls if w["length_px"] >= MIN_WALL_LENGTH_PX]

    # Remove duplicate walls (same location, keep the thicker / more confident one)
    walls = _deduplicate_walls(walls)

    # Sort by length descending (most significant walls first)
    walls.sort(key=lambda w: w["length_px"], reverse=True)

    return walls


def detect_hough_lines_raw(img_bin: np.ndarray) -> list:
    """
    Return raw Hough line segments as minimal wall dicts (id + geometry only).

    Used by the GPT geometry extractor as snap targets: polygon vertices from
    GPT-4o are snapped to the nearest intersection of these raw lines, giving
    pixel-level precision without the full parallel-pair matching overhead.

    Returns more lines than detect_walls() (lower threshold, shorter min length)
    to maximize snap coverage.
    """
    lines = cv2.HoughLinesP(
        img_bin,
        rho=1,
        theta=np.pi / 180,
        threshold=25,           # lower threshold → more candidate lines
        minLineLength=10,       # shorter minimum → catch short wall segments
        maxLineGap=12,
    )
    if lines is None:
        return []

    raw = []
    for i, l in enumerate(lines):
        x1, y1, x2, y2 = l[0]
        raw.append({
            "id": f"raw-{i}",
            "geometry": [[int(x1), int(y1)], [int(x2), int(y2)]],
            "confidence": 0.5,
            "observation_type": "observed",
        })
    return raw
