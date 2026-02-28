"""
InfraAuto v4 - OCR Engine
============================
Google Cloud Vision (primary) + Tesseract (fallback).
Scale detection, legend recognition.
"""

import os
import re
import cv2
import numpy as np


def detect_scale(image_path: str, engine: str = "tesseract", api_key_path: str = None) -> dict:
    """
    Detect scale text from drawing image.
    Returns dict with scale_text, scale_ratio, pixel_to_meter, all_text.
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"이미지를 열 수 없습니다: {image_path}")

    # Get all text from image
    if engine == "google" and api_key_path:
        all_text = _ocr_google(image_path, api_key_path)
    else:
        all_text = _ocr_tesseract(img)

    # Parse scale from detected text
    scale_text, scale_ratio, pixel_to_meter = _parse_scale(all_text, img.shape)

    # Try to detect legend area
    legend_items = _detect_legend(img, all_text)

    return {
        "scale_text": scale_text,
        "scale_ratio": scale_ratio,
        "pixel_to_meter": pixel_to_meter,
        "all_text": all_text,
        "legend": legend_items,
    }


def _ocr_google(image_path: str, api_key_path: str) -> list[str]:
    """Google Cloud Vision OCR. Supports both API key string and service account JSON."""
    import base64

    # Detect if it's an API key (string) or JSON file path
    is_api_key = not api_key_path.endswith(".json")

    if is_api_key:
        # Use REST API with API key
        return _ocr_google_rest(image_path, api_key_path)

    # Service account JSON path
    try:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = api_key_path
        from google.cloud import vision

        client = vision.ImageAnnotatorClient()
        with open(image_path, "rb") as f:
            content = f.read()

        image = vision.Image(content=content)
        response = client.text_detection(image=image)

        texts = []
        for text in response.text_annotations:
            texts.append(text.description)

        if response.error.message:
            raise Exception(response.error.message)

        return texts
    except ImportError:
        return _ocr_google_rest(image_path, api_key_path)


def _ocr_google_rest(image_path: str, api_key: str) -> list[str]:
    """Google Cloud Vision via REST API (no SDK needed)."""
    import base64
    import json
    import urllib.request

    with open(image_path, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")

    url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"
    body = json.dumps({
        "requests": [{
            "image": {"content": content},
            "features": [{"type": "TEXT_DETECTION", "maxResults": 50}],
        }]
    }).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read().decode("utf-8"))

        texts = []
        for annotation in data.get("responses", [{}])[0].get("textAnnotations", []):
            texts.append(annotation.get("description", ""))
        return texts
    except Exception as e:
        # Fallback to Tesseract on API error
        print(f"Google Vision API 오류, Tesseract fallback: {e}")
        img = cv2.imread(image_path)
        return _ocr_tesseract(img)


def _ocr_tesseract(img: np.ndarray) -> list[str]:
    """Tesseract OCR fallback."""
    try:
        import pytesseract

        # Preprocess for better OCR
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Adaptive threshold for clean text
        processed = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

        # Denoise
        processed = cv2.medianBlur(processed, 3)

        # Run OCR with Korean + English
        custom_config = r"--oem 3 --psm 6 -l kor+eng"
        try:
            text = pytesseract.image_to_string(processed, config=custom_config)
        except Exception:
            # If Korean lang not available, use English only
            text = pytesseract.image_to_string(processed, config=r"--oem 3 --psm 6")

        # Split into lines, filter empty
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return lines

    except ImportError:
        raise ImportError(
            "pytesseract가 설치되지 않았습니다.\n"
            "설치: pip install pytesseract\n"
            "Tesseract 엔진: brew install tesseract"
        )


def _parse_scale(texts: list[str], img_shape: tuple) -> tuple[str, int, float]:
    """
    Parse scale from OCR text.
    Patterns:
      - "1:500", "1 : 200"
      - "Scale 1:100"
      - "축척 1:500"
      - "50mm = 10m"
    """
    full_text = " ".join(texts)

    # Pattern 1: "1:NNN" format
    match = re.search(r"[1１]\s*[:：]\s*(\d{2,5})", full_text)
    if match:
        ratio = int(match.group(1))
        # Assume image is at ~96 DPI (screen), 1 pixel ≈ 0.264mm at 96DPI
        px_to_m = (ratio * 0.000264)
        return f"1:{ratio}", ratio, round(px_to_m, 6)

    # Pattern 2: "Nmm = Nm" or "Ncm = Nm"
    match = re.search(r"(\d+)\s*(mm|cm|m)\s*=\s*(\d+)\s*(mm|cm|m)", full_text, re.IGNORECASE)
    if match:
        v1, u1, v2, u2 = match.groups()
        v1, v2 = float(v1), float(v2)
        # Convert to meters
        mult = {"mm": 0.001, "cm": 0.01, "m": 1.0}
        m1 = v1 * mult.get(u1.lower(), 1)
        m2 = v2 * mult.get(u2.lower(), 1)
        if m1 > 0:
            ratio = int(m2 / m1)
            px_to_m = ratio * 0.000264
            return f"{v1}{u1}={v2}{u2}", ratio, round(px_to_m, 6)

    # Not found → default
    return None, None, 0.1


def _detect_legend(img: np.ndarray, texts: list[str]) -> list[dict]:
    """
    Detect legend area (usually bottom-right) and extract color-label mappings.
    """
    h, w = img.shape[:2]
    legend_items = []

    # Look at bottom-right quadrant for legend
    roi = img[int(h * 0.6):, int(w * 0.6):]
    if roi.size == 0:
        return legend_items

    hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    # Detect colored blocks in the legend region
    color_names = {
        "black": ((0, 0, 0), (180, 80, 80)),
        "blue": ((90, 80, 50), (130, 255, 255)),
        "brown": ((10, 80, 50), (25, 255, 200)),
        "red": ((0, 120, 80), (10, 255, 255)),
        "green": ((35, 80, 50), (85, 255, 255)),
    }

    for name, (lower, upper) in color_names.items():
        mask = cv2.inRange(hsv_roi, np.array(lower), np.array(upper))
        if cv2.countNonZero(mask) > 50:
            legend_items.append({"color": name, "detected": True})

    return legend_items
