"""
InfraAuto - Building/Interior Analysis Engine
================================================
건축/인테리어 도면에서 자재를 인식하고 수량/사이즈를 산출합니다.

색상 매핑:
  하늘색 rect (작은) → 창문(소)
  파랑 rect (큰)    → 창문(대)
  갈색 rect         → 문
  연두색 area       → 장판/바닥
  주황 line         → 벽체 (실선=내력벽, 점선=경량벽)
  보라 area         → 천장
  청록 area         → 타일
  분홍 area         → 도장

고급 감지:
  창문 내부 평행선 → 단창/이중창/삼중창 분류
  문 주변 호(arc) → 여닫이/미닫이 분류, 스윙 방향
  벽체 선분 on/off → 실선(내력벽)/점선(경량벽) 구분
  테두리 버블+그리드선 → 구조 격자 메타데이터
"""

import math
import cv2
import numpy as np
from core.database import CATEGORIES, get_price
from config import (
    PIXEL_TO_METER, WINDOW_SIZE_THRESHOLD, MIN_CONTOUR_AREA,
    LINE_SAMPLE_POINTS, LINE_SOLID_THRESHOLD,
    DOOR_SEARCH_EXPAND, DOOR_ARC_MIN_RADIUS, DOOR_ARC_MAX_RADIUS,
    WINDOW_PANE_MIN_LINES, WINDOW_PANE_LINE_THRESHOLD,
    GRID_BORDER_RATIO, GRID_BUBBLE_MIN_RADIUS, GRID_BUBBLE_MAX_RADIUS,
)

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

# WINDOW_SIZE_THRESHOLD는 config.py에서 import


def analyze_building_image(img: np.ndarray, scale: float = PIXEL_TO_METER,
                           env_type: str = "default",
                           use_ocr_scale: bool = False) -> dict:
    """
    건축 도면 이미지 분석 파이프라인.

    Args:
        img: BGR 이미지
        scale: pixel_to_meter 비율
        env_type: 환경 타입 (default, urban, suburban, mountain)
        use_ocr_scale: True이면 OCR 치수 텍스트로 스케일 자동 보정 시도

    Returns:
        {
            "items": [{"category", "name", "quantity", "unit", "unit_price", "total", "basis", "details"}],
            "grand_total": int,
            "image_shape": tuple,
            "grid_info": dict | None,
            "ocr_scale": float | None,
        }
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # OCR 스케일 보정 (옵션)
    ocr_scale = None
    if use_ocr_scale:
        try:
            from analysis.ocr_engine import detect_dimension_text
            dim_result = detect_dimension_text(img)
            if dim_result and dim_result.get("pixel_to_meter"):
                ocr_scale = dim_result["pixel_to_meter"]
                scale = ocr_scale
        except Exception:
            pass

    items = []
    grand_total = 0

    # 1. 창문 감지 (하늘색 + 진파랑 사각형, 유형별 분류)
    win_items, win_total = _detect_windows(hsv, gray, scale, env_type)
    items.extend(win_items)
    grand_total += win_total

    # 2. 문 감지 (갈색 사각형, 스윙 방향)
    door_items, door_total = _detect_doors(hsv, gray, scale, env_type)
    items.extend(door_items)
    grand_total += door_total

    # 3. 장판/바닥 감지 (연두색 영역)
    floor_items, floor_total = _detect_area_material(hsv, "flooring", scale, env_type)
    items.extend(floor_items)
    grand_total += floor_total

    # 4. 벽체 감지 (주황 선, 실선/점선 구분)
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

    # 8. 그리드 시스템 감지 (메타데이터)
    grid_info = _detect_grid_system(gray)

    return {
        "items": items,
        "grand_total": round(grand_total),
        "image_shape": img.shape,
        "grid_info": grid_info,
        "ocr_scale": ocr_scale,
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


# ── 유틸리티 함수 ──────────────────────────────────────────


def _classify_line_type(mask: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> str:
    """
    선분 경로를 따라 N개 포인트를 샘플링하여 실선/점선을 판별한다.

    Args:
        mask: 이진 마스크 이미지 (벽체 색상 영역)
        x1, y1, x2, y2: 선분 양 끝점 좌표

    Returns:
        "solid" (실선, 내력벽) 또는 "dotted" (점선, 경량벽)
    """
    h, w = mask.shape[:2]
    n_points = LINE_SAMPLE_POINTS
    on_count = 0

    for i in range(n_points):
        t = i / max(n_points - 1, 1)
        px = int(x1 + t * (x2 - x1))
        py = int(y1 + t * (y2 - y1))
        # 경계 클램핑
        px = max(0, min(px, w - 1))
        py = max(0, min(py, h - 1))
        if mask[py, px] > 0:
            on_count += 1

    ratio = on_count / n_points
    return "solid" if ratio >= LINE_SOLID_THRESHOLD else "dotted"


def _classify_window_pane(gray_roi: np.ndarray) -> str:
    """
    창문 ROI 내부의 평행선 개수로 단창/이중창/삼중창을 분류한다.

    Args:
        gray_roi: 그레이스케일 창문 영역 이미지

    Returns:
        "window_single", "window_double", 또는 "window_triple"
    """
    if gray_roi.size == 0 or gray_roi.shape[0] < 5 or gray_roi.shape[1] < 5:
        return "window_single"

    edges = cv2.Canny(gray_roi, 50, 150)
    h, w = gray_roi.shape[:2]

    # 짧은 방향(폭 또는 높이 중 짧은 쪽)의 평행선을 감지
    min_len = max(min(h, w) // 3, 5)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=15,
                            minLineLength=min_len, maxLineGap=5)

    if lines is None:
        return "window_single"

    # 수평/수직 선분 중 지배적 방향 선정
    horiz_lines = []
    vert_lines = []
    for line in lines:
        lx1, ly1, lx2, ly2 = line[0]
        angle = abs(math.atan2(ly2 - ly1, lx2 - lx1))
        if angle < 0.3:  # ~17도 이내 → 수평
            horiz_lines.append((ly1 + ly2) / 2)
        elif angle > 1.27:  # ~73도 이상 → 수직
            vert_lines.append((lx1 + lx2) / 2)

    # 더 많은 방향의 평행선 사용
    positions = horiz_lines if len(horiz_lines) >= len(vert_lines) else vert_lines
    if len(positions) < 2:
        return "window_single"

    # 위치 클러스터링: WINDOW_PANE_LINE_THRESHOLD 이상 떨어진 선끼리만 별개 유리판 경계
    positions.sort()
    distinct = [positions[0]]
    for pos in positions[1:]:
        if pos - distinct[-1] >= WINDOW_PANE_LINE_THRESHOLD:
            distinct.append(pos)

    pane_boundaries = len(distinct)
    if pane_boundaries >= 3:
        return "window_triple"
    elif pane_boundaries >= WINDOW_PANE_MIN_LINES:
        return "window_double"
    return "window_single"


def _detect_door_swing(gray: np.ndarray, x: int, y: int, w: int, h: int) -> dict:
    """
    문 bounding rect 주변에서 호(arc)를 탐색하여 여닫이/미닫이를 판별한다.

    Args:
        gray: 전체 그레이스케일 이미지
        x, y, w, h: 문의 bounding rect

    Returns:
        {"type": "swing"|"sliding", "direction": "left"|"right"|None}
    """
    img_h, img_w = gray.shape[:2]

    # 확장 영역 (문 주변 1.5배)
    expand_w = int(w * (DOOR_SEARCH_EXPAND - 1) / 2)
    expand_h = int(h * (DOOR_SEARCH_EXPAND - 1) / 2)
    rx1 = max(0, x - expand_w)
    ry1 = max(0, y - expand_h)
    rx2 = min(img_w, x + w + expand_w)
    ry2 = min(img_h, y + h + expand_h)

    roi = gray[ry1:ry2, rx1:rx2]
    if roi.size == 0:
        return {"type": "sliding", "direction": None}

    # 블러 후 원 검출
    blurred = cv2.GaussianBlur(roi, (9, 9), 2)
    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT,
        dp=1.2, minDist=max(w, h) // 2,
        param1=100, param2=30,
        minRadius=DOOR_ARC_MIN_RADIUS,
        maxRadius=DOOR_ARC_MAX_RADIUS,
    )

    if circles is None:
        return {"type": "sliding", "direction": None}

    # 부분 호 검증: 원 둘레 중 실제 엣지가 존재하는 비율 확인
    edges_roi = cv2.Canny(roi, 50, 150)
    for circle in circles[0]:
        cx, cy, r = circle
        # 원 둘레 위 샘플 포인트
        arc_points = 0
        total_samples = 36
        for i in range(total_samples):
            angle = 2 * math.pi * i / total_samples
            px = int(cx + r * math.cos(angle))
            py = int(cy + r * math.sin(angle))
            if 0 <= px < edges_roi.shape[1] and 0 <= py < edges_roi.shape[0]:
                if edges_roi[py, px] > 0:
                    arc_points += 1

        arc_ratio = arc_points / total_samples
        # 부분 호: 25%~75% 정도가 존재해야 함 (완전한 원은 문 스윙이 아닐 수 있음)
        if 0.15 <= arc_ratio <= 0.8:
            # 스윙 방향: 호 중심이 문 중심의 왼쪽이면 좌개, 오른쪽이면 우개
            door_center_x = (x - rx1) + w / 2
            direction = "left" if cx < door_center_x else "right"
            return {"type": "swing", "direction": direction}

    return {"type": "sliding", "direction": None}


# ── 개별 감지 함수들 ─────────────────────────────────────────


def _detect_windows(hsv, gray, scale, env_type):
    """
    하늘색/파랑 사각형에서 창문 감지.
    크기로 소/대 구분 + 내부 평행선으로 단창/이중창/삼중창 분류.
    """
    items = []
    total_cost = 0

    # 두 색상 범위 합침
    mask1 = cv2.inRange(hsv, np.array(BUILDING_COLORS["window"]["lower"]),
                        np.array(BUILDING_COLORS["window"]["upper"]))
    mask2 = cv2.inRange(hsv, np.array(BUILDING_COLORS["window_deep"]["lower"]),
                        np.array(BUILDING_COLORS["window_deep"]["upper"]))
    mask = cv2.bitwise_or(mask1, mask2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 크기별 분류 (기존 호환)
    small_windows = []
    large_windows = []
    # 유형별 분류 (신규)
    pane_counts = {"window_single": [], "window_double": [], "window_triple": []}

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

            # 크기 분류 (기존 호환)
            if area >= WINDOW_SIZE_THRESHOLD:
                large_windows.append(detail)
            else:
                small_windows.append(detail)

            # 유형 분류 (평행선 기반)
            roi = gray[y:y+h, x:x+w]
            pane_type = _classify_window_pane(roi)
            pane_counts[pane_type].append(detail)

    # 크기별 출력 (기존 호환 - window_s, window_l)
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

    # 유형별 출력 (신규 - window_single, window_double, window_triple)
    for pane_key, windows in pane_counts.items():
        if not windows:
            continue
        count = len(windows)
        cat = CATEGORIES[pane_key]
        unit_price = get_price(pane_key, env_type)
        total = round(count * unit_price)
        total_cost += total

        det = ", ".join(windows[:5])
        if count > 5:
            det += f" 외 {count - 5}개"
        type_label = {"window_single": "단창", "window_double": "이중창", "window_triple": "삼중창"}[pane_key]
        basis = (
            f"{type_label} {count}개 감지 (내부 평행선 분석)\n"
            f"규격: {det}\n"
            f"{count}개 x {unit_price:,}원 = {total:,}원"
        )
        items.append({
            "category": pane_key, "name": cat["name"],
            "quantity": count, "unit": "ea",
            "unit_price": unit_price, "total": total, "basis": basis,
        })

    return items, total_cost


def _detect_doors(hsv, gray, scale, env_type):
    """갈색 사각형에서 문 감지. 주변 호 탐색으로 여닫이/미닫이 분류."""
    r = BUILDING_COLORS["door"]
    mask = cv2.inRange(hsv, np.array(r["lower"]), np.array(r["upper"]))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    swing_doors = []  # 여닫이
    sliding_doors = []  # 미닫이
    swing_left = 0
    swing_right = 0

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
            detail = f"{w_m}x{h_m}m"

            # 스윙 방향 감지
            swing_info = _detect_door_swing(gray, x, y, w, h)
            if swing_info["type"] == "swing":
                swing_doors.append(detail)
                if swing_info["direction"] == "left":
                    swing_left += 1
                else:
                    swing_right += 1
            else:
                sliding_doors.append(detail)

    all_doors = swing_doors + sliding_doors
    if not all_doors:
        return [], 0

    count = len(all_doors)
    cat = CATEGORIES["door"]
    unit_price = get_price("door", env_type)
    total = round(count * unit_price)

    det = ", ".join(all_doors[:5])
    if count > 5:
        det += f" 외 {count - 5}개"

    # 상세 분류 표기
    type_parts = []
    if swing_doors:
        dir_detail = []
        if swing_left > 0:
            dir_detail.append(f"좌개 {swing_left}개")
        if swing_right > 0:
            dir_detail.append(f"우개 {swing_right}개")
        type_parts.append(f"여닫이({', '.join(dir_detail)})")
    if sliding_doors:
        type_parts.append(f"미닫이 {len(sliding_doors)}개")
    type_desc = ", ".join(type_parts) if type_parts else f"{count}개"

    basis = (
        f"문 {count}개 감지 (갈색 사각형)\n"
        f"유형: {type_desc}\n"
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
    """
    주황색 선에서 벽체 감지.
    실선(내력벽)과 점선(경량벽)을 구분하여 별도 카테고리로 산출한다.
    """
    r = BUILDING_COLORS["wall"]
    mask = cv2.inRange(hsv, np.array(r["lower"]), np.array(r["upper"]))
    edges = cv2.Canny(mask, 50, 150)

    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=30, minLineLength=20, maxLineGap=10)
    if lines is None or len(lines) == 0:
        return [], 0

    solid_lengths = []  # 내력벽 (실선)
    dotted_lengths = []  # 경량벽 (점선)
    solid_px = 0.0
    dotted_px = 0.0

    for line in lines:
        x1, y1, x2, y2 = line[0]
        px = math.hypot(x2 - x1, y2 - y1)
        line_type = _classify_line_type(mask, x1, y1, x2, y2)

        if line_type == "solid":
            solid_px += px
            solid_lengths.append(round(px * scale, 1))
        else:
            dotted_px += px
            dotted_lengths.append(round(px * scale, 1))

    items = []
    total_cost = 0

    # 내력벽 (실선)
    if solid_px > 0:
        length_m = round(solid_px * scale, 2)
        cat = CATEGORIES["wall"]
        unit_price = get_price("wall", env_type)
        total = round(length_m * unit_price)
        total_cost += total

        n = len(solid_lengths)
        segs = ", ".join(f"{s}m" for s in solid_lengths[:5])
        if n > 5:
            segs += f" 외 {n - 5}개"
        basis = (
            f"내력벽(실선) {n}개 감지\n"
            f"구간: {segs}\n"
            f"총 {length_m}m x {unit_price:,}원/m = {total:,}원"
        )
        items.append({
            "category": "wall", "name": cat["name"],
            "quantity": length_m, "unit": "m",
            "unit_price": unit_price, "total": total, "basis": basis,
        })

    # 경량벽 (점선)
    if dotted_px > 0:
        length_m = round(dotted_px * scale, 2)
        cat = CATEGORIES["wall_light"]
        unit_price = get_price("wall_light", env_type)
        total = round(length_m * unit_price)
        total_cost += total

        n = len(dotted_lengths)
        segs = ", ".join(f"{s}m" for s in dotted_lengths[:5])
        if n > 5:
            segs += f" 외 {n - 5}개"
        basis = (
            f"경량벽(점선) {n}개 감지\n"
            f"구간: {segs}\n"
            f"총 {length_m}m x {unit_price:,}원/m = {total:,}원"
        )
        items.append({
            "category": "wall_light", "name": cat["name"],
            "quantity": length_m, "unit": "m",
            "unit_price": unit_price, "total": total, "basis": basis,
        })

    return items, total_cost


def _detect_grid_system(gray: np.ndarray) -> dict | None:
    """
    도면 가장자리 원(버블) 마커 + 그리드선을 감지하여 구조 격자 메타데이터를 반환한다.

    테두리 15% 영역에서 HoughCircles로 버블 마커를 찾고,
    각 버블 중심에서 수직/수평 연장선을 추출하여 격자 간격을 계산한다.

    Returns:
        {
            "bubbles": [{"x", "y", "radius", "label"}],
            "horizontal_grid": [y좌표 리스트],
            "vertical_grid": [x좌표 리스트],
            "spans_h": [수평 격자 간격 px],
            "spans_v": [수직 격자 간격 px],
        }
        감지 실패 시 None
    """
    h, w = gray.shape[:2]
    border = GRID_BORDER_RATIO

    # 테두리 영역 마스크 생성 (상하좌우 15%)
    border_mask = np.zeros((h, w), dtype=np.uint8)
    bh = int(h * border)
    bw = int(w * border)
    border_mask[:bh, :] = 255        # 상단
    border_mask[h - bh:, :] = 255    # 하단
    border_mask[:, :bw] = 255        # 좌측
    border_mask[:, w - bw:] = 255    # 우측

    # 테두리 영역만 추출
    border_gray = cv2.bitwise_and(gray, gray, mask=border_mask)
    blurred = cv2.GaussianBlur(border_gray, (9, 9), 2)

    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT,
        dp=1.2, minDist=max(GRID_BUBBLE_MIN_RADIUS * 3, 20),
        param1=100, param2=30,
        minRadius=GRID_BUBBLE_MIN_RADIUS,
        maxRadius=GRID_BUBBLE_MAX_RADIUS,
    )

    if circles is None or len(circles[0]) < 2:
        return None

    bubbles = []
    for circle in circles[0]:
        cx, cy, r = int(circle[0]), int(circle[1]), int(circle[2])

        # 버블 내부 OCR로 라벨 읽기
        label = _read_bubble_label(gray, cx, cy, r)
        bubbles.append({"x": cx, "y": cy, "radius": r, "label": label})

    if len(bubbles) < 2:
        return None

    # 수평/수직 분류 (좌우 테두리 → 수평 그리드, 상하 테두리 → 수직 그리드)
    h_grid = sorted(set(
        b["y"] for b in bubbles
        if b["x"] < bw or b["x"] > w - bw
    ))
    v_grid = sorted(set(
        b["x"] for b in bubbles
        if b["y"] < bh or b["y"] > h - bh
    ))

    # 격자 간격 계산
    spans_h = [h_grid[i+1] - h_grid[i] for i in range(len(h_grid) - 1)] if len(h_grid) > 1 else []
    spans_v = [v_grid[i+1] - v_grid[i] for i in range(len(v_grid) - 1)] if len(v_grid) > 1 else []

    return {
        "bubbles": bubbles,
        "horizontal_grid": h_grid,
        "vertical_grid": v_grid,
        "spans_h": spans_h,
        "spans_v": spans_v,
    }


def _read_bubble_label(gray: np.ndarray, cx: int, cy: int, r: int) -> str:
    """버블(원) 내부 영역에서 OCR로 라벨 텍스트를 읽는다."""
    h, w = gray.shape[:2]
    x1 = max(0, cx - r)
    y1 = max(0, cy - r)
    x2 = min(w, cx + r)
    y2 = min(h, cy + r)
    roi = gray[y1:y2, x1:x2]

    if roi.size == 0:
        return ""

    try:
        import pytesseract
        # 단일 문자/숫자 모드 (PSM 10)
        _, thresh = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        text = pytesseract.image_to_string(thresh, config="--oem 3 --psm 10 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
        return text.strip()
    except Exception:
        return ""
