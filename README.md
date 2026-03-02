# InfraAuto - 도면 기반 인프라 견적 자동산출

## v6.1 (현재)

### 주요 기능
- Ollama LLM 통합 (비전 모델로 도면 분석 강화)
- 전문 Excel 6시트 출력 (표지, 견적서, 세부공정, 공정별요약, 남은작업, 대시보드)
- 남은작업 관리 (공정별 진행률 추적)
- OpenCV + LLM 하이브리드 분석
- PDF 도면 로드 지원 (PyMuPDF)
- OCR 스케일 자동감지 (Tesseract / Google Vision)
- 사용자 설정 영속화 (user_config.json)

### 설치

```bash
pip install -r requirements.txt
```

### Ollama 설치 가이드

1. Ollama 설치: https://ollama.ai
2. 서버 실행:
```bash
ollama serve
```
3. 모델 다운로드:
```bash
ollama pull llava:13b      # 비전 모델 (도면 분석)
ollama pull llama3.1:8b    # 텍스트 모델 (산출근거 생성)
```

**Ollama 없이도 전체 기능 동작** - LLM 기능만 비활성화됩니다.

### Excel 출력 시트 구성

| # | 시트명 | 내용 |
|---|--------|------|
| 1 | 표지 | 프로젝트명, 날짜, 회사정보, 총액 |
| 2 | 견적서 | 자재별 비용 내역 |
| 3 | 세부공정내역 | 공정별 자재비+노무비 |
| 4 | 공정별요약 | 대공정 기준 집계 |
| 5 | 남은작업 | 진행률, 상태 드롭다운 |
| 6 | 대시보드 | 파이차트, 바차트 |

### 실행 방법
```bash
python infra_auto_gui.py
```

---

## 프로젝트 구조

```
infraauto/
├── infra_auto_gui.py        # 메인 앱 엔트리포인트 + InfraAutoApp
├── config.py                # 중앙 설정 (Ollama, Excel, 분석 파라미터)
├── requirements.txt         # Python 의존성
├── InfraAuto.spec           # PyInstaller 번들링 설정
├── pricing.db               # SQLite 단가 DB
│
├── gui/
│   ├── __init__.py          # GUI 모듈 패키지
│   ├── styles.py            # 스타일시트 + 도구 상수 (INFRA_TOOLS, BUILDING_TOOLS)
│   ├── dialogs.py           # LLM 설정 다이얼로그
│   ├── workers.py           # 비동기 분석 워커 (QThread)
│   └── canvas.py            # 드로잉 캔버스 위젯
│
├── core/
│   ├── app_path.py          # PyInstaller 경로 호환
│   └── database.py          # SQLite 단가 DB 관리
│
├── analysis/
│   ├── engine.py            # 인프라 이미지 분석 (OpenCV)
│   ├── building_engine.py   # 건축 이미지 분석 (OpenCV)
│   ├── llm_engine.py        # Ollama HTTP 클라이언트
│   ├── llm_analyzer.py      # LLM+OpenCV 하이브리드 분석기
│   ├── ml_predictor.py      # ML 단가 예측 (앙상블)
│   └── ocr_engine.py        # OCR 스케일 감지 (Tesseract/Google Vision)
│
├── export/
│   ├── excel_exporter.py    # 전문 Excel 6시트 출력
│   └── process_mapper.py    # 공정 추출 + 매핑
│
├── resources/
│   ├── icon_auto.ico        # 앱 아이콘 (Windows)
│   ├── icon_auto.icns       # 앱 아이콘 (macOS)
│   ├── icon_auto.png        # 앱 아이콘 (범용)
│   └── models/              # ML 학습 모델 (pkl)
│
└── icon_auto.iconset/       # macOS 아이콘셋
```

---

## 이전 버전

### v6.0
- Ollama LLM 통합, 전문 Excel 6시트 출력

### v5
- PyQt5 기반 통합 GUI (인프라 + 건축 모드)
- OpenCV 색상/형태 감지 이미지 분석

### v4: OCR 자동 도면 분석
- Google Cloud Vision API + Tesseract 폴백
- 스케일 자동 인식, 범례 인식

### v3: ML 단가 예측
- GradientBoosting + RandomForest 앙상블

### v2: 공종 분류 확장 + 단가 DB
- 15종 자재 분류 (인프라 7 + 건축 8)

### v1 (MVP)
- Paint 도면 PNG → 케이블/맨홀 검출 → 고정단가 견적
