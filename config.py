"""
InfraAuto v6 - 중앙 설정 모듈
Ollama LLM, Excel 출력, 기능 플래그 등 전역 설정을 관리합니다.
사용자 설정은 user_config.json에 영속 저장됩니다.
"""

import json
import os

# ── 버전 정보 ────────────────────────────────────────────────────
VERSION = "6.1"
APP_NAME = "InfraAuto"

# ── 사용자 설정 파일 경로 ────────────────────────────────────────
_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
_USER_CONFIG_PATH = os.path.join(_CONFIG_DIR, "user_config.json")

# ── 기본값 (변경하지 않는 상수) ──────────────────────────────────

# Ollama LLM 기본값
_DEFAULTS = {
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_VISION_MODEL": "llava:13b",
    "OLLAMA_TEXT_MODEL": "llama3.1:8b",
    "OLLAMA_TIMEOUT": 120,
    "OLLAMA_MAX_RETRIES": 2,
    "LLM_ENABLED": True,
    "LLM_FALLBACK_TO_OPENCV": True,
    "LLM_CONFIDENCE_THRESHOLD": 0.5,
    "MERGE_STRATEGY": "opencv_measure_llm_classify",
    "COMPANY_NAME": "주식회사 인프라오토",
    "PROJECT_NAME": "건설 견적 프로젝트",
    "AUTHOR_NAME": "",
    "DEFAULT_REGION": "서울",
    "DEFAULT_ENV": "default",
    "DEFAULT_GRADE": "보통",
}


def _load_user_config() -> dict:
    """user_config.json에서 사용자 설정을 로드합니다."""
    if os.path.isfile(_USER_CONFIG_PATH):
        try:
            with open(_USER_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_config():
    """현재 설정을 user_config.json에 저장합니다."""
    data = {}
    for key in _DEFAULTS:
        current = globals().get(key)
        if current != _DEFAULTS[key]:
            data[key] = current
    try:
        with open(_USER_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


# ── 설정 로드 및 모듈 변수 초기화 ───────────────────────────────
_user = _load_user_config()

# Ollama LLM 설정
OLLAMA_BASE_URL = _user.get("OLLAMA_BASE_URL", _DEFAULTS["OLLAMA_BASE_URL"])
OLLAMA_VISION_MODEL = _user.get("OLLAMA_VISION_MODEL", _DEFAULTS["OLLAMA_VISION_MODEL"])
OLLAMA_TEXT_MODEL = _user.get("OLLAMA_TEXT_MODEL", _DEFAULTS["OLLAMA_TEXT_MODEL"])
OLLAMA_TIMEOUT = _user.get("OLLAMA_TIMEOUT", _DEFAULTS["OLLAMA_TIMEOUT"])
OLLAMA_MAX_RETRIES = _user.get("OLLAMA_MAX_RETRIES", _DEFAULTS["OLLAMA_MAX_RETRIES"])

# 기능 플래그
LLM_ENABLED = _user.get("LLM_ENABLED", _DEFAULTS["LLM_ENABLED"])
LLM_FALLBACK_TO_OPENCV = _user.get("LLM_FALLBACK_TO_OPENCV", _DEFAULTS["LLM_FALLBACK_TO_OPENCV"])

# 분석 설정
LLM_CONFIDENCE_THRESHOLD = _user.get("LLM_CONFIDENCE_THRESHOLD", _DEFAULTS["LLM_CONFIDENCE_THRESHOLD"])
MERGE_STRATEGY = _user.get("MERGE_STRATEGY", _DEFAULTS["MERGE_STRATEGY"])

# Excel 출력 설정
COMPANY_NAME = _user.get("COMPANY_NAME", _DEFAULTS["COMPANY_NAME"])
PROJECT_NAME = _user.get("PROJECT_NAME", _DEFAULTS["PROJECT_NAME"])
AUTHOR_NAME = _user.get("AUTHOR_NAME", _DEFAULTS["AUTHOR_NAME"])

# Excel 스타일 설정 (상수 -- 영속화 불필요)
HEADER_BG_COLOR = "1E3A5F"
HEADER_FONT_COLOR = "FFFFFF"
ALT_ROW_COLOR = "F0F4F8"
TOTAL_ROW_BG_COLOR = "FFF3CD"
STATUS_COMPLETE_COLOR = "C6EFCE"
STATUS_PROGRESS_COLOR = "FFEB9C"
STATUS_WAITING_COLOR = "FFFFFF"

# 프로젝트 기본값
DEFAULT_REGION = _user.get("DEFAULT_REGION", _DEFAULTS["DEFAULT_REGION"])
DEFAULT_ENV = _user.get("DEFAULT_ENV", _DEFAULTS["DEFAULT_ENV"])
DEFAULT_GRADE = _user.get("DEFAULT_GRADE", _DEFAULTS["DEFAULT_GRADE"])

# ── 분석 파라미터 (매직넘버 통합) ────────────────────────────────
PIXEL_TO_METER = 0.1
MANHOLE_AREA_THRESHOLD = 800       # px² -- 맨홀/핸드홀 구분 기준
WINDOW_SIZE_THRESHOLD = 2000       # px² -- 창문 소/대 구분 기준
HOUGH_THRESHOLD = 50               # HoughLinesP threshold
HOUGH_MIN_LINE_LENGTH = 30         # HoughLinesP minLineLength
HOUGH_MAX_LINE_GAP = 10            # HoughLinesP maxLineGap
MIN_CONTOUR_AREA = 100             # 최소 윤곽선 면적

# ── 도면 분석 고급 파라미터 ────────────────────────────────────

# 실선/점선 판별
LINE_SAMPLE_POINTS = 20            # 선분 샘플링 포인트 수
LINE_SOLID_THRESHOLD = 0.8         # 실선 판별 기준 (on 비율)

# 문 스윙 감지
DOOR_SEARCH_EXPAND = 1.5           # 문 주변 탐색 영역 확장 배율
DOOR_ARC_MIN_RADIUS = 15           # 최소 호 반지름 (px)
DOOR_ARC_MAX_RADIUS = 150          # 최대 호 반지름 (px)

# 창문 유형 분류
WINDOW_PANE_MIN_LINES = 2          # 이중창 최소 평행선 수
WINDOW_PANE_LINE_THRESHOLD = 15    # 평행선 간격 최소 (px)

# 그리드 감지
GRID_BORDER_RATIO = 0.15           # 테두리 탐색 비율
GRID_BUBBLE_MIN_RADIUS = 8         # 버블 최소 반지름
GRID_BUBBLE_MAX_RADIUS = 30        # 버블 최대 반지름
