"""
InfraAuto - Image Analysis Engine
====================================
7-category detection with color-based classification.
"""

import math
import cv2
import numpy as np
from core.database import CATEGORIES, get_price
from config import (
    PIXEL_TO_METER, MANHOLE_AREA_THRESHOLD,
    HOUGH_THRESHOLD, HOUGH_MIN_LINE_LENGTH, HOUGH_MAX_LINE_GAP,
    MIN_CONTOUR_AREA,
)

# ── Color ranges in HSV for classification ─────────────────
# Paint uses simple solid colors. These ranges cover typical Paint colors.

COLOR_RANGES = {
    # Black lines → conduit (H:any, S:low, V:low)
    "conduit": {"lower": (0, 0, 0), "upper": (180, 80, 80)},
    # Blue lines → cable
    "cable": {"lower": (90, 80, 50), "upper": (130, 255, 255)},
    # Brown lines → earthwork
    "earthwork": {"lower": (10, 80, 50), "upper": (25, 255, 200)},
    # Red circles → pole
    "pole": {"lower": (0, 120, 80), "upper": (10, 255, 255)},
    "pole2": {"lower": (170, 120, 80), "upper": (180, 255, 255)},  # red wraps
    # Green rectangles → junction
    "junction": {"lower": (35, 80, 50), "upper": (85, 255, 255)},
}


def analyze_image(img: np.ndarray, scale: float = PIXEL_TO_METER, env_type: str = "default") -> dict:
    """
    Full analysis pipeline. Returns:
    {
        "items": [{"category": ..., "name": ..., "quantity": ..., "unit": ..., "unit_price": ..., "total": ...}],
        "grand_total": ...,
        "details": {"conduit_px": ..., ...}
    }
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    results = {}

    # 1. Detect lines by color
    line_categories = _detect_colored_lines(img, hsv, gray)
    for cat, total_px in line_categories.items():
        length_m = total_px * scale
        if length_m > 0:
            results[cat] = {"quantity": round(length_m, 2), "unit": "m"}

    # 2. Detect rectangles → manhole (big) vs handhole (small)
    mh_count, hh_count = _detect_rectangles(gray)
    if mh_count > 0:
        results["manhole"] = {"quantity": mh_count, "unit": "ea"}
    if hh_count > 0:
        results["handhole"] = {"quantity": hh_count, "unit": "ea"}

    # 3. Detect circles → poles (red)
    pole_count = _detect_circles(hsv, gray)
    if pole_count > 0:
        results["pole"] = {"quantity": pole_count, "unit": "ea"}

    # 4. Detect green rectangles → junctions
    junc_count = _detect_colored_rects(hsv, "junction")
    if junc_count > 0:
        results["junction"] = {"quantity": junc_count, "unit": "ea"}

    # 5. Build cost items
    items = []
    grand_total = 0
    for cat_key in ["conduit", "cable", "earthwork", "manhole", "handhole", "pole", "junction"]:
        if cat_key not in results:
            continue
        r = results[cat_key]
        cat_info = CATEGORIES[cat_key]
        unit_price = get_price(cat_key, env_type)
        total = r["quantity"] * unit_price
        grand_total += total
        items.append({
            "category": cat_key,
            "name": cat_info["name"],
            "quantity": r["quantity"],
            "unit": r["unit"],
            "unit_price": unit_price,
            "total": round(total),
        })

    return {
        "items": items,
        "grand_total": round(grand_total),
        "image_shape": img.shape,
    }


def analyze_image_with_basis(img: np.ndarray, scale: float = PIXEL_TO_METER, env_type: str = "default") -> dict:
    """
    Same as analyze_image but with detailed basis text for each item.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    items = []
    grand_total = 0

    # 1. Lines by color
    for cat_key in ["conduit", "cable", "earthwork"]:
        if cat_key in ["cable", "earthwork"]:
            r = COLOR_RANGES[cat_key]
            mask = cv2.inRange(hsv, np.array(r["lower"]), np.array(r["upper"]))
            edges = cv2.Canny(mask, 50, 150)
        else:
            _, black_mask = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)
            for c in ["cable", "earthwork", "pole", "pole2", "junction"]:
                cr = COLOR_RANGES[c]
                cm = cv2.inRange(hsv, np.array(cr["lower"]), np.array(cr["upper"]))
                black_mask = cv2.bitwise_and(black_mask, cv2.bitwise_not(cm))
            edges = cv2.Canny(black_mask, 50, 150)

        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=HOUGH_THRESHOLD, minLineLength=HOUGH_MIN_LINE_LENGTH, maxLineGap=HOUGH_MAX_LINE_GAP)
        if lines is None or len(lines) == 0:
            continue

        seg_lengths = []
        total_px = 0.0
        for line in lines:
            x1, y1, x2, y2 = line[0]
            px = math.hypot(x2 - x1, y2 - y1)
            total_px += px
            seg_lengths.append(round(px * scale, 1))

        length_m = round(total_px * scale, 2)
        if length_m <= 0:
            continue

        cat_info = CATEGORIES[cat_key]
        unit_price = get_price(cat_key, env_type)
        total = round(length_m * unit_price)
        grand_total += total

        # Build basis
        n = len(seg_lengths)
        segs = ", ".join(f"{s}m" for s in seg_lengths[:5])
        if n > 5:
            segs += f" 외 {n - 5}개"
        color_name = {"conduit": "검정", "cable": "파랑", "earthwork": "갈색"}[cat_key]
        basis = (
            f"{color_name}색 선 {n}개 감지 (Hough 변환)\n"
            f"구간: {segs}\n"
            f"총 {round(total_px)}px x {scale}m/px = {length_m}m\n"
            f"{length_m}m x {unit_price:,}원/m = {total:,}원"
        )

        items.append({
            "category": cat_key, "name": cat_info["name"],
            "quantity": length_m, "unit": "m",
            "unit_price": unit_price, "total": total, "basis": basis,
        })

    # 2. Rectangles
    _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    mh_rects, hh_rects = [], []
    MANHOLE_AREA_THRESHOLD = 800

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 100:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        if len(approx) == 4:
            x, y, w, h = cv2.boundingRect(approx)
            aspect = max(w, h) / (min(w, h) + 1e-5)
            if aspect < 3.0:
                if area >= MANHOLE_AREA_THRESHOLD:
                    mh_rects.append(f"{w}x{h}px (면적:{int(area)})")
                else:
                    hh_rects.append(f"{w}x{h}px (면적:{int(area)})")

    for cat_key, rects in [("manhole", mh_rects), ("handhole", hh_rects)]:
        if not rects:
            continue
        cat_info = CATEGORIES[cat_key]
        count = len(rects)
        unit_price = get_price(cat_key, env_type)
        total = round(count * unit_price)
        grand_total += total

        size_label = "큰" if cat_key == "manhole" else "작은"
        threshold_note = f"면적 {'≥' if cat_key == 'manhole' else '<'}{MANHOLE_AREA_THRESHOLD}px²"
        rects_str = ", ".join(rects[:4])
        if count > 4:
            rects_str += f" 외 {count - 4}개"
        basis = (
            f"{size_label} 사각형 {count}개 감지 ({threshold_note})\n"
            f"크기: {rects_str}\n"
            f"{count}개 x {unit_price:,}원 = {total:,}원"
        )

        items.append({
            "category": cat_key, "name": cat_info["name"],
            "quantity": count, "unit": "ea",
            "unit_price": unit_price, "total": total, "basis": basis,
        })

    # 3. Red circles → poles
    mask1 = cv2.inRange(hsv, np.array(COLOR_RANGES["pole"]["lower"]), np.array(COLOR_RANGES["pole"]["upper"]))
    mask2 = cv2.inRange(hsv, np.array(COLOR_RANGES["pole2"]["lower"]), np.array(COLOR_RANGES["pole2"]["upper"]))
    red_mask = cv2.bitwise_or(mask1, mask2)

    circles = cv2.HoughCircles(red_mask, cv2.HOUGH_GRADIENT, dp=1.2, minDist=30,
                                param1=50, param2=20, minRadius=5, maxRadius=50)
    pole_count = 0
    pole_details = []
    if circles is not None:
        pole_count = len(circles[0])
        for c in circles[0][:5]:
            pole_details.append(f"({int(c[0])},{int(c[1])}) r={int(c[2])}")
    else:
        cnts, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            if cv2.contourArea(c) > 50:
                pole_count += 1

    if pole_count > 0:
        unit_price = get_price("pole", env_type)
        total = round(pole_count * unit_price)
        grand_total += total
        det = ", ".join(pole_details) if pole_details else f"{pole_count}개 윤곽선"
        basis = (
            f"빨강색 원 {pole_count}개 감지 (Hough 원 검출)\n"
            f"위치: {det}\n"
            f"{pole_count}개 x {unit_price:,}원 = {total:,}원"
        )
        items.append({
            "category": "pole", "name": CATEGORIES["pole"]["name"],
            "quantity": pole_count, "unit": "ea",
            "unit_price": unit_price, "total": total, "basis": basis,
        })

    # 4. Green rects → junctions
    jr = COLOR_RANGES["junction"]
    jmask = cv2.inRange(hsv, np.array(jr["lower"]), np.array(jr["upper"]))
    jcnts, _ = cv2.findContours(jmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    junc_count = 0
    for cnt in jcnts:
        if cv2.contourArea(cnt) < 100:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        if len(approx) == 4:
            junc_count += 1

    if junc_count > 0:
        unit_price = get_price("junction", env_type)
        total = round(junc_count * unit_price)
        grand_total += total
        basis = (
            f"녹색 사각형 {junc_count}개 감지 (HSV 색상 필터)\n"
            f"{junc_count}개 x {unit_price:,}원 = {total:,}원"
        )
        items.append({
            "category": "junction", "name": CATEGORIES["junction"]["name"],
            "quantity": junc_count, "unit": "ea",
            "unit_price": unit_price, "total": total, "basis": basis,
        })

    return {
        "items": items,
        "grand_total": round(grand_total),
        "image_shape": img.shape,
    }


def _detect_colored_lines(img, hsv, gray) -> dict:
    """Detect lines separated by color."""
    results = {"conduit": 0.0, "cable": 0.0, "earthwork": 0.0}

    # For each color category, create a mask and detect lines
    for cat in ["cable", "earthwork"]:
        r = COLOR_RANGES[cat]
        mask = cv2.inRange(hsv, np.array(r["lower"]), np.array(r["upper"]))
        edges = cv2.Canny(mask, 50, 150)
        results[cat] = _hough_total_length(edges)

    # Black (conduit) = use grayscale thresholding, subtract colored pixels
    _, black_mask = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)

    # Remove colored regions from black mask
    for cat in ["cable", "earthwork", "pole", "pole2", "junction"]:
        r = COLOR_RANGES[cat]
        color_mask = cv2.inRange(hsv, np.array(r["lower"]), np.array(r["upper"]))
        black_mask = cv2.bitwise_and(black_mask, cv2.bitwise_not(color_mask))

    edges = cv2.Canny(black_mask, 50, 150)
    results["conduit"] = _hough_total_length(edges)

    return results


def _hough_total_length(edges) -> float:
    """Run HoughLinesP and return total pixel length."""
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=HOUGH_THRESHOLD, minLineLength=HOUGH_MIN_LINE_LENGTH, maxLineGap=HOUGH_MAX_LINE_GAP)
    if lines is None:
        return 0.0
    total = 0.0
    for line in lines:
        x1, y1, x2, y2 = line[0]
        total += math.hypot(x2 - x1, y2 - y1)
    return total


def _detect_rectangles(gray) -> tuple[int, int]:
    """Detect black rectangles. Big = manhole, small = handhole."""
    _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    manholes = 0
    handholes = 0
    

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 100:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        if len(approx) == 4:
            x, y, w, h = cv2.boundingRect(approx)
            aspect = max(w, h) / (min(w, h) + 1e-5)
            if aspect < 3.0:
                if area >= MANHOLE_AREA_THRESHOLD:
                    manholes += 1
                else:
                    handholes += 1

    return manholes, handholes


def _detect_circles(hsv, gray) -> int:
    """Detect red circles as poles."""
    # Red mask (two ranges because red wraps in HSV)
    mask1 = cv2.inRange(hsv, np.array(COLOR_RANGES["pole"]["lower"]), np.array(COLOR_RANGES["pole"]["upper"]))
    mask2 = cv2.inRange(hsv, np.array(COLOR_RANGES["pole2"]["lower"]), np.array(COLOR_RANGES["pole2"]["upper"]))
    red_mask = cv2.bitwise_or(mask1, mask2)

    # Find circles in red areas
    circles = cv2.HoughCircles(
        red_mask, cv2.HOUGH_GRADIENT, dp=1.2, minDist=30,
        param1=50, param2=20, minRadius=5, maxRadius=50,
    )
    if circles is not None:
        return len(circles[0])

    # Fallback: count red contours
    contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return sum(1 for c in contours if cv2.contourArea(c) > 50)


def _detect_colored_rects(hsv, category: str) -> int:
    """Detect colored rectangles for a given category."""
    r = COLOR_RANGES.get(category)
    if not r:
        return 0
    mask = cv2.inRange(hsv, np.array(r["lower"]), np.array(r["upper"]))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    count = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 100:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        if len(approx) == 4:
            count += 1
    return count
