"""
InfraAuto MVP - Paint Drawing to Cost Estimate
================================================
Converts a simple Windows Paint drawing (PNG) into:
  1) Basic quantity takeoff
  2) Simple cost calculation
  3) Excel output (estimate.xlsx)

Assumptions:
  - Black lines = cable routes
  - Closed rectangles = manholes
  - 1 pixel = 0.1 meter
"""

import math
import cv2
import numpy as np
import pandas as pd

# ── Configuration ──────────────────────────────────────────────

INPUT_FILE = "input.png"
OUTPUT_FILE = "estimate.xlsx"
PIXEL_TO_METER = 0.1

PRICING = {
    "cable_per_meter": 5000,
    "manhole_unit": 1_200_000,
}

# ── Image Processing ──────────────────────────────────────────


def load_and_preprocess(path: str):
    """Load image, convert to grayscale, apply edge detection."""
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(f"Cannot open image: {path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    return img, gray, edges


def detect_lines(edges) -> float:
    """Detect lines with HoughLinesP and return total length in pixels."""
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=50,
        minLineLength=30,
        maxLineGap=10,
    )
    if lines is None:
        return 0.0

    total_px = 0.0
    for line in lines:
        x1, y1, x2, y2 = line[0]
        total_px += math.hypot(x2 - x1, y2 - y1)

    return total_px


def detect_manholes(gray) -> int:
    """Detect closed rectangles (4-vertex polygons) as manholes."""
    _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    count = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 200:
            continue

        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)

        # Rectangle = 4 vertices, aspect ratio close to square-ish
        if len(approx) == 4:
            x, y, w, h = cv2.boundingRect(approx)
            aspect = max(w, h) / (min(w, h) + 1e-5)
            if aspect < 3.0:  # filter out long thin shapes
                count += 1

    return count


# ── Cost Calculation ──────────────────────────────────────────


def calculate_costs(cable_length_m: float, manhole_count: int) -> list[dict]:
    """Build line items for the estimate."""
    cable_total = cable_length_m * PRICING["cable_per_meter"]
    manhole_total = manhole_count * PRICING["manhole_unit"]
    grand_total = cable_total + manhole_total

    return [
        {
            "Item": "Cable Installation",
            "Quantity": round(cable_length_m, 2),
            "Unit": "m",
            "Unit Price": PRICING["cable_per_meter"],
            "Total": round(cable_total),
        },
        {
            "Item": "Manhole Installation",
            "Quantity": manhole_count,
            "Unit": "ea",
            "Unit Price": PRICING["manhole_unit"],
            "Total": round(manhole_total),
        },
        {
            "Item": "Grand Total",
            "Quantity": "",
            "Unit": "",
            "Unit Price": "",
            "Total": round(grand_total),
        },
    ]


# ── Excel Output ──────────────────────────────────────────────


def write_excel(rows: list[dict], path: str):
    """Write estimate to Excel file."""
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Estimate")
    print(f"Saved: {path}")


# ── Main ──────────────────────────────────────────────────────


def main():
    print("=" * 50)
    print("InfraAuto MVP - Paint Drawing Cost Estimator")
    print("=" * 50)

    # 1. Load and preprocess
    img, gray, edges = load_and_preprocess(INPUT_FILE)
    print(f"Image loaded: {INPUT_FILE} ({img.shape[1]}x{img.shape[0]}px)")

    # 2. Detect cable routes (lines)
    total_px = detect_lines(edges)
    cable_length_m = total_px * PIXEL_TO_METER
    print(f"Cable length: {total_px:.0f}px = {cable_length_m:.2f}m")

    # 3. Detect manholes (rectangles)
    manhole_count = detect_manholes(gray)
    print(f"Manholes detected: {manhole_count}")

    # 4. Calculate costs
    rows = calculate_costs(cable_length_m, manhole_count)

    # 5. Print summary
    print("-" * 50)
    for r in rows:
        if r["Item"] == "Grand Total":
            print(f"{'Grand Total':>30s}: {r['Total']:>12,} KRW")
        else:
            print(f"{r['Item']:>30s}: {r['Quantity']} {r['Unit']} x {r['Unit Price']:,} = {r['Total']:,} KRW")
    print("-" * 50)

    # 6. Save Excel
    write_excel(rows, OUTPUT_FILE)
    print("Done.")


if __name__ == "__main__":
    main()
