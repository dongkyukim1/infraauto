"""
Generate a realistic test drawing simulating a Paint-style infrastructure plan.
- Black lines = cable routes (horizontal/vertical)
- Black rectangles = manholes at junctions/endpoints
- Labels for clarity
"""
import cv2
import numpy as np

img = np.ones((800, 1200, 3), dtype=np.uint8) * 255  # white canvas

BLACK = (0, 0, 0)

# ── Main horizontal cable route ────────────────────────────
cv2.line(img, (80, 400), (1120, 400), BLACK, 3)

# ── Branch lines (vertical) ───────────────────────────────
cv2.line(img, (200, 150), (200, 650), BLACK, 3)   # branch 1
cv2.line(img, (500, 200), (500, 600), BLACK, 3)   # branch 2
cv2.line(img, (800, 150), (800, 650), BLACK, 3)   # branch 3
cv2.line(img, (1050, 250), (1050, 550), BLACK, 3) # branch 4

# ── Sub horizontal routes ─────────────────────────────────
cv2.line(img, (200, 200), (800, 200), BLACK, 2)   # upper link
cv2.line(img, (500, 600), (1050, 600), BLACK, 2)   # lower link

# ── Manholes (rectangles at junctions) ────────────────────
manhole_positions = [
    (80, 400),     # left start
    (200, 400),    # junction 1
    (200, 150),    # branch 1 top
    (200, 650),    # branch 1 bottom
    (500, 400),    # junction 2
    (500, 200),    # branch 2 top
    (500, 600),    # branch 2 bottom
    (800, 400),    # junction 3
    (800, 150),    # branch 3 top
    (800, 650),    # branch 3 bottom
    (1050, 400),   # junction 4
    (1050, 250),   # branch 4 top
    (1050, 550),   # branch 4 bottom
    (1120, 400),   # right end
]

for (cx, cy) in manhole_positions:
    half = 18
    cv2.rectangle(img, (cx - half, cy - half), (cx + half, cy + half), BLACK, 2)

# ── Labels (just for human readability) ───────────────────
font = cv2.FONT_HERSHEY_SIMPLEX
cv2.putText(img, "MH", (62, 375), font, 0.4, (100, 100, 100), 1)
for i, (cx, cy) in enumerate(manhole_positions):
    cv2.putText(img, f"MH{i+1}", (cx - 14, cy - 24), font, 0.35, (120, 120, 120), 1)

cv2.putText(img, "CABLE ROUTE PLAN (TEST)", (400, 50), font, 0.9, (80, 80, 80), 2)
cv2.putText(img, "Scale: 1px = 0.1m", (400, 80), font, 0.5, (150, 150, 150), 1)

out = "/Users/a1/Desktop/test_drawing.png"
cv2.imwrite(out, img)
print(f"Created: {out}")
print(f"  - Cable lines: 7 routes")
print(f"  - Manholes: {len(manhole_positions)} boxes")
