"""
InfraAuto - SQLite Pricing Database
=====================================
7 work categories with environment-based pricing.
"""

import sqlite3
import os
import shutil
from contextlib import contextmanager
from core.app_path import get_base_dir, get_writable_dir

_writable = get_writable_dir()
DB_PATH = os.path.join(_writable, "pricing.db")

# 번들 실행 시 초기 DB를 쓰기 가능 위치로 복사
_bundled_db = os.path.join(get_base_dir(), "pricing.db")
if not os.path.exists(DB_PATH) and os.path.exists(_bundled_db):
    shutil.copy2(_bundled_db, DB_PATH)

# ── 7 Work Categories ──────────────────────────────────────

CATEGORIES = {
    # ── 인프라 (기존) ──
    "conduit":   {"name": "관로",   "unit": "m",  "default_price": 15000,  "group": "infra"},
    "cable":     {"name": "케이블", "unit": "m",  "default_price": 5000,   "group": "infra"},
    "earthwork": {"name": "토공",   "unit": "m",  "default_price": 25000,  "group": "infra"},
    "manhole":   {"name": "맨홀",   "unit": "ea", "default_price": 1200000,"group": "infra"},
    "handhole":  {"name": "핸드홀", "unit": "ea", "default_price": 350000, "group": "infra"},
    "pole":      {"name": "전주",   "unit": "ea", "default_price": 800000, "group": "infra"},
    "junction":  {"name": "접속함", "unit": "ea", "default_price": 450000, "group": "infra"},
    # ── 건축/인테리어 (신규) ──
    "window_s":      {"name": "창문(소)",     "unit": "ea", "default_price": 250000, "group": "building"},
    "window_l":      {"name": "창문(대)",     "unit": "ea", "default_price": 450000, "group": "building"},
    "window_single": {"name": "단창",        "unit": "ea", "default_price": 200000, "group": "building"},
    "window_double": {"name": "이중창",      "unit": "ea", "default_price": 350000, "group": "building"},
    "window_triple": {"name": "삼중창",      "unit": "ea", "default_price": 500000, "group": "building"},
    "door":          {"name": "문",          "unit": "ea", "default_price": 350000, "group": "building"},
    "flooring":      {"name": "장판/바닥",   "unit": "m²", "default_price": 35000,  "group": "building"},
    "wall":          {"name": "벽체(내력)",  "unit": "m",  "default_price": 85000,  "group": "building"},
    "wall_light":    {"name": "벽체(경량)",  "unit": "m",  "default_price": 55000,  "group": "building"},
    "ceiling":       {"name": "천장",        "unit": "m²", "default_price": 45000,  "group": "building"},
    "tile":          {"name": "타일",        "unit": "m²", "default_price": 55000,  "group": "building"},
    "paint":         {"name": "도장",        "unit": "m²", "default_price": 15000,  "group": "building"},
}

INFRA_KEYS = [k for k, v in CATEGORIES.items() if v["group"] == "infra"]
BUILDING_KEYS = [k for k, v in CATEGORIES.items() if v["group"] == "building"]


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables and seed default pricing data."""
    with get_connection() as conn:
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS pricing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                item_name TEXT NOT NULL,
                unit TEXT NOT NULL,
                unit_price REAL NOT NULL,
                env_type TEXT DEFAULT 'default',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Seed defaults if empty
        c.execute("SELECT COUNT(*) FROM pricing")
        if c.fetchone()[0] == 0:
            for cat_key, cat in CATEGORIES.items():
                for env in ["default", "urban", "suburban", "mountain"]:
                    multiplier = {"default": 1.0, "urban": 1.3, "suburban": 1.0, "mountain": 1.5}[env]
                    price = int(cat["default_price"] * multiplier)
                    c.execute(
                        "INSERT INTO pricing (category, item_name, unit, unit_price, env_type) VALUES (?,?,?,?,?)",
                        (cat_key, cat["name"], cat["unit"], price, env),
                    )


def get_all_pricing(env_type: str = "default") -> list[dict]:
    """Get all pricing for a given environment."""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT id, category, item_name, unit, unit_price, env_type FROM pricing WHERE env_type = ? ORDER BY id",
            (env_type,),
        )
        rows = c.fetchall()
    return [
        {"id": r[0], "category": r[1], "item_name": r[2], "unit": r[3], "unit_price": r[4], "env_type": r[5]}
        for r in rows
    ]


def get_price(category: str, env_type: str = "default") -> float:
    """Get unit price for a category and environment."""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT unit_price FROM pricing WHERE category = ? AND env_type = ?",
            (category, env_type),
        )
        row = c.fetchone()
    if row:
        return row[0]
    # Fallback to default
    return CATEGORIES.get(category, {}).get("default_price", 0)


def update_price(row_id: int, unit_price: float):
    """Update a pricing row."""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE pricing SET unit_price = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (unit_price, row_id))


def add_price(category: str, item_name: str, unit: str, unit_price: float, env_type: str = "default"):
    """Add a new pricing row."""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO pricing (category, item_name, unit, unit_price, env_type) VALUES (?,?,?,?,?)",
            (category, item_name, unit, unit_price, env_type),
        )


def delete_price(row_id: int):
    """Delete a pricing row."""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM pricing WHERE id = ?", (row_id,))


# Initialize on import
try:
    init_db()
except Exception as e:
    print(f"DB init warning: {e}")
