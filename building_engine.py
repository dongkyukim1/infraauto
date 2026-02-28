"""
InfraAuto - Building/Interior Analysis Engine
================================================
건축/인테리어 도면에서 자재를 인식하고 수량/사이즈를 산출합니다.

색상 매핑:
  하늘색 rect (작은) → 창문(소)
  파랑 rect (큰)    → 창문(대)
  갈색 rect         → 문
  연두색 area       → 장판/바닥
  주황 line         → 벽체
  보라 area         → 천장
  청록 area         → 타일
  분홍 area         → 도장
"""

import math
import cv2
import numpy as np
from database import CATEGORIES, get_price

PIXEL_TO_METER = 0.1

# ── HSV 색상 범위 ─────────────────────────────────────────

BUILDING_COLORS = {
    # 하늘색 (창문) - light blue
    "window": {"lower": (90, 50, 150), "upper": (115, 255, 255)},
    # 진파랑 (창문 대형) - deep blue
    "window_deep": {"lower": (100, 120, 50), "upper": (130, 255, 255)},
    # 갈색 (문) - brown
    "door": {"lower": (10, 80, 50), "upper": (25, 255, 200)},
    # 연두색 (장판/바닥) - light green
    "flooring": {"lower": (35, 50, 100), "upper": (75, 255, 255)},
    # 주황 (벽체) - orange
    "wall": {"lower": (5, 100, 100), "upper": (20, 255, 255)},
    # 보라 (천장) - purple
    "ceiling": {"lower": (125, 50, 50), "upper": (160, 255, 255)},
    # 청록 (타일) - teal/cyan
    "tile": {"lower": (75, 80, 80), "upper": (95, 255, 255)},
    # 분홍 (도장) - pink
    "paint": {"lower": (160, 30, 150), "upper": (180, 150, 255)},
}

# 창문 소/대 구분 면적 임계값 (px²)
WINDOW_SIZE_THRESHOLD = 2000


def analyze_building_image(img: np.ndarray, scale: float = PIXEL_TO_METER, env_type: str = "default") -> dict:
    """
    건축 도면 이미지 분석 파이프라인.
    Returns:
        {
            "items": [{"category", "name", "quantity", "unit", "unit_price", "total", "basis", "details"}],
            "grand_total": int,
            "image_shape": tuple
        }
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    items = []
    grand_total = 0

    # 1. 창문 감지 (하늘색 + 진파랑 사각형)
    win_items, win_total = _detect_windows(hsv, scale, env_type)
    items.extend(win_items)
    grand_total += win_total

    # 2. 문 감지 (갈색 사각형)
    door_items, door_total = _detect_doors(hsv, scale, env_type)
    items.extend(door_items)
    grand_total += door_total

    # 3. 장판/바닥 감지 (연두색 영역)
    floor_items, floor_total = _detect_area_material(hsv, "flooring", scale, env_type)
    items.extend(floor_items)
    grand_total += floor_total

    # 4. 벽체 감지 (주황 선)
    wall_items, wall_total = _detect_wall_lines(hsv, scale, env_type)
    items.extend(wall_items)
    grand_total += wall_total

    # 5. 천장 감지 (보라 영역)
    ceil_items, ceil_total = _detect_area_material(hsv, "ceiling", scale, env_type)
    items.extend(ceil_items)
    grand_total += ceil_total

    # 6. 타일 감지 (청록 영역)
    tile_items, tile_total = _detect_area_material(hsv, "tile", scale, env_type)
    items.extend(tile_items)
    grand_total += tile_total

    # 7. 도장 감지 (분홍 영역)
    paint_items, paint_total = _detect_area_material(hsv, "paint", scale, env_type)
    items.extend(paint_items)
    grand_total += paint_total

    return {
        "items": items,
        "grand_total": round(grand_total),
        "image_shape": img.shape,
    }


def analyze_building_canvas(canvas_items: list, scale: float = PIXEL_TO_METER, env_type: str = "default") -> dict:
    """
    캔버스에서 직접 그린 건축 아이템 분석.
    canvas_items: [(shape, key, color, data), ...]
    """
    qty = {}
    for shape, key, color, data in canvas_items:
        if key not in qty:
            qty[key] = {"count": 0, "length_px": 0.0, "area_px": 0.0, "lines": [], "details": []}

        if shape == "line":
            x1, y1, x2, y2 = data
            px = math.hypot(x2 - x1, y2 - y1)
            qty[key]["length_px"] += px
            qty[key]["lines"].append(round(px, 1))
        elif shape == "rect":
            x, y, w, h = data
            area = w * h
            qty[key]["area_px"] += area
            qty[key]["count"] += 1
            size_m2 = round(area * scale * scale, 2)
            w_m = round(w * scale, 2)
            h_m = round(h * scale, 2)
            qty[key]["details"].append(f"{w_m}x{h_m}m ({size_m2}m²)")
        elif shape == "area":
            x, y, w, h = data
            area = w * h
            qty[key]["area_px"] += area
            qty[key]["count"] += 1
        elif shape == "circle":
            qty[key]["count"] += 1

    items = []
    grand_total = 0

    for key, q in qty.items():
        if key not in CATEGORIES:
            continue
        cat = CATEGORIES[key]
        unit_price = get_price(key, env_type)

        if cat["unit"] == "m":
            amount = round(q["length_px"] * scale, 1)
            if amount <= 0:
                continue
            n = len(q["lines"])
            segs = ", ".join(f"{round(l * scale, 1)}m" for l in q["lines"][:5])
            if n > 5:
                segs += f" 외 {n - 5}개"
            basis = (
                f"선 {n}개 ({segs})\n"
                f"총 {amount}m x {unit_price:,}원/m = {round(amount * unit_price):,}원"
            )
            total = round(amount * unit_price)
        elif cat["unit"] == "m²":
            amount = round(q["area_px"] * scale * scale, 1)
            if amount <= 0:
                continue
            basis = (
                f"영역 {q['count']}개, 총 면적 {amount}m²\n"
                f"{amount}m² x {unit_price:,}원/m² = {round(amount * unit_price):,}원"
            )
            total = round(amount * unit_price)
        else:  # ea
            amount = q["count"]
            if amount <= 0:
                continue
            det = ", ".join(q["details"][:5]) if q["details"] else f"{amount}개"
            basis = (
                f"{cat['name']} {amount}개\n"
                f"규격: {det}\n"
                f"{amount}개 x {unit_price:,}원 = {round(amount * unit_price):,}원"
            )
            total = round(amount * unit_price)

        grand_total += total
        items.append({
            "category": key,
            "name": cat["name"],
            "quantity": amount,
            "unit": cat["unit"],
            "unit_price": unit_price,
            "total": total,
            "basis": basis,
        })

    return {
        "items": items,
        "grand_total": round(grand_total),
    }


# ── 개별 감지 함수들 ─────────────────────────────────────────


def _detect_windows(hsv, scale, env_type):
    """하늘색/파랑 사각형에서 창문 감지. 크기로 소/대 구분."""
    items = []
    total_cost = 0

    # 두 색상 범위 합침
    mask1 = cv2.inRange(hsv, np.array(BUILDING_COLORS["window"]["lower"]),
                        np.array(BUILDING_COLORS["window"]["upper"]))
    mask2 = cv2.inRange(hsv, np.array(BUILDING_COLORS["window_deep"]["lower"]),
                        np.array(BUILDING_COLORS["window_deep"]["upper"]))
    mask = cv2.bitwise_or(mask1, mask2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    small_windows = []
    large_windows = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 100:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        if len(approx) >= 4:
            x, y, w, h = cv2.boundingRect(approx)
            w_m = round(w * scale, 2)
            h_m = round(h * scale, 2)
            detail = f"{w_m}x{h_m}m"
            if area >= WINDOW_SIZE_THRESHOLD:
                large_windows.append(detail)
            else:
                small_windows.append(detail)

    for cat_key, windows in [("window_s", small_windows), ("window_l", large_windows)]:
        if not windows:
            continue
        count = len(windows)
        cat = CATEGORIES[cat_key]
        unit_price = get_price(cat_key, env_type)
        total = round(count * unit_price)
        total_cost += total

        det = ", ".join(windows[:5])
        if count > 5:
            det += f" 외 {count - 5}개"
        size_label = "소형" if cat_key == "window_s" else "대형"
        basis = (
            f"{size_label} 창문 {count}개 감지 (면적 {'<' if cat_key == 'window_s' else '≥'}{WINDOW_SIZE_THRESHOLD}px²)\n"
            f"규격: {det}\n"
            f"{count}개 x {unit_price:,}원 = {total:,}원"
        )
        items.append({
            "category": cat_key, "name": cat["name"],
            "quantity": count, "unit": "ea",
            "unit_price": unit_price, "total": total, "basis": basis,
        })

    return items, total_cost


def _detect_doors(hsv, scale, env_type):
    """갈색 사각형에서 문 감지."""
    r = BUILDING_COLORS["door"]
    mask = cv2.inRange(hsv, np.array(r["lower"]), np.array(r["upper"]))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    doors = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 200:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        if len(approx) >= 4:
            x, y, w, h = cv2.boundingRect(approx)
            w_m = round(w * scale, 2)
            h_m = round(h * scale, 2)
            doors.append(f"{w_m}x{h_m}m")

    if not doors:
        return [], 0

    count = len(doors)
    cat = CATEGORIES["door"]
    unit_price = get_price("door", env_type)
    total = round(count * unit_price)

    det = ", ".join(doors[:5])
    if count > 5:
        det += f" 외 {count - 5}개"
    basis = (
        f"문 {count}개 감지 (갈색 사각형)\n"
        f"규격: {det}\n"
        f"{count}개 x {unit_price:,}원 = {total:,}원"
    )

    return [{
        "category": "door", "name": cat["name"],
        "quantity": count, "unit": "ea",
        "unit_price": unit_price, "total": total, "basis": basis,
    }], total


def _detect_area_material(hsv, category, scale, env_type):
    """색상 영역 면적으로 자재량 산출 (장판, 천장, 타일, 도장)."""
    color_key = category  # flooring, ceiling, tile, paint
    r = BUILDING_COLORS.get(color_key)
    if not r:
        return [], 0

    mask = cv2.inRange(hsv, np.array(r["lower"]), np.array(r["upper"]))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    total_area_px = 0
    regions = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 200:
            continue
        total_area_px += area
        x, y, w, h = cv2.boundingRect(cnt)
        area_m2 = round(area * scale * scale, 2)
        regions.append(f"{round(w * scale, 1)}x{round(h * scale, 1)}m ({area_m2}m²)")

    if total_area_px == 0:
        return [], 0

    area_m2 = round(total_area_px * scale * scale, 1)
    cat = CATEGORIES[category]
    unit_price = get_price(category, env_type)
    total = round(area_m2 * unit_price)

    det = ", ".join(regions[:4])
    if len(regions) > 4:
        det += f" 외 {len(regions) - 4}개"
    color_names = {
        "flooring": "연두색", "ceiling": "보라색", "tile": "청록색", "paint": "분홍색"
    }
    basis = (
        f"{color_names.get(category, '')} 영역 {len(regions)}개 감지\n"
        f"구역: {det}\n"
        f"총 면적 {area_m2}m² x {unit_price:,}원/m² = {total:,}원"
    )

    return [{
        "category": category, "name": cat["name"],
        "quantity": area_m2, "unit": "m²",
        "unit_price": unit_price, "total": total, "basis": basis,
    }], total


def _detect_wall_lines(hsv, scale, env_type):
    """주황색 선에서 벽체 감지."""
    r = BUILDING_COLORS["wall"]
    mask = cv2.inRange(hsv, np.array(r["lower"]), np.array(r["upper"]))
    edges = cv2.Canny(mask, 50, 150)

    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=30, minLineLength=20, maxLineGap=10)
    if lines is None or len(lines) == 0:
        return [], 0

    seg_lengths = []
    total_px = 0.0
    for line in lines:
        x1, y1, x2, y2 = line[0]
        px = math.hypot(x2 - x1, y2 - y1)
        total_px += px
        seg_lengths.append(round(px * scale, 1))

    length_m = round(total_px * scale, 2)
    if length_m <= 0:
        return [], 0

    cat = CATEGORIES["wall"]
    unit_price = get_price("wall", env_type)
    total = round(length_m * unit_price)

    n = len(seg_lengths)
    segs = ", ".join(f"{s}m" for s in seg_lengths[:5])
    if n > 5:
        segs += f" 외 {n - 5}개"
    basis = (
        f"주황색 벽체 선 {n}개 감지\n"
        f"구간: {segs}\n"
        f"총 {length_m}m x {unit_price:,}원/m = {total:,}원"
    )

    return [{
        "category": "wall", "name": cat["name"],
        "quantity": length_m, "unit": "m",
        "unit_price": unit_price, "total": total, "basis": basis,
    }], total
