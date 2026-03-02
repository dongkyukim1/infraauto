"""
InfraAuto - 공정 자동추출 모듈
================================
인식된 자재로부터 세부 공정, 인력, 소요일수를 자동 도출합니다.

흐름: 인식된 자재 목록 → 공정 매핑 → 공정내역표 생성 → Excel 시트
"""

import pandas as pd
from core.database import CATEGORIES

# ── 자재 → 공정 매핑 테이블 ─────────────────────────────────

PROCESS_MAP = {
    # ── 건축/인테리어 공정 ──
    "window_s": [
        {"process": "유리공사", "sub": "소형 유리 시공",    "unit": "ea", "labor": "유리공 1인", "days_per_unit": 0.3, "material_ratio": 0.6},
        {"process": "샤시공사", "sub": "소형 샤시 설치",    "unit": "ea", "labor": "샤시공 1인", "days_per_unit": 0.5, "material_ratio": 0.5},
        {"process": "코킹공사", "sub": "창문 코킹",        "unit": "ea", "labor": "방수공 1인", "days_per_unit": 0.1, "material_ratio": 0.3},
    ],
    "window_l": [
        {"process": "유리공사", "sub": "대형 유리 시공",    "unit": "ea", "labor": "유리공 2인", "days_per_unit": 0.5, "material_ratio": 0.6},
        {"process": "샤시공사", "sub": "대형 샤시 설치",    "unit": "ea", "labor": "샤시공 2인", "days_per_unit": 0.8, "material_ratio": 0.5},
        {"process": "코킹공사", "sub": "창문 코킹",        "unit": "ea", "labor": "방수공 1인", "days_per_unit": 0.2, "material_ratio": 0.3},
    ],
    "window_single": [
        {"process": "유리공사", "sub": "단창 유리 시공",    "unit": "ea", "labor": "유리공 1인", "days_per_unit": 0.3, "material_ratio": 0.6},
        {"process": "샤시공사", "sub": "단창 샤시 설치",    "unit": "ea", "labor": "샤시공 1인", "days_per_unit": 0.4, "material_ratio": 0.5},
        {"process": "코킹공사", "sub": "창문 코킹",        "unit": "ea", "labor": "방수공 1인", "days_per_unit": 0.1, "material_ratio": 0.3},
    ],
    "window_double": [
        {"process": "유리공사", "sub": "이중창 유리 시공",  "unit": "ea", "labor": "유리공 1인", "days_per_unit": 0.5, "material_ratio": 0.6},
        {"process": "샤시공사", "sub": "이중창 샤시 설치",  "unit": "ea", "labor": "샤시공 2인", "days_per_unit": 0.7, "material_ratio": 0.5},
        {"process": "코킹공사", "sub": "창문 코킹",        "unit": "ea", "labor": "방수공 1인", "days_per_unit": 0.15, "material_ratio": 0.3},
    ],
    "window_triple": [
        {"process": "유리공사", "sub": "삼중창 유리 시공",  "unit": "ea", "labor": "유리공 2인", "days_per_unit": 0.7, "material_ratio": 0.6},
        {"process": "샤시공사", "sub": "삼중창 샤시 설치",  "unit": "ea", "labor": "샤시공 2인", "days_per_unit": 0.9, "material_ratio": 0.5},
        {"process": "코킹공사", "sub": "창문 코킹",        "unit": "ea", "labor": "방수공 1인", "days_per_unit": 0.2, "material_ratio": 0.3},
    ],
    "door": [
        {"process": "목공사",   "sub": "문틀 설치",        "unit": "ea", "labor": "목수 1인",   "days_per_unit": 0.5, "material_ratio": 0.4},
        {"process": "철물공사", "sub": "경첩/손잡이 설치",  "unit": "ea", "labor": "목수 1인",   "days_per_unit": 0.2, "material_ratio": 0.3},
        {"process": "도장공사", "sub": "문짝 도장",        "unit": "ea", "labor": "도장공 1인", "days_per_unit": 0.3, "material_ratio": 0.2},
    ],
    "flooring": [
        {"process": "바닥공사", "sub": "하지 정리",        "unit": "m²", "labor": "미장공 1인", "days_per_unit": 0.02, "material_ratio": 0.1},
        {"process": "바닥공사", "sub": "장판 깔기",        "unit": "m²", "labor": "도배공 1인", "days_per_unit": 0.03, "material_ratio": 0.7},
        {"process": "바닥공사", "sub": "걸레받이 시공",    "unit": "m²", "labor": "도배공 1인", "days_per_unit": 0.01, "material_ratio": 0.1},
    ],
    "wall": [
        {"process": "미장공사", "sub": "내력벽 미장",      "unit": "m",  "labor": "미장공 1인", "days_per_unit": 0.1,  "material_ratio": 0.4},
        {"process": "도배공사", "sub": "벽지 시공",        "unit": "m",  "labor": "도배공 1인", "days_per_unit": 0.08, "material_ratio": 0.5},
    ],
    "wall_light": [
        {"process": "경량벽공사", "sub": "경량 스터드 설치",  "unit": "m",  "labor": "목수 1인",   "days_per_unit": 0.08, "material_ratio": 0.4},
        {"process": "경량벽공사", "sub": "석고보드 시공",    "unit": "m",  "labor": "목수 1인",   "days_per_unit": 0.06, "material_ratio": 0.4},
        {"process": "도배공사",   "sub": "벽지 시공",        "unit": "m",  "labor": "도배공 1인", "days_per_unit": 0.08, "material_ratio": 0.3},
    ],
    "ceiling": [
        {"process": "천장공사", "sub": "천장틀 설치",      "unit": "m²", "labor": "목수 1인",   "days_per_unit": 0.04, "material_ratio": 0.3},
        {"process": "천장공사", "sub": "석고보드 시공",    "unit": "m²", "labor": "목수 1인",   "days_per_unit": 0.03, "material_ratio": 0.4},
        {"process": "도장공사", "sub": "천장 도장",        "unit": "m²", "labor": "도장공 1인", "days_per_unit": 0.02, "material_ratio": 0.2},
    ],
    "tile": [
        {"process": "방수공사", "sub": "방수 처리",        "unit": "m²", "labor": "방수공 1인", "days_per_unit": 0.03, "material_ratio": 0.3},
        {"process": "타일공사", "sub": "타일 붙이기",      "unit": "m²", "labor": "타일공 1인", "days_per_unit": 0.05, "material_ratio": 0.6},
        {"process": "타일공사", "sub": "줄눈 시공",        "unit": "m²", "labor": "타일공 1인", "days_per_unit": 0.02, "material_ratio": 0.1},
    ],
    "paint": [
        {"process": "도장공사", "sub": "면 처리(퍼티)",    "unit": "m²", "labor": "도장공 1인", "days_per_unit": 0.02, "material_ratio": 0.2},
        {"process": "도장공사", "sub": "초벌 도장",        "unit": "m²", "labor": "도장공 1인", "days_per_unit": 0.02, "material_ratio": 0.3},
        {"process": "도장공사", "sub": "재벌 도장",        "unit": "m²", "labor": "도장공 1인", "days_per_unit": 0.02, "material_ratio": 0.3},
    ],
    # ── 인프라 공정 ──
    "conduit": [
        {"process": "관로공사", "sub": "터파기",           "unit": "m",  "labor": "보통인부 2인", "days_per_unit": 0.05, "material_ratio": 0.1},
        {"process": "관로공사", "sub": "관로 매설",        "unit": "m",  "labor": "배관공 1인",   "days_per_unit": 0.08, "material_ratio": 0.6},
        {"process": "관로공사", "sub": "되메우기",         "unit": "m",  "labor": "보통인부 2인", "days_per_unit": 0.03, "material_ratio": 0.1},
    ],
    "cable": [
        {"process": "케이블공사", "sub": "케이블 포설",    "unit": "m",  "labor": "전기공 2인", "days_per_unit": 0.05, "material_ratio": 0.7},
        {"process": "케이블공사", "sub": "접속 및 단말",   "unit": "m",  "labor": "전기공 1인", "days_per_unit": 0.02, "material_ratio": 0.2},
    ],
    "earthwork": [
        {"process": "토공사",   "sub": "터파기",           "unit": "m",  "labor": "보통인부 2인", "days_per_unit": 0.1,  "material_ratio": 0.1},
        {"process": "토공사",   "sub": "되메우기 및 다짐", "unit": "m",  "labor": "보통인부 2인", "days_per_unit": 0.05, "material_ratio": 0.1},
    ],
    "manhole": [
        {"process": "맨홀공사", "sub": "맨홀 터파기",      "unit": "ea", "labor": "보통인부 3인", "days_per_unit": 1.0,  "material_ratio": 0.1},
        {"process": "맨홀공사", "sub": "맨홀 본체 설치",   "unit": "ea", "labor": "배관공 2인",   "days_per_unit": 1.5,  "material_ratio": 0.6},
        {"process": "맨홀공사", "sub": "되메우기",         "unit": "ea", "labor": "보통인부 2인", "days_per_unit": 0.5,  "material_ratio": 0.1},
    ],
    "handhole": [
        {"process": "핸드홀공사", "sub": "핸드홀 설치",    "unit": "ea", "labor": "배관공 1인",   "days_per_unit": 0.5,  "material_ratio": 0.6},
    ],
    "pole": [
        {"process": "전주공사", "sub": "전주 근가 터파기", "unit": "ea", "labor": "보통인부 2인", "days_per_unit": 0.5,  "material_ratio": 0.1},
        {"process": "전주공사", "sub": "전주 건주",        "unit": "ea", "labor": "전기공 2인",   "days_per_unit": 1.0,  "material_ratio": 0.7},
    ],
    "junction": [
        {"process": "접속함공사", "sub": "접속함 설치",    "unit": "ea", "labor": "전기공 1인",   "days_per_unit": 0.5,  "material_ratio": 0.6},
        {"process": "접속함공사", "sub": "케이블 접속",    "unit": "ea", "labor": "전기공 1인",   "days_per_unit": 0.3,  "material_ratio": 0.3},
    ],
}

# 일당 단가 (노무비)
LABOR_DAILY_RATE = {
    "유리공": 250000,
    "샤시공": 280000,
    "방수공": 230000,
    "목수":   280000,
    "도장공": 220000,
    "도배공": 230000,
    "미장공": 250000,
    "타일공": 270000,
    "전기공": 260000,
    "배관공": 260000,
    "보통인부": 180000,
}


def extract_processes(estimate_items: list, use_llm=False, llm_client=None) -> list:
    """
    견적 항목에서 세부 공정 목록을 추출합니다.

    Args:
        estimate_items: [{"category": str, "quantity": float, ...}, ...]
        use_llm: LLM을 사용하여 누락 공정 검토 여부 (기본 False)
        llm_client: OllamaClient 인스턴스 (use_llm=True일 때 사용)

    Returns:
        [{
            "no": int,
            "process": str,       # 대공정
            "sub_process": str,   # 세부공정
            "material": str,      # 자재명
            "quantity": float,    # 수량
            "unit": str,          # 단위
            "material_cost": int, # 자재비
            "labor": str,         # 투입인력
            "labor_days": float,  # 소요일수
            "labor_cost": int,    # 노무비
            "total_cost": int,    # 합계
        }, ...]
    """
    processes = []
    no = 1

    for item in estimate_items:
        cat_key = item.get("category", "")
        if cat_key not in PROCESS_MAP:
            continue

        quantity = item.get("quantity", 0)
        item_total = item.get("total", 0)

        for proc in PROCESS_MAP[cat_key]:
            # 자재비 = 항목 총액의 비율
            material_cost = round(item_total * proc["material_ratio"])

            # 소요일수 = 수량 × 단위당 일수
            labor_days = round(quantity * proc["days_per_unit"], 1)

            # 노무비 계산
            labor_desc = proc["labor"]
            # "유리공 2인" → 유리공, 2
            parts = labor_desc.replace("인", "").split()
            labor_type = parts[0] if parts else "보통인부"
            labor_count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
            daily_rate = LABOR_DAILY_RATE.get(labor_type, 200000)
            labor_cost = round(daily_rate * labor_count * labor_days)

            total_cost = material_cost + labor_cost

            processes.append({
                "no": no,
                "process": proc["process"],
                "sub_process": proc["sub"],
                "material": CATEGORIES.get(cat_key, {}).get("name", cat_key),
                "quantity": quantity,
                "unit": proc["unit"],
                "material_cost": material_cost,
                "labor": labor_desc,
                "labor_days": labor_days,
                "labor_cost": labor_cost,
                "total_cost": total_cost,
            })
            no += 1

    # LLM 누락 공정 검토
    if use_llm and llm_client and processes:
        try:
            process_names = [f"{p['process']}/{p['sub_process']}" for p in processes]
            categories = list(set(item.get("category", "") for item in estimate_items))
            prompt = (
                "건설 공정 전문가로서 다음 자재 목록에 대한 공정 내역을 검토하세요.\n"
                f"자재 카테고리: {', '.join(categories)}\n"
                f"현재 추출된 공정: {', '.join(process_names)}\n\n"
                "누락된 공정이 있다면 JSON으로 반환하세요:\n"
                '{"missing_processes": [{"process": "대공정명", "sub_process": "세부공정명", '
                '"reason": "누락 사유"}]}\n'
                "누락된 공정이 없으면 빈 배열을 반환하세요."
            )
            result = llm_client.generate_json(prompt)
            missing = result.get("missing_processes", [])
            if missing:
                for mp in missing:
                    processes.append({
                        "no": no,
                        "process": mp.get("process", "기타"),
                        "sub_process": mp.get("sub_process", "LLM 추천 공정"),
                        "material": "LLM 추천",
                        "quantity": 0,
                        "unit": "-",
                        "material_cost": 0,
                        "labor": "-",
                        "labor_days": 0,
                        "labor_cost": 0,
                        "total_cost": 0,
                    })
                    no += 1
        except Exception:
            pass  # LLM 실패 시 기존 결과만 사용

    return processes


def get_process_summary(processes: list) -> dict:
    """공정별 요약 (대공정 기준 집계)."""
    summary = {}
    for p in processes:
        proc_name = p["process"]
        if proc_name not in summary:
            summary[proc_name] = {
                "process": proc_name,
                "material_cost": 0,
                "labor_cost": 0,
                "total_cost": 0,
                "total_days": 0.0,
                "sub_count": 0,
            }
        s = summary[proc_name]
        s["material_cost"] += p["material_cost"]
        s["labor_cost"] += p["labor_cost"]
        s["total_cost"] += p["total_cost"]
        s["total_days"] = max(s["total_days"], p["labor_days"])  # 병렬 공정 가정
        s["sub_count"] += 1

    return summary


def export_process_excel(processes: list, summary: dict, file_path: str, estimate_rows: list = None, grand_total: int = 0):
    """
    공정내역 + 견적 통합 Excel 파일 저장.

    시트 구성:
      1. 견적서 (기존)
      2. 세부공정내역
      3. 공정별요약
    """
    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        # Sheet 1: 견적서
        if estimate_rows:
            est_data = []
            for r in estimate_rows:
                est_data.append({
                    "항목": r["name"],
                    "수량": r["qty"] if "qty" in r else r.get("quantity", 0),
                    "단위": r["unit"],
                    "단가(원)": r["unit_price"],
                    "금액(원)": r["total"],
                    "산출근거": r.get("basis", "").replace("\n", " | "),
                })
            est_data.append({
                "항목": "합계", "수량": "", "단위": "", "단가(원)": "",
                "금액(원)": grand_total, "산출근거": "",
            })
            df_est = pd.DataFrame(est_data)
            df_est.to_excel(writer, index=False, sheet_name="견적서")

        # Sheet 2: 세부공정내역
        proc_data = []
        for p in processes:
            proc_data.append({
                "No": p["no"],
                "대공정": p["process"],
                "세부공정": p["sub_process"],
                "자재": p["material"],
                "수량": p["quantity"],
                "단위": p["unit"],
                "자재비(원)": p["material_cost"],
                "투입인력": p["labor"],
                "소요일수": p["labor_days"],
                "노무비(원)": p["labor_cost"],
                "합계(원)": p["total_cost"],
            })
        total_material = sum(p["material_cost"] for p in processes)
        total_labor = sum(p["labor_cost"] for p in processes)
        total_all = sum(p["total_cost"] for p in processes)
        proc_data.append({
            "No": "", "대공정": "합계", "세부공정": "", "자재": "",
            "수량": "", "단위": "", "자재비(원)": total_material,
            "투입인력": "", "소요일수": "",
            "노무비(원)": total_labor, "합계(원)": total_all,
        })
        df_proc = pd.DataFrame(proc_data)
        df_proc.to_excel(writer, index=False, sheet_name="세부공정내역")

        # Sheet 3: 공정별요약
        sum_data = []
        for s in summary.values():
            sum_data.append({
                "공정명": s["process"],
                "세부공정수": s["sub_count"],
                "자재비(원)": s["material_cost"],
                "노무비(원)": s["labor_cost"],
                "합계(원)": s["total_cost"],
                "예상소요일": s["total_days"],
            })
        total_sum_mat = sum(s["material_cost"] for s in summary.values())
        total_sum_lab = sum(s["labor_cost"] for s in summary.values())
        total_sum_all = sum(s["total_cost"] for s in summary.values())
        max_days = sum(s["total_days"] for s in summary.values())
        sum_data.append({
            "공정명": "합계", "세부공정수": "",
            "자재비(원)": total_sum_mat, "노무비(원)": total_sum_lab,
            "합계(원)": total_sum_all, "예상소요일": round(max_days, 1),
        })
        df_sum = pd.DataFrame(sum_data)
        df_sum.to_excel(writer, index=False, sheet_name="공정별요약")
