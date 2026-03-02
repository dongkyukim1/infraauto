"""
InfraAuto v6 - 통합 견적 플랫폼
=================================
인프라(통신/전기) + 건축/인테리어 통합 견적 시스템
그림 그리기 → 자재 인식 → 수량/단가 산출 → 공정 자동추출 → Excel 출력
Ollama LLM 통합 + 전문 Excel 6시트 출력 + 남은작업 관리
"""

import sys

import cv2
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox, QButtonGroup,
    QFrame, QTabWidget, QComboBox, QGroupBox, QCheckBox,
    QDialog, QLineEdit, QProgressBar,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

from core.database import init_db, get_price, CATEGORIES
from export.process_mapper import extract_processes, get_process_summary, export_process_excel
import config
from config import PIXEL_TO_METER

from gui.styles import GLOBAL_STYLE, INFRA_TOOLS, BUILDING_TOOLS, SHAPE_LABELS
from gui.dialogs import LLMSettingsDialog
from gui.workers import LLMAnalysisWorker
from gui.canvas import DrawingCanvas


# ── Main App ──────────────────────────────────────────────


class InfraAutoApp(QWidget):
    def __init__(self):
        super().__init__()
        init_db()
        self.current_mode = "building"  # 기본 건축 모드
        self._llm_client = None
        self._llm_worker = None
        self._remaining_data = []  # 남은작업 데이터 캐시
        self.init_ui()
        self._check_llm_status()

    def init_ui(self):
        self.setWindowTitle(f"InfraAuto v{config.VERSION} - 통합 견적 플랫폼")
        self.setMinimumSize(1400, 800)
        self.setStyleSheet(GLOBAL_STYLE)

        main = QHBoxLayout()
        main.setContentsMargins(24, 24, 24, 24)
        main.setSpacing(24)

        # ── Left: Canvas area ──────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(12)

        # Title + Mode selector
        title_row = QHBoxLayout()
        title = QLabel(f"InfraAuto v{config.VERSION}")
        title.setFont(QFont("Helvetica", 20, QFont.Bold))
        title.setStyleSheet("color: #1E293B;")
        title_row.addWidget(title)
        title_row.addStretch()

        # 모드 선택
        mode_label = QLabel("모드:")
        mode_label.setFont(QFont("Helvetica", 13, QFont.Bold))
        mode_label.setStyleSheet("color: #475569;")
        title_row.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["건축/인테리어", "인프라(통신/전기)"])
        self.mode_combo.setFixedHeight(36)
        self.mode_combo.setFixedWidth(180)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_change)
        title_row.addWidget(self.mode_combo)

        left.addLayout(title_row)

        # 환경 설정 (ML 예측용)
        env_group = QGroupBox("환경 설정 (단가 예측용)")
        env_layout = QHBoxLayout()
        env_layout.setContentsMargins(16, 20, 16, 16)
        env_layout.setSpacing(12)

        self.region_combo = QComboBox()
        self.region_combo.addItems(["서울", "경기", "부산", "대구", "광주", "대전", "인천"])
        self.region_combo.setFixedWidth(90)
        env_layout.addWidget(QLabel("지역:"))
        env_layout.addWidget(self.region_combo)

        self.env_combo = QComboBox()
        self.env_combo.addItems(["default", "urban", "suburban", "mountain"])
        self.env_combo.setFixedWidth(110)
        env_layout.addWidget(QLabel("환경:"))
        env_layout.addWidget(self.env_combo)

        self.grade_combo = QComboBox()
        self.grade_combo.addItems(["보통", "중급", "고급"])
        self.grade_combo.setFixedWidth(90)
        env_layout.addWidget(QLabel("자재등급:"))
        env_layout.addWidget(self.grade_combo)

        env_layout.addStretch()

        # ML 학습 버튼
        ml_btn = QPushButton("ML 학습 데이터 불러오기")
        ml_btn.setFixedHeight(32)
        ml_btn.setStyleSheet("""
            QPushButton {
                background-color: #F59E0B;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #D97706; }
            QPushButton:pressed { background-color: #B45309; }
        """)
        ml_btn.clicked.connect(self._train_ml)
        env_layout.addWidget(ml_btn)

        self.ml_status = QLabel("")
        self.ml_status.setStyleSheet("color: #64748B; font-size: 12px;")
        env_layout.addWidget(self.ml_status)

        env_group.setLayout(env_layout)
        left.addWidget(env_group)

        # ── LLM 설정 패널 ────────────────────────────────
        llm_group = QGroupBox("LLM 분석 설정")
        llm_layout = QHBoxLayout()
        llm_layout.setContentsMargins(16, 20, 16, 16)
        llm_layout.setSpacing(12)

        self.llm_checkbox = QCheckBox("LLM 분석 사용")
        self.llm_checkbox.setChecked(config.LLM_ENABLED)
        self.llm_checkbox.stateChanged.connect(self._on_llm_toggle)
        llm_layout.addWidget(self.llm_checkbox)

        self.llm_status_label = QLabel("확인 중...")
        self.llm_status_label.setStyleSheet("font-size: 12px; color: #64748B;")
        llm_layout.addWidget(self.llm_status_label)

        llm_layout.addStretch()

        # 프로젝트 정보
        llm_layout.addWidget(QLabel("프로젝트:"))
        self.project_name_edit = QLineEdit(config.PROJECT_NAME)
        self.project_name_edit.setFixedWidth(150)
        self.project_name_edit.setPlaceholderText("프로젝트명")
        llm_layout.addWidget(self.project_name_edit)

        llm_layout.addWidget(QLabel("회사:"))
        self.company_name_edit = QLineEdit(config.COMPANY_NAME)
        self.company_name_edit.setFixedWidth(130)
        self.company_name_edit.setPlaceholderText("회사명")
        llm_layout.addWidget(self.company_name_edit)

        llm_settings_btn = QPushButton("LLM 설정")
        llm_settings_btn.setFixedHeight(32)
        llm_settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #7C3AED;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #6D28D9; }
            QPushButton:pressed { background-color: #5B21B6; }
        """)
        llm_settings_btn.clicked.connect(self._open_llm_settings)
        llm_layout.addWidget(llm_settings_btn)

        llm_group.setLayout(llm_layout)
        left.addWidget(llm_group)

        # Canvas (toolbar보다 먼저 생성 - set_tool 호출 필요)
        self.canvas = DrawingCanvas(on_change=self.update_estimate)
        self.canvas.setStyleSheet("background: white; border: 1px solid #CBD5E1; border-radius: 8px;")

        # Toolbar
        self.toolbar_layout = QHBoxLayout()
        self.toolbar_layout.setSpacing(8)
        self.tool_group = QButtonGroup()
        self.tool_group.setExclusive(True)
        self.tool_buttons = []

        self._build_toolbar(BUILDING_TOOLS)

        left.addLayout(self.toolbar_layout)
        left.addWidget(self.canvas)

        # Bottom buttons
        load_row = QHBoxLayout()
        load_btn = QPushButton("PNG 불러오기")
        load_btn.setFixedHeight(36)
        load_btn.clicked.connect(self.load_image)
        load_row.addWidget(load_btn)
        load_row.addStretch()

        undo_btn = QPushButton("\u21a9 되돌리기")
        undo_btn.setFixedHeight(36)
        undo_btn.clicked.connect(lambda: self.canvas.undo())
        load_row.addWidget(undo_btn)

        clear_btn = QPushButton("전체삭제")
        clear_btn.setFixedHeight(36)
        clear_btn.setStyleSheet("color: #DC2626;")
        clear_btn.clicked.connect(lambda: self.canvas.clear_all())
        load_row.addWidget(clear_btn)

        left.addLayout(load_row)

        left_widget = QWidget()
        left_widget.setLayout(left)

        # ── Right: Tabs (견적 + 공정) ─────────────────────
        right = QVBoxLayout()
        right.setSpacing(16)

        self.tabs = QTabWidget()

        # Tab 1: 견적 내역
        est_widget = QWidget()
        est_layout = QVBoxLayout()
        est_layout.setContentsMargins(12, 12, 12, 12)
        est_layout.setSpacing(12)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["항목", "수량", "단위", "단가", "금액", "산출 근거"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 90)
        self.table.setColumnWidth(1, 70)
        self.table.setColumnWidth(2, 50)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(4, 100)
        est_layout.addWidget(self.table)

        self.total_label = QLabel("합계: 0 원")
        self.total_label.setFont(QFont("Helvetica", 18, QFont.Bold))
        self.total_label.setAlignment(Qt.AlignRight)
        self.total_label.setStyleSheet("color: #E11D48; padding: 8px;")
        est_layout.addWidget(self.total_label)

        est_widget.setLayout(est_layout)
        self.tabs.addTab(est_widget, "견적 내역")

        # Tab 2: 공정 내역
        proc_widget = QWidget()
        proc_layout = QVBoxLayout()
        proc_layout.setContentsMargins(12, 12, 12, 12)
        proc_layout.setSpacing(12)

        self.proc_table = QTableWidget()
        self.proc_table.setColumnCount(8)
        self.proc_table.setHorizontalHeaderLabels(
            ["No", "대공정", "세부공정", "수량", "단위", "자재비", "노무비", "합계"])
        self.proc_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.proc_table.setAlternatingRowColors(True)
        self.proc_table.verticalHeader().setVisible(False)
        self.proc_table.setShowGrid(False)

        ph = self.proc_table.horizontalHeader()
        ph.setSectionResizeMode(0, QHeaderView.Fixed)
        ph.setSectionResizeMode(1, QHeaderView.Fixed)
        ph.setSectionResizeMode(2, QHeaderView.Stretch)
        ph.setSectionResizeMode(3, QHeaderView.Fixed)
        ph.setSectionResizeMode(4, QHeaderView.Fixed)
        ph.setSectionResizeMode(5, QHeaderView.Fixed)
        ph.setSectionResizeMode(6, QHeaderView.Fixed)
        ph.setSectionResizeMode(7, QHeaderView.Fixed)
        self.proc_table.setColumnWidth(0, 40)
        self.proc_table.setColumnWidth(1, 90)
        self.proc_table.setColumnWidth(3, 60)
        self.proc_table.setColumnWidth(4, 50)
        self.proc_table.setColumnWidth(5, 85)
        self.proc_table.setColumnWidth(6, 85)
        self.proc_table.setColumnWidth(7, 90)
        proc_layout.addWidget(self.proc_table)

        self.proc_total_label = QLabel("공정 합계: 0 원 | 예상 소요일: 0일")
        self.proc_total_label.setFont(QFont("Helvetica", 14, QFont.Bold))
        self.proc_total_label.setAlignment(Qt.AlignRight)
        self.proc_total_label.setStyleSheet("color: #059669; padding: 8px;")
        proc_layout.addWidget(self.proc_total_label)

        proc_widget.setLayout(proc_layout)
        self.tabs.addTab(proc_widget, "공정 내역")

        # Tab 3: 남은작업
        remaining_widget = QWidget()
        remaining_layout = QVBoxLayout()
        remaining_layout.setContentsMargins(12, 12, 12, 12)
        remaining_layout.setSpacing(12)

        self.remaining_table = QTableWidget()
        self.remaining_table.setColumnCount(10)
        self.remaining_table.setHorizontalHeaderLabels(
            ["No", "공정", "세부공정", "자재", "전체수량", "완료수량",
             "잔여수량", "단위", "진행률(%)", "상태"])
        self.remaining_table.setAlternatingRowColors(True)
        self.remaining_table.verticalHeader().setVisible(False)
        self.remaining_table.setShowGrid(False)

        rh = self.remaining_table.horizontalHeader()
        rh.setSectionResizeMode(0, QHeaderView.Fixed)
        rh.setSectionResizeMode(1, QHeaderView.Fixed)
        rh.setSectionResizeMode(2, QHeaderView.Stretch)
        rh.setSectionResizeMode(3, QHeaderView.Fixed)
        rh.setSectionResizeMode(4, QHeaderView.Fixed)
        rh.setSectionResizeMode(5, QHeaderView.Fixed)
        rh.setSectionResizeMode(6, QHeaderView.Fixed)
        rh.setSectionResizeMode(7, QHeaderView.Fixed)
        rh.setSectionResizeMode(8, QHeaderView.Fixed)
        rh.setSectionResizeMode(9, QHeaderView.Fixed)
        self.remaining_table.setColumnWidth(0, 40)
        self.remaining_table.setColumnWidth(1, 80)
        self.remaining_table.setColumnWidth(3, 70)
        self.remaining_table.setColumnWidth(4, 70)
        self.remaining_table.setColumnWidth(5, 70)
        self.remaining_table.setColumnWidth(6, 70)
        self.remaining_table.setColumnWidth(7, 45)
        self.remaining_table.setColumnWidth(8, 70)
        self.remaining_table.setColumnWidth(9, 60)

        self.remaining_table.cellChanged.connect(self._on_remaining_cell_changed)
        remaining_layout.addWidget(self.remaining_table)

        # 전체 진행률 바
        progress_row = QHBoxLayout()
        progress_label = QLabel("전체 진행률:")
        progress_label.setFont(QFont("Helvetica", 13, QFont.Bold))
        progress_row.addWidget(progress_label)

        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setValue(0)
        self.overall_progress.setFixedHeight(28)
        self.overall_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                background: #F1F5F9;
                text-align: center;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #22C55E, stop:1 #16A34A);
                border-radius: 5px;
            }
        """)
        progress_row.addWidget(self.overall_progress)

        self.progress_text = QLabel("0%")
        self.progress_text.setFont(QFont("Helvetica", 14, QFont.Bold))
        self.progress_text.setStyleSheet("color: #059669;")
        progress_row.addWidget(self.progress_text)

        remaining_layout.addLayout(progress_row)

        remaining_widget.setLayout(remaining_layout)
        self.tabs.addTab(remaining_widget, "남은작업")

        right.addWidget(self.tabs)

        # Status bar
        self.statusBar_label = QLabel("")
        self.statusBar_label.setStyleSheet("color: #64748B; font-size: 11px; padding: 4px;")
        right.addWidget(self.statusBar_label)

        # Export button
        export_btn = QPushButton("통합 견적서 Excel 저장")
        export_btn.setFont(QFont("Helvetica", 15, QFont.Bold))
        export_btn.setFixedHeight(56)
        export_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: white;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #1D4ED8; }
            QPushButton:pressed { background-color: #1E40AF; }
        """)
        export_btn.clicked.connect(self.export_excel)
        right.addWidget(export_btn)

        right_widget = QWidget()
        right_widget.setLayout(right)
        right_widget.setFixedWidth(600)

        # ── Layout ─────────────────────────────────────────
        main.addWidget(left_widget, 1)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #E2E8F0; border-width: 1px;")
        main.addWidget(sep)

        main.addWidget(right_widget)

        self.setLayout(main)
        self._update_ml_status()
        self.update_estimate()

    def _build_toolbar(self, tools):
        """도구 버튼 빌드."""
        # 기존 버튼 제거
        for btn in self.tool_buttons:
            self.toolbar_layout.removeWidget(btn)
            self.tool_group.removeButton(btn)
            btn.deleteLater()
        self.tool_buttons.clear()

        for i, t in enumerate(tools):
            label = f"{SHAPE_LABELS.get(t['shape'], '?')} {t['label']}"
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(40)
            c = t["color"]
            fg = "white" if c.lightness() < 140 else "black"

            btn.setStyleSheet(f"""
                QPushButton {{
                    padding: 6px 12px;
                    border: 1px solid #CBD5E1;
                    border-radius: 6px;
                    font-size: 13px;
                    font-weight: bold;
                    background-color: #FFFFFF;
                    color: #334155;
                }}
                QPushButton:hover {{
                    background-color: #F8FAFC;
                    border: 1px solid #94A3B8;
                }}
                QPushButton:checked {{
                    background-color: {c.name()};
                    color: {fg};
                    border: 2px solid {c.darker(120).name()};
                }}
            """)
            btn.clicked.connect(lambda _, tt=t: self.canvas.set_tool(tt["key"], tt["shape"], tt["color"]))
            self.toolbar_layout.addWidget(btn)
            self.tool_group.addButton(btn, i)
            self.tool_buttons.append(btn)
            if i == 0:
                btn.setChecked(True)
                self.canvas.set_tool(t["key"], t["shape"], t["color"])

    def _on_mode_change(self, index):
        """모드 전환."""
        if index == 0:
            self.current_mode = "building"
            self._build_toolbar(BUILDING_TOOLS)
        else:
            self.current_mode = "infra"
            self._build_toolbar(INFRA_TOOLS)
        self.canvas.clear_all()

    def _update_ml_status(self):
        """ML 모델 상태 표시."""
        try:
            from analysis.ml_predictor import get_model_info
            info = get_model_info()
            if info.get("trained"):
                r2 = round((info.get("r2_gb", 0) + info.get("r2_rf", 0)) / 2, 3)
                self.ml_status.setText(f"ML: R\u00b2={r2} ({info.get('rows', 0)}건)")
                self.ml_status.setStyleSheet("font-size: 10px; color: #2e7d32;")
            else:
                self.ml_status.setText("ML: 미학습")
        except Exception:
            self.ml_status.setText("ML: 미학습")

    def _train_ml(self):
        """ML 학습 데이터 로드 및 학습."""
        path, _ = QFileDialog.getOpenFileName(
            self, "학습 데이터 선택", "",
            "Data (*.csv *.xlsx *.xls)")
        if not path:
            return
        try:
            from analysis.ml_predictor import train_from_file
            r2, rows = train_from_file(path)
            QMessageBox.information(self, "학습 완료",
                                    f"학습 완료!\nR\u00b2 Score: {r2:.4f}\n데이터: {rows}건")
            self._update_ml_status()
        except Exception as e:
            QMessageBox.critical(self, "학습 오류", str(e))

    def update_estimate(self):
        """견적 + 공정 내역 갱신."""
        qty = self.canvas.get_quantities()

        # 사용할 카테고리 키
        if self.current_mode == "building":
            tool_list = BUILDING_TOOLS
        else:
            tool_list = INFRA_TOOLS

        env_type = self.env_combo.currentText()

        rows = []
        grand_total = 0

        for t in tool_list:
            key = t["key"]
            if key not in qty:
                continue
            q = qty[key]
            cat = CATEGORIES[key]
            unit_price = get_price(key, env_type)

            # ML 예측 시도
            try:
                from analysis.ml_predictor import predict as ml_predict
                predicted = ml_predict(
                    category=key,
                    project_type=self.current_mode,
                    region=self.region_combo.currentText(),
                    material_grade=self.grade_combo.currentText(),
                )
                if predicted > 0:
                    unit_price = predicted
            except Exception:
                pass

            if cat["unit"] == "m":
                amount = round(q["length_px"] * PIXEL_TO_METER, 1)
                unit = "m"
                n = len(q["lines"])
                segs = ", ".join(f"{round(l * PIXEL_TO_METER, 1)}m" for l in q["lines"][:5])
                if n > 5:
                    segs += f" 외 {n - 5}개"
                basis = f"선 {n}개 ({segs})\n총 {amount}m x {unit_price:,}원 = {round(amount * unit_price):,}원"
            elif cat["unit"] == "m\u00b2":
                area_m2 = round(q["area_px"] * PIXEL_TO_METER * PIXEL_TO_METER, 1)
                amount = area_m2
                unit = "m\u00b2"
                det = ", ".join(q["details"][:3]) if q["details"] else ""
                basis = f"영역 {q['count']}개 ({det})\n총 {amount}m\u00b2 x {unit_price:,}원 = {round(amount * unit_price):,}원"
            else:
                amount = q["count"]
                unit = "ea"
                det = ", ".join(q["details"][:5]) if q["details"] else f"{amount}개"
                basis = f"{cat['name']} {amount}개 ({det})\n{amount}개 x {unit_price:,}원 = {round(amount * unit_price):,}원"

            if amount == 0:
                continue

            total = round(amount * unit_price)
            grand_total += total
            rows.append({
                "name": cat["name"],
                "category": key,
                "qty": amount,
                "unit": unit,
                "unit_price": unit_price,
                "total": total,
                "basis": basis,
            })

        # 견적 테이블 업데이트
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(r["name"]))
            qi = QTableWidgetItem(f"{r['qty']:,}" if isinstance(r['qty'], int) else f"{r['qty']}")
            qi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 1, qi)
            self.table.setItem(i, 2, QTableWidgetItem(r["unit"]))
            pi = QTableWidgetItem(f"{r['unit_price']:,}")
            pi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 3, pi)
            ti = QTableWidgetItem(f"{r['total']:,}")
            ti.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 4, ti)
            bi = QTableWidgetItem(r["basis"])
            bi.setToolTip(r["basis"])
            bi.setFont(QFont("Helvetica", 9))
            bi.setForeground(QColor(100, 100, 100))
            self.table.setItem(i, 5, bi)

        self.table.resizeRowsToContents()
        self.total_label.setText(f"합계: {grand_total:,} 원")

        self._current_rows = rows
        self._current_total = grand_total

        # 공정 내역 자동 갱신
        self._update_processes(rows, grand_total)

    def _update_processes(self, estimate_rows, grand_total):
        """공정 내역 테이블 갱신."""
        # 견적 항목을 공정 추출 형식으로 변환
        est_items = []
        for r in estimate_rows:
            est_items.append({
                "category": r["category"],
                "quantity": r["qty"],
                "total": r["total"],
            })

        processes = extract_processes(est_items)
        summary = get_process_summary(processes)

        self._current_processes = processes
        self._current_summary = summary

        # 테이블 업데이트
        self.proc_table.setRowCount(len(processes))
        for i, p in enumerate(processes):
            self.proc_table.setItem(i, 0, QTableWidgetItem(str(p["no"])))
            self.proc_table.setItem(i, 1, QTableWidgetItem(p["process"]))
            self.proc_table.setItem(i, 2, QTableWidgetItem(p["sub_process"]))

            qi = QTableWidgetItem(f"{p['quantity']}")
            qi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.proc_table.setItem(i, 3, qi)

            self.proc_table.setItem(i, 4, QTableWidgetItem(p["unit"]))

            mi = QTableWidgetItem(f"{p['material_cost']:,}")
            mi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.proc_table.setItem(i, 5, mi)

            li = QTableWidgetItem(f"{p['labor_cost']:,}")
            li.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.proc_table.setItem(i, 6, li)

            ti = QTableWidgetItem(f"{p['total_cost']:,}")
            ti.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.proc_table.setItem(i, 7, ti)

        self.proc_table.resizeRowsToContents()

        total_cost = sum(p["total_cost"] for p in processes)
        total_days = sum(s["total_days"] for s in summary.values())
        self.proc_total_label.setText(
            f"공정 합계: {total_cost:,} 원 | 예상 소요일: {round(total_days, 1)}일"
        )

        # 남은작업 탭 갱신
        self._update_remaining_table(processes)

    def _convert_pdf_to_image(self, pdf_path):
        """PDF 첫 페이지를 PNG로 변환. 성공 시 임시 이미지 경로 반환."""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            if len(doc) == 0:
                QMessageBox.critical(self, "오류", "빈 PDF 파일입니다.")
                doc.close()
                return None
            page = doc[0]
            # 고해상도 렌더링 (2x zoom)
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat)
            import tempfile
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            pix.save(tmp.name)
            doc.close()
            self.statusBar_label.setText(f"PDF 변환 완료: {page.rect.width:.0f}x{page.rect.height:.0f}pt")
            return tmp.name
        except ImportError:
            QMessageBox.critical(self, "오류",
                                 "PyMuPDF가 설치되지 않았습니다.\npip install PyMuPDF")
            return None
        except Exception as e:
            QMessageBox.critical(self, "오류", f"PDF 변환 실패: {e}")
            return None

    def _detect_scale_ocr(self, image_path):
        """OCR로 도면 스케일을 감지합니다. 실패 시 기본값 반환."""
        try:
            from analysis.ocr_engine import detect_scale
            result = detect_scale(image_path, engine="tesseract")
            ptm = result.get("pixel_to_meter", PIXEL_TO_METER)
            scale_text = result.get("scale_text")
            if scale_text and ptm > 0:
                self.statusBar_label.setText(f"OCR 스케일 감지: {scale_text} (1px={ptm:.4f}m)")
                return ptm
        except Exception:
            pass
        return PIXEL_TO_METER

    def load_image(self):
        """이미지 로드 및 분석 (LLM 활성 시 비동기 분석)."""
        path, _ = QFileDialog.getOpenFileName(self, "도면 이미지 선택", "",
                                              "Images (*.png *.jpg *.jpeg *.bmp *.pdf)")
        if not path:
            return

        # PDF → 이미지 변환
        if path.lower().endswith(".pdf"):
            path = self._convert_pdf_to_image(path)
            if not path:
                return

        img = cv2.imread(path)
        if img is None:
            QMessageBox.critical(self, "오류", "이미지를 열 수 없습니다.")
            return

        env_type = self.env_combo.currentText()

        # OCR 스케일 감지 시도
        scale = self._detect_scale_ocr(path)

        # LLM 활성 + Ollama 연결 시 비동기 분석
        if config.LLM_ENABLED and self._llm_client and self.llm_checkbox.isChecked():
            self.statusBar_label.setText("LLM 분석 중...")
            self._llm_worker = LLMAnalysisWorker(path, self.current_mode, env_type)
            self._llm_worker.finished.connect(self._on_llm_analysis_finished)
            self._llm_worker.error.connect(self._on_llm_analysis_error)
            self._llm_worker.progress.connect(self._on_llm_progress)
            self._llm_worker.start()
            return

        # OpenCV 분석 (기존 방식)
        if self.current_mode == "building":
            from analysis.building_engine import analyze_building_image
            result = analyze_building_image(img, scale, env_type)
        else:
            from analysis.engine import analyze_image_with_basis
            result = analyze_image_with_basis(img, scale, env_type)

        rows = []
        for it in result["items"]:
            rows.append({
                "name": it["name"],
                "category": it.get("category", ""),
                "qty": it["quantity"],
                "unit": it["unit"],
                "unit_price": it["unit_price"],
                "total": it["total"],
                "basis": it.get("basis", ""),
            })

        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(r["name"]))
            qi = QTableWidgetItem(f"{r['qty']}")
            qi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 1, qi)
            self.table.setItem(i, 2, QTableWidgetItem(r["unit"]))
            pi = QTableWidgetItem(f"{r['unit_price']:,}")
            pi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 3, pi)
            ti = QTableWidgetItem(f"{r['total']:,}")
            ti.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 4, ti)
            bi = QTableWidgetItem(r["basis"])
            bi.setToolTip(r["basis"])
            bi.setFont(QFont("Helvetica", 9))
            bi.setForeground(QColor(100, 100, 100))
            self.table.setItem(i, 5, bi)

        self.table.resizeRowsToContents()
        self.total_label.setText(f"합계: {result['grand_total']:,} 원")
        self._current_rows = rows
        self._current_total = result["grand_total"]
        self.statusBar_label.setText("OpenCV 분석 완료")

        # 공정 갱신
        self._update_processes(rows, result["grand_total"])

    def export_excel(self):
        """통합 견적서 + 공정내역 Excel 저장 (6시트 전문 포맷)."""
        if not hasattr(self, "_current_rows") or not self._current_rows:
            QMessageBox.warning(self, "알림", "먼저 도면을 그려주세요.")
            return

        default_name = "세부금액_총공사금액.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "통합 견적서 저장", default_name, "Excel (*.xlsx)")
        if not path:
            return

        processes = getattr(self, "_current_processes", [])
        summary = getattr(self, "_current_summary", {})

        project_info = {
            "company_name": self.company_name_edit.text().strip() or config.COMPANY_NAME,
            "project_name": self.project_name_edit.text().strip() or config.PROJECT_NAME,
            "author": config.AUTHOR_NAME,
        }

        # 남은작업 데이터 수집
        remaining_work = self._collect_remaining_data()

        try:
            from export.excel_exporter import ProfessionalExcelExporter
            exporter = ProfessionalExcelExporter()
            exporter.export(
                file_path=path,
                estimate_rows=self._current_rows,
                processes=processes,
                summary=summary,
                remaining_work=remaining_work,
                project_info=project_info,
            )
            QMessageBox.information(self, "완료",
                                    f"통합 견적서 저장 완료!\n{path}\n\n"
                                    f"시트 구성:\n"
                                    f"  1. 표지\n"
                                    f"  2. 견적서 (자재별 금액)\n"
                                    f"  3. 세부공정내역 (공정별 자재비+노무비)\n"
                                    f"  4. 공정별요약 (대공정별 집계)\n"
                                    f"  5. 남은작업 (진행률/상태)\n"
                                    f"  6. 대시보드 (차트)")
        except Exception as e:
            # 새 엑스포터 실패 시 기존 방식으로 폴백
            try:
                export_process_excel(
                    processes=processes,
                    summary=summary,
                    file_path=path,
                    estimate_rows=self._current_rows,
                    grand_total=self._current_total,
                )
                QMessageBox.information(self, "완료",
                                        f"견적서 저장 완료 (기본 포맷)\n{path}\n\n"
                                        f"참고: 전문 포맷 오류 - {e}")
            except Exception as e2:
                QMessageBox.critical(self, "오류", f"Excel 저장 실패: {e2}")


    # ── LLM 관련 메서드 ────────────────────────────────────

    def _check_llm_status(self):
        """LLM 연결 상태 확인."""
        try:
            from analysis.llm_engine import OllamaClient
            self._llm_client = OllamaClient()
            if self._llm_client.is_available():
                models = self._llm_client.list_models()
                model_names = ", ".join(models[:3]) if models else "모델 없음"
                self.llm_status_label.setText(f"연결됨 ({model_names})")
                self.llm_status_label.setStyleSheet("font-size: 12px; color: #059669; font-weight: bold;")
            else:
                self.llm_status_label.setText("끊김 - Ollama 미실행")
                self.llm_status_label.setStyleSheet("font-size: 12px; color: #DC2626;")
                self._llm_client = None
        except Exception:
            self.llm_status_label.setText("끊김 - LLM 모듈 오류")
            self.llm_status_label.setStyleSheet("font-size: 12px; color: #DC2626;")
            self._llm_client = None

    def _on_llm_toggle(self, state):
        """LLM 사용 토글."""
        config.LLM_ENABLED = (state == Qt.Checked)
        if config.LLM_ENABLED:
            self._check_llm_status()
        else:
            self.llm_status_label.setText("비활성")
            self.llm_status_label.setStyleSheet("font-size: 12px; color: #64748B;")

    def _open_llm_settings(self):
        """LLM 설정 다이얼로그."""
        dlg = LLMSettingsDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self._check_llm_status()

    def _on_llm_analysis_finished(self, result):
        """LLM 비동기 분석 완료 콜백."""
        self._llm_worker = None

        rows = []
        for it in result.get("items", []):
            rows.append({
                "name": it["name"],
                "category": it.get("category", ""),
                "qty": it["quantity"],
                "unit": it["unit"],
                "unit_price": it["unit_price"],
                "total": it["total"],
                "basis": it.get("basis", ""),
            })

        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(r["name"]))
            qi = QTableWidgetItem(f"{r['qty']}")
            qi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 1, qi)
            self.table.setItem(i, 2, QTableWidgetItem(r["unit"]))
            pi = QTableWidgetItem(f"{r['unit_price']:,}")
            pi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 3, pi)
            ti = QTableWidgetItem(f"{r['total']:,}")
            ti.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 4, ti)
            bi = QTableWidgetItem(r["basis"])
            bi.setToolTip(r["basis"])
            bi.setFont(QFont("Helvetica", 9))
            bi.setForeground(QColor(100, 100, 100))
            self.table.setItem(i, 5, bi)

        self.table.resizeRowsToContents()
        grand_total = result.get("grand_total", sum(r["total"] for r in rows))
        self.total_label.setText(f"합계: {grand_total:,} 원")
        self._current_rows = rows
        self._current_total = grand_total

        # LLM 사용 여부 표시
        if result.get("llm_used"):
            notes = result.get("llm_notes", "")
            basis = result.get("analysis_basis", "")
            if notes or basis:
                self.statusBar_label.setText(f"LLM 분석 완료: {notes[:80]}")
        else:
            self.statusBar_label.setText("OpenCV 분석 완료 (LLM 미사용)")

        self._update_processes(rows, grand_total)

    def _on_llm_analysis_error(self, error_msg):
        """LLM 비동기 분석 오류 콜백."""
        self._llm_worker = None
        self.statusBar_label.setText(f"분석 오류: {error_msg}")
        QMessageBox.warning(self, "LLM 분석 오류",
                            f"LLM 분석 실패: {error_msg}\nOpenCV 분석으로 전환합니다.")

    def _on_llm_progress(self, msg):
        """LLM 분석 진행 상태 업데이트."""
        self.statusBar_label.setText(msg)

    # ── 남은작업 관련 메서드 ──────────────────────────────

    def _update_remaining_table(self, processes):
        """남은작업 탭 업데이트."""
        self.remaining_table.blockSignals(True)
        self.remaining_table.setRowCount(len(processes))

        for i, p in enumerate(processes):
            # No
            no_item = QTableWidgetItem(str(p["no"]))
            no_item.setFlags(no_item.flags() & ~Qt.ItemIsEditable)
            self.remaining_table.setItem(i, 0, no_item)

            # 공정
            proc_item = QTableWidgetItem(p["process"])
            proc_item.setFlags(proc_item.flags() & ~Qt.ItemIsEditable)
            self.remaining_table.setItem(i, 1, proc_item)

            # 세부공정
            sub_item = QTableWidgetItem(p["sub_process"])
            sub_item.setFlags(sub_item.flags() & ~Qt.ItemIsEditable)
            self.remaining_table.setItem(i, 2, sub_item)

            # 자재
            mat_item = QTableWidgetItem(p["material"])
            mat_item.setFlags(mat_item.flags() & ~Qt.ItemIsEditable)
            self.remaining_table.setItem(i, 3, mat_item)

            # 전체수량
            total_qty = p["quantity"]
            tq_item = QTableWidgetItem(f"{total_qty}")
            tq_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tq_item.setFlags(tq_item.flags() & ~Qt.ItemIsEditable)
            self.remaining_table.setItem(i, 4, tq_item)

            # 완료수량 (편집 가능)
            # 기존 데이터가 있으면 유지
            existing_completed = 0
            if i < len(self._remaining_data):
                existing_completed = self._remaining_data[i].get("completed_qty", 0)
            cq_item = QTableWidgetItem(str(existing_completed))
            cq_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.remaining_table.setItem(i, 5, cq_item)

            # 잔여수량
            remaining = max(0, total_qty - existing_completed)
            rq_item = QTableWidgetItem(f"{remaining}")
            rq_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            rq_item.setFlags(rq_item.flags() & ~Qt.ItemIsEditable)
            self.remaining_table.setItem(i, 6, rq_item)

            # 단위
            unit_item = QTableWidgetItem(p["unit"])
            unit_item.setFlags(unit_item.flags() & ~Qt.ItemIsEditable)
            self.remaining_table.setItem(i, 7, unit_item)

            # 진행률
            if total_qty > 0:
                progress = round(existing_completed / total_qty * 100, 1)
            else:
                progress = 0
            pg_item = QTableWidgetItem(f"{progress}")
            pg_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            pg_item.setFlags(pg_item.flags() & ~Qt.ItemIsEditable)
            self.remaining_table.setItem(i, 8, pg_item)

            # 상태
            if progress >= 100:
                status = "완료"
            elif progress > 0:
                status = "진행중"
            else:
                status = "대기"
            st_item = QTableWidgetItem(status)
            st_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            st_item.setFlags(st_item.flags() & ~Qt.ItemIsEditable)
            if status == "완료":
                st_item.setBackground(QColor(198, 239, 206))
            elif status == "진행중":
                st_item.setBackground(QColor(255, 235, 156))
            self.remaining_table.setItem(i, 9, st_item)

        self.remaining_table.resizeRowsToContents()
        self.remaining_table.blockSignals(False)
        self._update_overall_progress()

    def _on_remaining_cell_changed(self, row, col):
        """남은작업 테이블 셀 변경 (완료수량 편집)."""
        if col != 5:  # 완료수량 컬럼만
            return

        self.remaining_table.blockSignals(True)
        try:
            completed_text = self.remaining_table.item(row, 5).text()
            completed = float(completed_text) if completed_text else 0
            total_text = self.remaining_table.item(row, 4).text()
            total_qty = float(total_text) if total_text else 0

            completed = max(0, min(completed, total_qty))

            # 잔여수량 업데이트
            remaining = max(0, total_qty - completed)
            rq_item = self.remaining_table.item(row, 6)
            if rq_item:
                rq_item.setText(f"{remaining}")

            # 진행률 업데이트
            progress = round(completed / total_qty * 100, 1) if total_qty > 0 else 0
            pg_item = self.remaining_table.item(row, 8)
            if pg_item:
                pg_item.setText(f"{progress}")

            # 상태 업데이트
            if progress >= 100:
                status = "완료"
            elif progress > 0:
                status = "진행중"
            else:
                status = "대기"
            st_item = self.remaining_table.item(row, 9)
            if st_item:
                st_item.setText(status)
                if status == "완료":
                    st_item.setBackground(QColor(198, 239, 206))
                elif status == "진행중":
                    st_item.setBackground(QColor(255, 235, 156))
                else:
                    st_item.setBackground(QColor(255, 255, 255))

            # 캐시 업데이트
            while len(self._remaining_data) <= row:
                self._remaining_data.append({"completed_qty": 0, "status": "대기"})
            self._remaining_data[row]["completed_qty"] = completed
            self._remaining_data[row]["status"] = status

        except (ValueError, AttributeError):
            pass
        self.remaining_table.blockSignals(False)
        self._update_overall_progress()

    def _update_overall_progress(self):
        """전체 진행률 업데이트."""
        total_items = self.remaining_table.rowCount()
        if total_items == 0:
            self.overall_progress.setValue(0)
            self.progress_text.setText("0%")
            return

        total_progress = 0
        for i in range(total_items):
            pg_item = self.remaining_table.item(i, 8)
            if pg_item:
                try:
                    total_progress += float(pg_item.text())
                except ValueError:
                    pass

        avg_progress = round(total_progress / total_items, 1)
        self.overall_progress.setValue(int(avg_progress))
        self.progress_text.setText(f"{avg_progress}%")

    def _collect_remaining_data(self):
        """남은작업 테이블에서 데이터 수집."""
        data = []
        for i in range(self.remaining_table.rowCount()):
            row_data = {}
            for col, key in enumerate(["no", "process", "sub_process", "material",
                                        "total_qty", "completed_qty", "remaining_qty",
                                        "unit", "progress", "status"]):
                item = self.remaining_table.item(i, col)
                row_data[key] = item.text() if item else ""
            data.append(row_data)
        return data


def main():
    app = QApplication(sys.argv)
    w = InfraAutoApp()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
