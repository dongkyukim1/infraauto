"""
InfraAuto v6 - LLM+OpenCV Hybrid Diagram Analyzer
====================================================
Combines pixel-precise OpenCV measurements with LLM semantic
understanding for construction diagram analysis.

Pipeline:
    1. OpenCV engine runs first (pixel-based precision)
    2. LLM vision model classifies and validates (semantic understanding)
    3. Merge strategy: OpenCV measurements + LLM classifications
    4. LLM text model generates natural language basis summary

Fallback: If Ollama is unavailable or fails, OpenCV results are
returned unchanged -- identical to v5 behavior.
"""

import json
import logging
import math
import os
from typing import Union

import cv2
import numpy as np

from config import (
    LLM_CONFIDENCE_THRESHOLD,
    LLM_ENABLED,
    LLM_FALLBACK_TO_OPENCV,
    OLLAMA_TEXT_MODEL,
    OLLAMA_VISION_MODEL,
)
from core.database import CATEGORIES, get_price
from analysis.llm_engine import OllamaClient

from analysis import engine as engine
from analysis import building_engine as building_engine

logger = logging.getLogger(__name__)

from config import PIXEL_TO_METER

# Category keys grouped by mode for validation
INFRA_CATEGORIES = frozenset(
    k for k, v in CATEGORIES.items() if v["group"] == "infra"
)
BUILDING_CATEGORIES = frozenset(
    k for k, v in CATEGORIES.items() if v["group"] == "building"
)

# All recognized category keys the LLM may return
ALL_CATEGORY_KEYS = frozenset(CATEGORIES.keys())

# Korean vision prompt for diagram analysis
_VISION_PROMPT = (
    "당신은 건설 도면 분석 전문가입니다.\n"
    "이 도면을 분석하여 JSON으로 반환하세요:\n"
    "{\n"
    '  "diagram_type": "인프라" 또는 "건축",\n'
    '  "detected_items": [\n'
    '    {"category": "카테고리키", "estimated_quantity": 숫자,\n'
    '     "unit": "단위", "confidence": 0.0~1.0, "description": "설명"}\n'
    "  ],\n"
    '  "notes": "추가 관찰 사항"\n'
    "}\n"
    "카테고리 키: conduit, cable, earthwork, manhole, handhole, pole, "
    "junction, window_s, window_l, door, flooring, wall, ceiling, tile, paint"
)

# Korean canvas analysis prompt
_CANVAS_PROMPT = (
    "당신은 건설 도면 분석 전문가입니다.\n"
    "사용자가 캔버스에 직접 그린 건설 도면입니다.\n"
    "다음 아이템이 이미 인식되었습니다:\n"
    "{items_summary}\n\n"
    "이 도면 이미지를 분석하여 JSON으로 반환하세요:\n"
    "{{\n"
    '  "observations": "도면에서 관찰되는 전반적인 특징",\n'
    '  "missing_items": [\n'
    '    {{"category": "카테고리키", "reason": "추가해야 하는 이유"}}\n'
    "  ],\n"
    '  "suggestions": [\n'
    '    {{"suggestion": "개선 제안", "priority": "high/medium/low"}}\n'
    "  ],\n"
    '  "layout_assessment": "배치 평가"\n'
    "}}\n"
    "카테고리 키: conduit, cable, earthwork, manhole, handhole, pole, "
    "junction, window_s, window_l, door, flooring, wall, ceiling, tile, paint"
)

# Natural language basis generation prompt
_BASIS_PROMPT = (
    "당신은 건설 견적 전문가입니다.\n"
    "다음 도면 분석 결과를 자연어로 요약해 주세요.\n"
    "각 항목의 수량 산출 근거와 전체적인 분석 결과를 설명하세요.\n\n"
    "분석 모드: {mode}\n"
    "감지된 항목:\n{items_text}\n\n"
    "LLM 관찰 사항: {llm_notes}\n\n"
    "간결하고 명확한 한국어로 3~5문장으로 요약하세요."
)


class LLMDiagramAnalyzer:
    """Hybrid diagram analyzer combining OpenCV precision with LLM understanding.

    The analyzer runs the appropriate OpenCV engine first for pixel-precise
    measurements, then optionally enhances results with LLM-based semantic
    analysis. If the LLM is unavailable or fails at any step, the analyzer
    gracefully falls back to OpenCV-only results.

    Attributes:
        llm_client: OllamaClient instance used for LLM communication.
    """

    def __init__(self, llm_client: Union[OllamaClient, None] = None) -> None:
        """Initialize the hybrid analyzer.

        Args:
            llm_client: OllamaClient instance. If None, a new one is created
                        with default configuration from config.py.
        """
        if llm_client is not None:
            self.llm_client = llm_client
        else:
            self.llm_client = OllamaClient()

    # ── Public API ────────────────────────────────────────────────

    def analyze_diagram(
        self,
        image_path: str,
        mode: str,
        env_type: str = "default",
    ) -> dict:
        """Analyze a construction diagram image with hybrid OpenCV+LLM pipeline.

        Pipeline:
            1. Load image and run the appropriate OpenCV engine
            2. If LLM is enabled and available, send image for semantic analysis
            3. Merge OpenCV measurements with LLM classifications
            4. Generate natural language analysis basis via LLM text model

        Args:
            image_path: Absolute or relative path to the diagram image file.
            mode: Analysis mode -- ``"infra"`` for infrastructure diagrams or
                  ``"building"`` for building/interior diagrams.
            env_type: Environment type for pricing lookup (e.g. ``"default"``,
                      ``"urban"``, ``"suburban"``, ``"mountain"``).

        Returns:
            dict with keys:
                - ``items``: list of item dicts matching engine.py output format
                  (category, name, quantity, unit, unit_price, total, basis)
                - ``grand_total``: total estimated cost
                - ``image_shape``: tuple of (height, width, channels)
                - ``llm_used``: bool indicating whether LLM enhanced the results
                - ``llm_notes``: str with LLM observations or status message
                - ``analysis_basis``: natural language explanation of analysis

        Raises:
            FileNotFoundError: If image_path does not exist.
            ValueError: If mode is not ``"infra"`` or ``"building"``.
        """
        # ── Validate inputs ───────────────────────────────────────
        if mode not in ("infra", "building"):
            raise ValueError(
                f"Invalid mode '{mode}'. Must be 'infra' or 'building'."
            )

        if not os.path.isfile(image_path):
            raise FileNotFoundError(
                f"Image file not found: {image_path}"
            )

        # ── Step 1: Load image and run OpenCV engine ──────────────
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(
                f"Failed to decode image file: {image_path}. "
                "Verify it is a valid image format (PNG, JPG, BMP)."
            )

        image_shape = img.shape

        opencv_result = self._run_opencv_engine(img, mode, env_type)
        opencv_items = opencv_result.get("items", [])
        opencv_total = opencv_result.get("grand_total", 0)

        # ── Step 2: Check LLM availability ────────────────────────
        llm_available = self._check_llm_available()

        if not llm_available:
            note = self._build_unavailable_note()
            return {
                "items": opencv_items,
                "grand_total": opencv_total,
                "image_shape": image_shape,
                "llm_used": False,
                "llm_notes": note,
                "analysis_basis": "",
            }

        # ── Step 3: Send image to LLM for semantic analysis ──────
        llm_result = self._run_llm_vision(image_path)

        if llm_result is None:
            logger.info("LLM vision analysis returned no results; using OpenCV only.")
            return {
                "items": opencv_items,
                "grand_total": opencv_total,
                "image_shape": image_shape,
                "llm_used": False,
                "llm_notes": "LLM 분석 실패 -- OpenCV 결과만 사용",
                "analysis_basis": "",
            }

        # ── Step 4: Merge results ─────────────────────────────────
        llm_notes = llm_result.get("notes", "")
        llm_items = llm_result.get("detected_items", [])

        merged_items, merge_total = self._merge_results(
            opencv_items, llm_items, mode, env_type
        )

        # ── Step 5: Generate natural language basis ───────────────
        analysis_basis = self._generate_basis(
            merged_items, llm_notes, mode
        )

        return {
            "items": merged_items,
            "grand_total": merge_total,
            "image_shape": image_shape,
            "llm_used": True,
            "llm_notes": llm_notes,
            "analysis_basis": analysis_basis,
        }

    def analyze_canvas(
        self,
        canvas_image_path: str,
        canvas_items: list,
        mode: str,
    ) -> dict:
        """Analyze a canvas drawing with LLM enhancement.

        Sends the saved canvas image to the LLM along with a summary of
        already-recognized items, requesting observations about missing
        elements and improvement suggestions.

        Args:
            canvas_image_path: Path to the saved canvas image file.
            canvas_items: List of drawn items from the canvas widget.
                Each item is typically a tuple of (shape, key, color, data).
            mode: ``"infra"`` or ``"building"``.

        Returns:
            dict with keys:
                - ``llm_available``: whether LLM was used
                - ``observations``: general observations about the drawing
                - ``missing_items``: list of potentially missing items
                - ``suggestions``: list of improvement suggestions
                - ``layout_assessment``: assessment of spatial layout
                - ``raw_response``: the raw LLM response dict
        """
        default_response = {
            "llm_available": False,
            "observations": "",
            "missing_items": [],
            "suggestions": [],
            "layout_assessment": "",
            "raw_response": {},
        }

        if not os.path.isfile(canvas_image_path):
            logger.warning("Canvas image not found: %s", canvas_image_path)
            default_response["observations"] = (
                "캔버스 이미지 파일을 찾을 수 없습니다."
            )
            return default_response

        if not self._check_llm_available():
            note = self._build_unavailable_note()
            default_response["observations"] = note
            return default_response

        # Build items summary for the prompt
        items_summary = self._format_canvas_items_summary(canvas_items)

        prompt = _CANVAS_PROMPT.format(items_summary=items_summary)

        # Send to LLM vision model
        try:
            raw_text = self.llm_client.analyze_image(
                canvas_image_path, prompt, OLLAMA_VISION_MODEL
            )
        except Exception as exc:
            logger.error("LLM canvas analysis failed: %s", exc)
            default_response["observations"] = (
                f"LLM 분석 중 오류 발생: {exc}"
            )
            return default_response

        if not raw_text:
            default_response["observations"] = (
                "LLM이 응답하지 않았습니다."
            )
            return default_response

        # Parse JSON response
        parsed = self._parse_llm_json(raw_text)
        if parsed is None:
            return {
                "llm_available": True,
                "observations": raw_text[:500],
                "missing_items": [],
                "suggestions": [],
                "layout_assessment": "",
                "raw_response": {},
            }

        return {
            "llm_available": True,
            "observations": parsed.get("observations", ""),
            "missing_items": self._sanitize_list(
                parsed.get("missing_items", [])
            ),
            "suggestions": self._sanitize_list(
                parsed.get("suggestions", [])
            ),
            "layout_assessment": parsed.get("layout_assessment", ""),
            "raw_response": parsed,
        }

    # ── OpenCV engine dispatch ────────────────────────────────────

    def _run_opencv_engine(
        self,
        img: np.ndarray,
        mode: str,
        env_type: str,
    ) -> dict:
        """Run the appropriate OpenCV analysis engine.

        Args:
            img: Loaded image as numpy array (BGR format).
            mode: ``"infra"`` or ``"building"``.
            env_type: Environment type for pricing.

        Returns:
            dict from the engine with ``items``, ``grand_total``,
            ``image_shape`` keys.
        """
        try:
            if mode == "building":
                result = building_engine.analyze_building_image(
                    img, PIXEL_TO_METER, env_type
                )
            else:
                result = engine.analyze_image_with_basis(
                    img, PIXEL_TO_METER, env_type
                )
            return result
        except Exception as exc:
            logger.error("OpenCV engine failed for mode '%s': %s", mode, exc)
            return {"items": [], "grand_total": 0, "image_shape": img.shape}

    # ── LLM availability check ────────────────────────────────────

    def _check_llm_available(self) -> bool:
        """Determine if LLM analysis should be attempted.

        Returns False if the feature flag is disabled, the client is not
        configured, or the Ollama server is unreachable.
        """
        if not LLM_ENABLED:
            logger.debug("LLM disabled via LLM_ENABLED config flag.")
            return False

        try:
            available = self.llm_client.is_available()
        except Exception as exc:
            logger.warning("LLM availability check raised exception: %s", exc)
            available = False

        if not available:
            logger.info("Ollama server is not reachable.")

        return available

    def _build_unavailable_note(self) -> str:
        """Build a human-readable note explaining why LLM was not used."""
        if not LLM_ENABLED:
            return "LLM 기능이 비활성화되어 있습니다 (LLM_ENABLED=False)"
        return "Ollama 서버에 연결할 수 없습니다 -- OpenCV 결과만 사용"

    # ── LLM vision analysis ───────────────────────────────────────

    def _run_llm_vision(self, image_path: str) -> Union[dict, None]:
        """Send the diagram image to the LLM vision model for analysis.

        Returns the parsed JSON dict on success, or None on any failure
        (timeout, parse error, empty response).
        """
        try:
            raw_text = self.llm_client.analyze_image(
                image_path, _VISION_PROMPT, OLLAMA_VISION_MODEL
            )
        except Exception as exc:
            logger.error("LLM vision request failed: %s", exc)
            return None

        if not raw_text:
            logger.warning("LLM vision model returned empty response.")
            return None

        parsed = self._parse_llm_json(raw_text)
        if parsed is None:
            logger.warning(
                "Failed to parse LLM vision response as JSON. "
                "Raw (truncated): %.300s", raw_text
            )
            return None

        return parsed

    # ── Result merging ────────────────────────────────────────────

    def _merge_results(
        self,
        opencv_items: list,
        llm_items: list,
        mode: str,
        env_type: str,
    ) -> tuple:
        """Merge OpenCV and LLM results using the configured strategy.

        Merge rules:
            - Measurements (quantity, length, area): OpenCV takes priority
              because pixel-based calculations are more precise.
            - Classification (which material categories are present): LLM
              takes priority for semantic understanding.
            - Items detected only by LLM with confidence >= threshold are
              added with LLM-estimated quantities.

        Args:
            opencv_items: Items detected by the OpenCV engine.
            llm_items: Items detected by the LLM vision model.
            mode: ``"infra"`` or ``"building"`` for category validation.
            env_type: Environment type for pricing new items.

        Returns:
            Tuple of (merged_items_list, grand_total).
        """
        valid_categories = (
            INFRA_CATEGORIES if mode == "infra" else BUILDING_CATEGORIES
        )

        # Index OpenCV items by category for fast lookup
        opencv_by_cat = {}
        for item in opencv_items:
            cat = item.get("category", "")
            if cat:
                opencv_by_cat[cat] = item

        # Start with a copy of OpenCV items -- they hold measurement authority
        merged = []
        for item in opencv_items:
            merged_item = dict(item)

            cat = item.get("category", "")
            llm_match = self._find_llm_item(llm_items, cat)

            if llm_match is not None:
                confidence = llm_match.get("confidence", 0.0)
                description = llm_match.get("description", "")

                # Enrich basis text with LLM classification insight
                existing_basis = merged_item.get("basis", "")
                llm_note = (
                    f"\n[LLM 분석] {description} "
                    f"(신뢰도: {confidence:.0%})"
                )
                merged_item["basis"] = existing_basis + llm_note

            merged.append(merged_item)

        # Check for items the LLM found but OpenCV missed
        for llm_item in llm_items:
            cat = self._normalize_category(llm_item.get("category", ""))
            if not cat:
                continue

            # Skip if category is not valid for this mode
            if cat not in valid_categories:
                continue

            # Skip if OpenCV already detected this category
            if cat in opencv_by_cat:
                continue

            confidence = self._safe_float(llm_item.get("confidence", 0.0))
            if confidence < LLM_CONFIDENCE_THRESHOLD:
                logger.debug(
                    "Skipping LLM-only item '%s' with confidence %.2f "
                    "(threshold: %.2f)",
                    cat, confidence, LLM_CONFIDENCE_THRESHOLD,
                )
                continue

            # Build a new item from LLM detection
            new_item = self._build_item_from_llm(
                llm_item, cat, env_type, confidence
            )
            if new_item is not None:
                merged.append(new_item)

        # Recalculate grand total from merged items
        grand_total = sum(item.get("total", 0) for item in merged)

        return merged, round(grand_total)

    def _find_llm_item(
        self,
        llm_items: list,
        target_category: str,
    ) -> Union[dict, None]:
        """Find the LLM item matching a given category key.

        Handles minor variations in category naming that the LLM might
        produce (e.g. trailing whitespace, case differences).
        """
        for item in llm_items:
            cat = self._normalize_category(item.get("category", ""))
            if cat == target_category:
                return item
        return None

    def _build_item_from_llm(
        self,
        llm_item: dict,
        category: str,
        env_type: str,
        confidence: float,
    ) -> Union[dict, None]:
        """Construct a standard item dict from an LLM-only detection.

        Returns None if the category is unknown or quantity is invalid.
        """
        if category not in CATEGORIES:
            logger.warning(
                "LLM returned unknown category '%s'; skipping.", category
            )
            return None

        cat_info = CATEGORIES[category]
        quantity = self._safe_float(llm_item.get("estimated_quantity", 0))

        if quantity <= 0:
            logger.debug(
                "LLM item '%s' has non-positive quantity (%.2f); skipping.",
                category, quantity,
            )
            return None

        unit = llm_item.get("unit", cat_info["unit"])
        # Ensure unit matches the database definition
        if unit not in ("m", "m\u00b2", "ea"):
            unit = cat_info["unit"]

        unit_price = get_price(category, env_type)
        total = round(quantity * unit_price)

        description = llm_item.get("description", "")
        basis = (
            f"[LLM 감지] {cat_info['name']} -- {description}\n"
            f"추정 수량: {quantity}{unit} (신뢰도: {confidence:.0%})\n"
            f"{quantity}{unit} x {unit_price:,}원/{unit} = {total:,}원\n"
            f"* OpenCV 미감지 -- LLM 추정치 사용"
        )

        return {
            "category": category,
            "name": cat_info["name"],
            "quantity": quantity,
            "unit": unit,
            "unit_price": unit_price,
            "total": total,
            "basis": basis,
        }

    # ── Natural language basis generation ─────────────────────────

    def _generate_basis(
        self,
        items: list,
        llm_notes: str,
        mode: str,
    ) -> str:
        """Generate a natural language summary of the analysis using LLM.

        If the LLM text model is unavailable or fails, returns an empty
        string without raising an exception.
        """
        if not items:
            return ""

        # Build items text summary
        lines = []
        for item in items:
            name = item.get("name", "")
            qty = item.get("quantity", 0)
            unit = item.get("unit", "")
            total = item.get("total", 0)
            lines.append(f"- {name}: {qty}{unit} (비용: {total:,}원)")
        items_text = "\n".join(lines)

        mode_label = "인프라" if mode == "infra" else "건축/인테리어"

        prompt = _BASIS_PROMPT.format(
            mode=mode_label,
            items_text=items_text,
            llm_notes=llm_notes or "없음",
        )

        try:
            basis_text = self.llm_client.generate_text(
                prompt, OLLAMA_TEXT_MODEL
            )
        except Exception as exc:
            logger.warning("LLM basis generation failed: %s", exc)
            return ""

        if not basis_text:
            return ""

        return basis_text.strip()

    # ── Canvas helpers ────────────────────────────────────────────

    def _format_canvas_items_summary(self, canvas_items: list) -> str:
        """Build a text summary of canvas items for the LLM prompt.

        Aggregates items by category key and produces a concise summary
        listing counts, lengths, and areas.
        """
        if not canvas_items:
            return "(아이템 없음)"

        counts: dict = {}
        for entry in canvas_items:
            # canvas_items entries are (shape, key, color, data)
            if not isinstance(entry, (list, tuple)) or len(entry) < 4:
                continue
            shape, key, _color, data = entry[0], entry[1], entry[2], entry[3]

            if key not in counts:
                counts[key] = {"count": 0, "total_length": 0.0, "total_area": 0.0}
            counts[key]["count"] += 1

            if shape == "line" and isinstance(data, (list, tuple)) and len(data) >= 4:
                x1, y1, x2, y2 = data[0], data[1], data[2], data[3]
                length = math.hypot(x2 - x1, y2 - y1) * PIXEL_TO_METER
                counts[key]["total_length"] += length
            elif shape in ("rect", "area") and isinstance(data, (list, tuple)) and len(data) >= 4:
                w, h = abs(data[2]), abs(data[3])
                area = w * h * PIXEL_TO_METER * PIXEL_TO_METER
                counts[key]["total_area"] += area

        if not counts:
            return "(아이템 없음)"

        lines = []
        for key, info in counts.items():
            cat_name = CATEGORIES.get(key, {}).get("name", key)
            parts = [f"{cat_name} {info['count']}개"]
            if info["total_length"] > 0:
                parts.append(f"총 길이 {info['total_length']:.1f}m")
            if info["total_area"] > 0:
                parts.append(f"총 면적 {info['total_area']:.1f}m\u00b2")
            lines.append(", ".join(parts))

        return "\n".join(lines)

    # ── JSON parsing utilities ────────────────────────────────────

    def _parse_llm_json(self, raw_text: str) -> Union[dict, None]:
        """Extract and parse a JSON object from LLM response text.

        LLM responses often contain markdown code fences or surrounding
        text around the JSON. This method attempts multiple extraction
        strategies before giving up.

        Returns the parsed dict, or None if parsing fails completely.
        """
        if not raw_text or not raw_text.strip():
            return None

        text = raw_text.strip()

        # Strategy 1: Direct parse
        result = self._try_json_parse(text)
        if result is not None:
            return result

        # Strategy 2: Extract from markdown code fence
        result = self._extract_from_code_fence(text)
        if result is not None:
            return result

        # Strategy 3: Find first { ... } block
        result = self._extract_first_json_object(text)
        if result is not None:
            return result

        return None

    def _try_json_parse(self, text: str) -> Union[dict, None]:
        """Attempt to parse text as JSON. Returns dict or None."""
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    def _extract_from_code_fence(self, text: str) -> Union[dict, None]:
        """Extract JSON from ```json ... ``` or ``` ... ``` blocks."""
        # Try ```json ... ``` first
        markers = ["```json", "```JSON", "```"]
        for marker in markers:
            start_idx = text.find(marker)
            if start_idx == -1:
                continue
            content_start = start_idx + len(marker)
            end_idx = text.find("```", content_start)
            if end_idx == -1:
                # No closing fence; try to parse from marker to end
                fragment = text[content_start:].strip()
            else:
                fragment = text[content_start:end_idx].strip()

            result = self._try_json_parse(fragment)
            if result is not None:
                return result

        return None

    def _extract_first_json_object(self, text: str) -> Union[dict, None]:
        """Find the first balanced { ... } in text and attempt parsing."""
        first_brace = text.find("{")
        if first_brace == -1:
            return None

        depth = 0
        in_string = False
        escape_next = False

        for i in range(first_brace, len(text)):
            ch = text[i]

            if escape_next:
                escape_next = False
                continue

            if ch == "\\":
                if in_string:
                    escape_next = True
                continue

            if ch == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[first_brace:i + 1]
                    result = self._try_json_parse(candidate)
                    if result is not None:
                        return result
                    break

        return None

    # ── Category normalization ────────────────────────────────────

    def _normalize_category(self, raw: str) -> str:
        """Normalize a category key from LLM output.

        Strips whitespace, lowercases, and validates against known
        category keys. Returns an empty string for unrecognized values.
        """
        if not raw:
            return ""

        cleaned = raw.strip().lower()

        if cleaned in ALL_CATEGORY_KEYS:
            return cleaned

        # Handle common LLM variations
        aliases = {
            "window": "window_s",
            "window_small": "window_s",
            "window_large": "window_l",
            "windows": "window_s",
            "windows_s": "window_s",
            "windows_l": "window_l",
            "doors": "door",
            "walls": "wall",
            "ceilings": "ceiling",
            "tiles": "tile",
            "painting": "paint",
            "conduits": "conduit",
            "cables": "cable",
            "poles": "pole",
            "manholes": "manhole",
            "handholes": "handhole",
            "junctions": "junction",
            "floor": "flooring",
            "floors": "flooring",
        }

        return aliases.get(cleaned, "")

    # ── Numeric safety ────────────────────────────────────────────

    @staticmethod
    def _safe_float(value) -> float:
        """Convert a value to float safely. Returns 0.0 on failure."""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        return 0.0

    @staticmethod
    def _sanitize_list(value) -> list:
        """Ensure a value is a list. Wraps non-list values."""
        if isinstance(value, list):
            return value
        if value is None:
            return []
        return [value]
