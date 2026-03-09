"""Opening detection: gaps in walls + arc detection for doors."""
import cv2
import numpy as np
import logging
from uuid import uuid4

logger = logging.getLogger("noa.parsing.opening_detector")

MIN_OPENING_WIDTH_PX = 25
MAX_OPENING_WIDTH_PX = 200


def _detect_door_arcs(img_bin: np.ndarray) -> list[dict]:
    """Detect door swing arcs using HoughCircles for partial arcs."""
    # Thin the binary image to get cleaner arc detection
    thinned = cv2.ximgproc.thinning(img_bin) if hasattr(cv2, 'ximgproc') else img_bin

    circles = cv2.HoughCircles(
        thinned,
        cv2.HOUGH_GRADIENT,
        dp=1.5,
        minDist=30,
        param1=80,
        param2=30,
        minRadius=15,
        maxRadius=80,
    )

    arcs = []
    if circles is not None:
        for c in circles[0]:
            arcs.append({
                "center": (int(c[0]), int(c[1])),
                "radius": int(c[2]),
            })

    return arcs


def _find_wall_gaps(walls: list, img_bin: np.ndarray) -> list[dict]:
    """Find gaps in walls by scanning wall lines for discontinuities."""
    gaps = []

    for wall in walls:
        g = wall.get("geometry", [])
        if len(g) < 2:
            continue

        p1 = np.array(g[0], dtype=float)
        p2 = np.array(g[1], dtype=float)
        wall_vec = p2 - p1
        wall_len = np.linalg.norm(wall_vec)
        if wall_len < 20:
            continue

        wall_dir = wall_vec / wall_len
        thickness = wall.get("thickness_px", 10)

        # Normal direction for scanning across wall
        normal = np.array([-wall_dir[1], wall_dir[0]])

        # Sample along wall centerline
        n_samples = int(wall_len / 2)
        intensity_profile = []

        for si in range(n_samples):
            t = si / max(n_samples - 1, 1)
            center = p1 + t * wall_vec

            # Sample across wall width
            total_ink = 0
            n_cross = max(int(thickness), 5)
            for ci in range(-n_cross, n_cross + 1):
                sample_pt = center + ci * normal
                sx, sy = int(sample_pt[0]), int(sample_pt[1])
                if 0 <= sy < img_bin.shape[0] and 0 <= sx < img_bin.shape[1]:
                    total_ink += int(img_bin[sy, sx])

            intensity_profile.append((t, total_ink / max(2 * n_cross + 1, 1)))

        # Find gaps: regions where intensity drops below threshold
        threshold = 60  # average pixel value across wall cross-section
        in_gap = False
        gap_start = 0.0

        for t, intensity in intensity_profile:
            if intensity < threshold and not in_gap:
                in_gap = True
                gap_start = t
            elif intensity >= threshold and in_gap:
                in_gap = False
                gap_width_px = (t - gap_start) * wall_len
                if MIN_OPENING_WIDTH_PX < gap_width_px < MAX_OPENING_WIDTH_PX:
                    gap_center = (gap_start + t) / 2
                    center_pt = p1 + gap_center * wall_vec
                    half_w = gap_width_px / 2
                    pt1 = center_pt - half_w * wall_dir
                    pt2 = center_pt + half_w * wall_dir

                    gaps.append({
                        "wall_id": wall["id"],
                        "position_on_wall": gap_center,
                        "width_px": gap_width_px,
                        "center": center_pt.tolist(),
                        "p1": [int(pt1[0]), int(pt1[1])],
                        "p2": [int(pt2[0]), int(pt2[1])],
                    })

        # Check for gap at end of wall
        if in_gap:
            gap_width_px = (1.0 - gap_start) * wall_len
            if MIN_OPENING_WIDTH_PX < gap_width_px < MAX_OPENING_WIDTH_PX:
                gap_center = (gap_start + 1.0) / 2
                center_pt = p1 + gap_center * wall_vec
                half_w = gap_width_px / 2
                pt1 = center_pt - half_w * wall_dir
                pt2 = center_pt + half_w * wall_dir

                gaps.append({
                    "wall_id": wall["id"],
                    "position_on_wall": gap_center,
                    "width_px": gap_width_px,
                    "center": center_pt.tolist(),
                    "p1": [int(pt1[0]), int(pt1[1])],
                    "p2": [int(pt2[0]), int(pt2[1])],
                })

    return gaps


def detect_openings(img_bin: np.ndarray, walls: list) -> list[dict]:
    """Full opening detection: gaps in walls + arc matching."""
    arcs = _detect_door_arcs(img_bin)
    logger.info("Detected %d potential door arcs", len(arcs))

    gaps = _find_wall_gaps(walls, img_bin)
    logger.info("Detected %d wall gaps", len(gaps))

    openings = []
    for gap in gaps:
        # Check if any arc center is near the gap
        has_arc = False
        for arc in arcs:
            dist = np.sqrt(
                (arc["center"][0] - gap["center"][0]) ** 2 +
                (arc["center"][1] - gap["center"][1]) ** 2
            )
            if dist < gap["width_px"] * 1.5:
                has_arc = True
                break

        opening_type = "door" if has_arc else "window"

        p1 = gap["p1"]
        p2 = gap["p2"]
        # Create a small rectangle around the gap
        wall = next((w for w in walls if w["id"] == gap["wall_id"]), None)
        thickness = wall["thickness_px"] if wall else 10
        normal_offset = max(int(thickness / 2), 5)

        g = wall["geometry"] if wall else [[0, 0], [1, 0]]
        dx = g[1][0] - g[0][0]
        dy = g[1][1] - g[0][1]
        wall_len = max(np.sqrt(dx ** 2 + dy ** 2), 1)
        nx = -dy / wall_len * normal_offset
        ny = dx / wall_len * normal_offset

        geometry = [
            [int(p1[0] + nx), int(p1[1] + ny)],
            [int(p2[0] + nx), int(p2[1] + ny)],
            [int(p2[0] - nx), int(p2[1] - ny)],
            [int(p1[0] - nx), int(p1[1] - ny)],
        ]

        openings.append({
            "id": f"opening-{uuid4().hex[:6]}",
            "wall_id": gap["wall_id"],
            "opening_type": opening_type,
            "geometry": geometry,
            "position_on_wall": round(gap["position_on_wall"], 3),
            "width_px": round(gap["width_px"], 1),
            "confidence": 0.80 if has_arc else 0.70,
            "observation_type": "observed",
        })

    logger.info("Total openings: %d (%d doors, %d windows)",
                len(openings),
                sum(1 for o in openings if o["opening_type"] == "door"),
                sum(1 for o in openings if o["opening_type"] == "window"))

    return openings


def filter_openings_by_scale(
    openings: list[dict],
    px_per_meter: float,
    min_width_m: float = 0.5,
    max_width_m: float = 2.5,
) -> list[dict]:
    """
    Keep only openings whose width in meters is within [min_width_m, max_width_m].
    Removes noise from tiny gaps and implausibly large openings.
    """
    if not px_per_meter or px_per_meter <= 0:
        return openings

    filtered = []
    for o in openings:
        width_px = o.get("width_px", 0)
        width_m = width_px / px_per_meter
        if min_width_m <= width_m <= max_width_m:
            filtered.append(o)
        else:
            logger.debug("Drop opening width_px=%.0f -> %.2fm (outside [%.2f, %.2f])",
                         width_px, width_m, min_width_m, max_width_m)

    logger.info("Filtered openings by scale: %d -> %d (%.1f px/m, %.2f–%.2f m)",
                len(openings), len(filtered), px_per_meter, min_width_m, max_width_m)
    return filtered
