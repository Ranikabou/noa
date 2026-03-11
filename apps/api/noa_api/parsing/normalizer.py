"""Image normalization: deskew, CLAHE, denoise, adaptive binarization.

Also strips circular/arc fixtures (bar counters, display cases, round tables,
hexagonal stools) from the binary image before returning it for wall detection.
Floor plan walls are straight lines; circles and arcs are furniture.
"""
import cv2
import numpy as np
import logging

logger = logging.getLogger("noa.parsing.normalizer")


def detect_rotation(img_gray: np.ndarray) -> float:
    """Detect dominant line angle via Hough transform. Returns degrees to correct."""
    edges = cv2.Canny(img_gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)
    if lines is None or len(lines) < 5:
        return 0.0

    angles = []
    for line in lines:
        theta = line[0][1]
        deg = np.degrees(theta)
        if deg > 135:
            deg -= 180
        elif deg > 45:
            deg -= 90
        angles.append(deg)

    if not angles:
        return 0.0

    median_angle = float(np.median(angles))
    if abs(median_angle) < 0.3:
        return 0.0
    return median_angle


def rotate_image(img: np.ndarray, angle_deg: float) -> np.ndarray:
    """Rotate image by given degrees around center."""
    h, w = img.shape[:2]
    center = (w / 2, h / 2)
    M = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    cos_a = abs(M[0, 0])
    sin_a = abs(M[0, 1])
    new_w = int(h * sin_a + w * cos_a)
    new_h = int(h * cos_a + w * sin_a)
    M[0, 2] += (new_w - w) / 2
    M[1, 2] += (new_h - h) / 2
    return cv2.warpAffine(img, M, (new_w, new_h), borderValue=255)


def erase_circular_fixtures(img_bin: np.ndarray) -> np.ndarray:
    """
    Remove circular and arc-shaped fixtures (bar counters, round tables,
    hexagonal stools, circular displays) from the binary image.

    Walls are straight; circles/arcs are furniture. If these pixels leak
    into Hough wall detection they generate spurious wall segments and
    incorrect room boundary polygons.

    Strategy:
    1. Detect circles (HoughCircles) — fills interior + border with black (erased)
    2. Detect large arc-shaped contours via circularity heuristic and erase them
    3. Erode then dilate (open) to remove isolated thin arc pixels leftover
    """
    cleaned = img_bin.copy()
    h, w = img_bin.shape[:2]

    # ── 1. Hough Circle detection ────────────────────────────────────
    # minRadius / maxRadius scaled to image size (circles from ~1% to 20% of min dim)
    min_dim = min(h, w)
    min_r = max(8, int(min_dim * 0.01))
    max_r = max(60, int(min_dim * 0.20))

    circles = cv2.HoughCircles(
        img_bin,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=int(min_r * 1.5),
        param1=50,
        param2=20,
        minRadius=min_r,
        maxRadius=max_r,
    )
    if circles is not None:
        circles = np.round(circles[0]).astype(int)
        for cx, cy, r in circles:
            # Erase the circle border AND fill interior
            cv2.circle(cleaned, (cx, cy), r + 4, 0, -1)   # filled erase
        logger.debug("Erased %d circles from binary image", len(circles))

    # ── 2. Contour circularity filter ───────────────────────────────
    # Any contour with circularity > 0.6 and reasonable size is likely a
    # circular fixture (round table, hexagonal stool cluster, curved counter arc)
    contours, _ = cv2.findContours(cleaned, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    erase_mask = np.zeros_like(cleaned)

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 100:
            continue
        perimeter = cv2.arcLength(cnt, True)
        if perimeter < 1e-6:
            continue
        circularity = 4 * np.pi * area / (perimeter * perimeter)

        # High circularity AND not so large it would be the whole floor plan
        if circularity > 0.55 and area < (h * w * 0.05):
            cv2.drawContours(erase_mask, [cnt], -1, 255, thickness=cv2.FILLED)

    erased_count = int(np.sum(erase_mask > 0) / max(area, 1)) if contours else 0
    if np.any(erase_mask > 0):
        cleaned[erase_mask > 0] = 0
        logger.debug("Erased circular contours from binary image")

    # ── 3. Morphological open to remove isolated arc pixel debris ───
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel, iterations=1)

    return cleaned


def normalize(image_bytes: bytes) -> dict:
    """
    Full normalization pipeline.

    Returns dict with:
      image_bin      - binarized image with circular fixtures erased (for Hough/rooms)
      image_bin_raw  - binarized image without fixture erasure (for opening detection)
      image_gray     - enhanced grayscale (for OCR)
      image_color    - original color image
      rotation_degrees
      dimensions_px  - (width, height)
      quality_flags
    """
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image")

    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Deskew
    rotation = detect_rotation(img_gray)
    if abs(rotation) > 0.5:
        img_gray = rotate_image(img_gray, -rotation)
        img = rotate_image(img, -rotation)
        logger.info("Rotated image by %.1f degrees", -rotation)

    # CLAHE contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    img_eq = clahe.apply(img_gray)

    # Denoise
    img_dn = cv2.fastNlMeansDenoising(img_eq, h=10, templateWindowSize=7, searchWindowSize=21)

    # Adaptive binarization (NOT global Otsu — floor plans have variable ink density)
    img_bin_raw = cv2.adaptiveThreshold(
        img_dn, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=15,
        C=4,
    )

    # Morphological cleanup: close small gaps in wall lines
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    img_bin_raw = cv2.morphologyEx(img_bin_raw, cv2.MORPH_CLOSE, kernel, iterations=1)

    # Erase circular/arc fixtures from the wall-detection copy.
    # img_bin_raw (unchanged) is used for opening gap detection where arc symbols matter.
    # img_bin (cleaned) is used for Hough wall detection and room segmentation.
    img_bin = erase_circular_fixtures(img_bin_raw)

    # Quality assessment
    quality_flags = []
    white_ratio = np.sum(img_bin == 0) / img_bin.size
    if white_ratio > 0.95:
        quality_flags.append("very_sparse_content")
    if white_ratio < 0.5:
        quality_flags.append("very_dense_content")

    h, w = img_bin.shape[:2]
    logger.info("Normalized: %dx%d, rotation=%.1f°, flags=%s", w, h, rotation, quality_flags)

    return {
        "image_bin": img_bin,           # fixture-erased — for walls + rooms
        "image_bin_raw": img_bin_raw,   # original binary — for opening detection
        "image_gray": img_dn,
        "image_color": img,
        "rotation_degrees": rotation,
        "dimensions_px": (w, h),
        "quality_flags": quality_flags,
    }
