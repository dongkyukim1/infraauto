"""Generate sample historical project data for ML training (통합 버전)."""
import random
import pandas as pd

random.seed(42)

regions = ["서울", "경기", "부산", "대구", "광주", "대전", "인천"]
terrains = ["일반", "암반", "연약지반"]
building_types = ["아파트", "오피스텔", "단독주택", "상가", "공장"]
material_grades = ["보통", "중급", "고급"]

# 인프라 카테고리 기본 단가
infra_categories = {
    "conduit": 15000, "cable": 5000, "earthwork": 25000,
    "manhole": 1200000, "handhole": 350000, "pole": 800000, "junction": 450000,
}

# 건축 카테고리 기본 단가
building_categories = {
    "window_s": 250000, "window_l": 450000, "door": 350000,
    "flooring": 35000, "wall": 85000, "ceiling": 45000,
    "tile": 55000, "paint": 15000,
}

region_mult = {"서울": 1.4, "경기": 1.1, "부산": 1.2, "대구": 1.05,
               "광주": 1.0, "대전": 1.0, "인천": 1.15}

rows = []

# ── 인프라 데이터 200건 ──
for _ in range(200):
    region = random.choice(regions)
    terrain = random.choice(terrains)
    road_width = round(random.uniform(4, 20), 1)
    depth = round(random.uniform(0.6, 3.0), 1)
    cat = random.choice(list(infra_categories.keys()))
    base = infra_categories[cat]

    terrain_mult = {"일반": 1.0, "암반": 1.6, "연약지반": 1.3}[terrain]
    depth_mult = 1 + (depth - 1.2) * 0.15
    width_mult = 1 + (road_width - 8) * 0.01
    noise = random.uniform(0.9, 1.1)

    price = int(base * region_mult[region] * terrain_mult * depth_mult * width_mult * noise)

    rows.append({
        "region": region, "terrain": terrain, "road_width": road_width,
        "depth": depth, "building_type": "일반", "area_m2": 0, "floors": 0,
        "material_grade": "보통", "category": cat, "project_type": "infra",
        "actual_price": price,
    })

# ── 건축 데이터 300건 ──
for _ in range(300):
    region = random.choice(regions)
    btype = random.choice(building_types)
    area = round(random.uniform(20, 300), 1)
    floors = random.randint(1, 30)
    grade = random.choice(material_grades)
    cat = random.choice(list(building_categories.keys()))
    base = building_categories[cat]

    grade_mult = {"보통": 1.0, "중급": 1.3, "고급": 1.8}[grade]
    btype_mult = {"아파트": 1.0, "오피스텔": 1.1, "단독주택": 1.15, "상가": 0.95, "공장": 0.85}[btype]
    area_mult = 1 + (area - 100) * 0.001
    floor_mult = 1 + floors * 0.005
    noise = random.uniform(0.85, 1.15)

    price = int(base * region_mult[region] * grade_mult * btype_mult * area_mult * floor_mult * noise)

    rows.append({
        "region": region, "terrain": "일반", "road_width": 0,
        "depth": 0, "building_type": btype, "area_m2": area, "floors": floors,
        "material_grade": grade, "category": cat, "project_type": "building",
        "actual_price": price,
    })

df = pd.DataFrame(rows)
path = "sample_historical_data.csv"
df.to_csv(path, index=False, encoding="utf-8-sig")
print(f"Created {path} ({len(df)} rows)")
print(f"  Infra: {len([r for r in rows if r['project_type'] == 'infra'])} rows")
print(f"  Building: {len([r for r in rows if r['project_type'] == 'building'])} rows")
print(df.head(10).to_string(index=False))
