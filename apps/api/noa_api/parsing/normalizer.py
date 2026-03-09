"""Image normalization: deskew, CLAHE, denoise, adaptive binarization."""
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
        # Normalize to [-45, 45] range relative to horizontal/vertical
        if deg > 135:
            deg -= 180
        elif deg > 45:
            deg -= 90
        angles.append(deg)

    if not angles:
        return 0.0

    # Use median to be robust against outliers
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


def normalize(image_bytes: bytes) -> dict:
    """
    Full normalization pipeline.
    Returns dict with: image (binarized), gray (enhanced grayscale),
    rotation_degrees, dimensions_px, quality_flags
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
    img_bin = cv2.adaptiveThreshold(
        img_dn, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=15,
        C=4,
    )

    # Morphological cleanup: close small gaps in wall lines
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    img_bin = cv2.morphologyEx(img_bin, cv2.MORPH_CLOSE, kernel, iterations=1)

    # Quality assessment
    quality_flags = []
    white_ratio = np.sum(img_bin == 0) / img_bin.size
    if white_ratio > 0.95:
        quality_flags.append("very_sparse_content")
    if white_ratio < 0.5:
        quality_flags.append("very_dense_content")

    h, w = img_bin.shape[:2]
    return {
        "image_bin": img_bin,
        "image_gray": img_dn,
        "image_color": img,
        "rotation_degrees": rotation,
        "dimensions_px": (w, h),
        "quality_flags": quality_flags,
    }
