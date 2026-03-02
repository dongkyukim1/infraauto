"""
InfraAuto v5 - ML Price Predictor (통합 버전)
================================================
인프라 + 건축/인테리어 가격 예측.
환경 변수(지역, 지형, 건물유형, 면적, 층수, 자재등급)에 따른 단가 학습.
"""

import os
import shutil
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import LabelEncoder
from core.app_path import get_base_dir, get_writable_dir

_writable = get_writable_dir()
MODEL_DIR = os.path.join(_writable, "models")
MODEL_PATH = os.path.join(MODEL_DIR, "price_predictor.pkl")
ENCODERS_PATH = os.path.join(MODEL_DIR, "encoders.pkl")
META_PATH = os.path.join(MODEL_DIR, "model_meta.pkl")

# 번들 실행 시 학습된 모델을 쓰기 가능 위치로 복사
_bundled_models = os.path.join(get_base_dir(), "models")
if not os.path.exists(MODEL_DIR) and os.path.exists(_bundled_models):
    shutil.copytree(_bundled_models, MODEL_DIR)

# 인프라 피처
INFRA_FEATURES = ["region", "terrain", "road_width", "depth", "category"]

# 건축 피처
BUILDING_FEATURES = ["region", "building_type", "area_m2", "floors", "material_grade", "category"]

# 통합 피처 (모든 컬럼, 없는 값은 0으로)
ALL_FEATURES = ["region", "terrain", "road_width", "depth",
                "building_type", "area_m2", "floors", "material_grade",
                "category", "project_type"]  # project_type: infra / building

CATEGORICAL_COLS = ["region", "terrain", "building_type", "material_grade", "category", "project_type"]
NUMERIC_COLS = ["road_width", "depth", "area_m2", "floors"]

TARGET_COL = "actual_price"


def train_from_file(file_path: str) -> tuple[float, int]:
    """
    CSV/Excel 파일로 학습.
    Returns (r2_score, row_count).

    지원 컬럼 (모두 필수 아님, 있는 것만 사용):
      - 인프라: region, terrain, road_width, depth, category, actual_price
      - 건축: region, building_type, area_m2, floors, material_grade, category, actual_price
      - 통합: 위 모두 + project_type
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(file_path)
    else:
        df = pd.read_excel(file_path)

    if TARGET_COL not in df.columns:
        raise ValueError(f"필수 컬럼 '{TARGET_COL}' 이 없습니다.")

    if "category" not in df.columns:
        raise ValueError("필수 컬럼 'category' 가 없습니다.")

    # project_type 자동 추론
    if "project_type" not in df.columns:
        if "building_type" in df.columns:
            df["project_type"] = "building"
        else:
            df["project_type"] = "infra"

    # 없는 컬럼은 기본값으로 채움
    defaults = {
        "region": "서울", "terrain": "일반", "road_width": 0.0, "depth": 0.0,
        "building_type": "일반", "area_m2": 0.0, "floors": 1, "material_grade": "보통",
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default

    df = df.dropna(subset=[TARGET_COL, "category"])
    if len(df) < 5:
        raise ValueError(f"데이터가 너무 적습니다 ({len(df)}건). 최소 5건 이상 필요합니다.")

    # 인코딩
    encoders = {}
    X = df[ALL_FEATURES].copy()
    for col in CATEGORICAL_COLS:
        le = LabelEncoder()
        X[col] = le.fit_transform(X[col].astype(str))
        encoders[col] = le
    for col in NUMERIC_COLS:
        X[col] = pd.to_numeric(X[col], errors="coerce").fillna(0)

    y = df[TARGET_COL].values

    # 앙상블: GradientBoosting + RandomForest 평균
    gb = GradientBoostingRegressor(n_estimators=150, max_depth=5, learning_rate=0.1, random_state=42)
    rf = RandomForestRegressor(n_estimators=150, max_depth=8, random_state=42)

    n_splits = min(5, len(df))
    r2_gb, r2_rf = 0.0, 0.0
    if n_splits >= 2:
        scores_gb = cross_val_score(gb, X.values, y, cv=n_splits, scoring="r2")
        scores_rf = cross_val_score(rf, X.values, y, cv=n_splits, scoring="r2")
        r2_gb = float(np.mean(scores_gb))
        r2_rf = float(np.mean(scores_rf))

    gb.fit(X.values, y)
    rf.fit(X.values, y)

    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump({"gb": gb, "rf": rf}, MODEL_PATH)
    joblib.dump(encoders, ENCODERS_PATH)
    joblib.dump({"features": ALL_FEATURES, "r2_gb": r2_gb, "r2_rf": r2_rf, "rows": len(df)}, META_PATH)

    r2_avg = round((r2_gb + r2_rf) / 2, 4)
    return r2_avg, len(df)


def predict(category: str, project_type: str = "infra", **kwargs) -> float:
    """
    단가 예측.

    Args:
        category: 자재 카테고리 (conduit, window_s, flooring, ...)
        project_type: "infra" 또는 "building"
        **kwargs: region, terrain, road_width, depth,
                  building_type, area_m2, floors, material_grade

    Returns:
        예측 단가 (원)
    """
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError("학습된 모델이 없습니다. 먼저 학습을 실행하세요.")

    models = joblib.load(MODEL_PATH)
    encoders = joblib.load(ENCODERS_PATH)

    defaults = {
        "region": "서울", "terrain": "일반", "road_width": 0.0, "depth": 0.0,
        "building_type": "일반", "area_m2": 0.0, "floors": 1, "material_grade": "보통",
    }

    features = {}
    for col in ALL_FEATURES:
        if col == "category":
            val = category
        elif col == "project_type":
            val = project_type
        else:
            val = kwargs.get(col, defaults.get(col, 0))

        if col in CATEGORICAL_COLS:
            le = encoders.get(col)
            if le and val in le.classes_:
                features[col] = le.transform([str(val)])[0]
            else:
                features[col] = 0
        else:
            features[col] = float(val)

    X = np.array([[features[col] for col in ALL_FEATURES]])

    # 앙상블 평균
    pred_gb = models["gb"].predict(X)[0]
    pred_rf = models["rf"].predict(X)[0]
    prediction = (pred_gb + pred_rf) / 2

    return round(max(0, prediction))


def get_model_info() -> dict:
    """학습된 모델 정보 반환."""
    if not os.path.exists(META_PATH):
        return {"trained": False}
    meta = joblib.load(META_PATH)
    return {"trained": True, **meta}
