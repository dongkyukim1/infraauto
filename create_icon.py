"""Generate a simple app icon for InfraAuto."""
import cv2
import numpy as np
import subprocess
import os

size = 256
img = np.ones((size, size, 3), dtype=np.uint8) * 255

# Blue background rounded-ish
cv2.rectangle(img, (10, 10), (246, 246), (180, 100, 40), -1)  # dark blue BGR

# White lines (cable symbol)
cv2.line(img, (40, 180), (216, 180), (255, 255, 255), 4)
cv2.line(img, (128, 60), (128, 200), (255, 255, 255), 4)

# White rectangles (manhole symbol)
cv2.rectangle(img, (110, 160), (146, 200), (255, 255, 255), 3)
cv2.rectangle(img, (28, 168), (52, 192), (255, 255, 255), 3)
cv2.rectangle(img, (204, 168), (228, 192), (255, 255, 255), 3)

# "IA" text
cv2.putText(img, "IA", (70, 130), cv2.FONT_HERSHEY_SIMPLEX, 2.5, (255, 255, 255), 6)

cv2.imwrite("icon.png", img)

# Convert to icns for macOS
subprocess.run(["mkdir", "-p", "icon.iconset"])
for s in [16, 32, 64, 128, 256]:
    resized = cv2.resize(img, (s, s), interpolation=cv2.INTER_AREA)
    cv2.imwrite(f"icon.iconset/icon_{s}x{s}.png", resized)
    if s <= 128:
        big = cv2.resize(img, (s * 2, s * 2), interpolation=cv2.INTER_AREA)
        cv2.imwrite(f"icon.iconset/icon_{s}x{s}@2x.png", big)

subprocess.run(["iconutil", "-c", "icns", "icon.iconset"])
print("Created icon.icns")
