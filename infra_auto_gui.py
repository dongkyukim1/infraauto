"""
InfraAuto v5 - 통합 견적 플랫폼
=================================
인프라(통신/전기) + 건축/인테리어 통합 견적 시스템
그림 그리기 → 자재 인식 → 수량/단가 산출 → 공정 자동추출 → Excel 출력
"""

import math
import os
import sys

import cv2
import numpy as np
import pandas as pd
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox, QButtonGroup,
    QFrame, QTabWidget, QComboBox, QGroupBox,
)
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QFont, QPainter, QPen, QColor, QCursor

from database import init_db, get_price, CATEGORIES, INFRA_KEYS, BUILDING_KEYS
from process_mapper import extract_processes, get_process_summary, export_process_excel

PIXEL_TO_METER = 0.1

GLOBAL_STYLE = """
/* Global Font & Background */
QWidget {
    font-family: 'Pretendard', 'Apple SD Gothic Neo', 'Malgun Gothic', 'Segoe UI', sans-serif;
    color: #2C3E50;
    background-color: #F4F6F8;
}

/* GroupBox */
QGroupBox {
    font-size: 13px;
    font-weight: bold;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 14px;
    background-color: #FFFFFF;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    left: 12px;
    color: #475569;
}

/* ComboBox */
QComboBox {
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 6px 10px;
    background: #FFFFFF;
    min-width: 4em;
}
QComboBox:hover {
    border: 1px solid #3B82F6;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    image: none; /* Can add a custom arrow icon here if desired */
}
QComboBox QAbstractItemView {
    border: 1px solid #CBD5E1;
    border-radius: 4px;
    selection-background-color: #EFF6FF;
    selection-color: #1D4ED8;
    background: #FFFFFF;
}

/* General Buttons */
QPushButton {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 6px 14px;
    color: #334155;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #F8FAFC;
    border: 1px solid #94A3B8;
}
QPushButton:pressed {
    background-color: #E2E8F0;
}

/* TableWidget */
QTableWidget {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    gridline-color: #F1F5F9;
    selection-background-color: #EFF6FF;
    selection-color: #1D4ED8;
    alternate-background-color: #FAFAF9;
}
QHeaderView::section {
    background-color: #F8FAFC;
    padding: 8px;
    border: none;
    border-right: 1px solid #E2E8F0;
    border-bottom: 1px solid #E2E8F0;
    font-weight: bold;
    color: #475569;
}

/* TabWidget */
QTabWidget::pane {
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    background: #FFFFFF;
    top: -1px;
}
QTabBar::tab {
    background: #F1F5F9;
    border: 1px solid #E2E8F0;
    border-bottom-color: #E2E8F0;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    min-width: 100px;
    padding: 10px 16px;
    color: #64748B;
    margin-right: 4px;
    font-weight: bold;
}
QTabBar::tab:selected {
    background: #FFFFFF;
    border-bottom-color: #FFFFFF;
    color: #2563EB;
}
QTabBar::tab:hover:!selected {
    background: #E2E8F0;
}

/* ScrollBar */
QScrollBar:vertical {
    border: none;
    background: #F1F5F9;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #CBD5E1;
    min-height: 20px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #94A3B8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

# ── 인프라 도구 ─────────────────────────────────────────────

INFRA_TOOLS = [
    {"key": "conduit",   "label": "관로",   "shape": "line",   "color": QColor(0, 0, 0),       "bgr": (0, 0, 0)},
    {"key": "cable",     "label": "케이블", "shape": "line",   "color": QColor(0, 80, 255),    "bgr": (255, 80, 0)},
    {"key": "earthwork", "label": "토공",   "shape": "line",   "color": QColor(139, 90, 43),   "bgr": (43, 90, 139)},
    {"key": "manhole",   "label": "맨홀",   "shape": "rect",   "color": QColor(0, 0, 0),       "bgr": (0, 0, 0)},
    {"key": "handhole",  "label": "핸드홀", "shape": "rect",   "color": QColor(80, 80, 80),    "bgr": (80, 80, 80)},
    {"key": "pole",      "label": "전주",   "shape": "circle", "color": QColor(220, 30, 30),   "bgr": (30, 30, 220)},
    {"key": "junction",  "label": "접속함", "shape": "rect",   "color": QColor(30, 160, 30),   "bgr": (30, 160, 30)},
]

# ── 건축 도구 ─────────────────────────────────────────────

BUILDING_TOOLS = [
    {"key": "window_s",  "label": "창문(소)", "shape": "rect",   "color": QColor(100, 180, 255), "bgr": (255, 180, 100)},
    {"key": "window_l",  "label": "창문(대)", "shape": "rect",   "color": QColor(30, 80, 220),   "bgr": (220, 80, 30)},
    {"key": "door",      "label": "문",       "shape": "rect",   "color": QColor(160, 100, 50),  "bgr": (50, 100, 160)},
    {"key": "flooring",  "label": "장판",     "shape": "area",   "color": QColor(100, 200, 80),  "bgr": (80, 200, 100)},
    {"key": "wall",      "label": "벽체",     "shape": "line",   "color": QColor(240, 140, 20),  "bgr": (20, 140, 240)},
    {"key": "ceiling",   "label": "천장",     "shape": "area",   "color": QColor(160, 80, 200),  "bgr": (200, 80, 160)},
    {"key": "tile",      "label": "타일",     "shape": "area",   "color": QColor(0, 180, 180),   "bgr": (180, 180, 0)},
    {"key": "paint",     "label": "도장",     "shape": "area",   "color": QColor(255, 150, 180), "bgr": (180, 150, 255)},
]

SHAPE_LABELS = {"line": "━", "rect": "□", "circle": "○", "area": "▨"}


# ── Drawing Canvas ────────────────────────────────────────


class DrawingCanvas(QWidget):
    def __init__(self, on_change=None, parent=None):
        super().__init__(parent)
        self.setMinimumSize(750, 480)
        self.setStyleSheet("background-color: white;")
        self.setCursor(QCursor(Qt.CrossCursor))

        self.on_change = on_change
        self.tool_key = "conduit"
        self.tool_shape = "line"
        self.tool_color = QColor(0, 0, 0)
        self.items = []  # (shape, key, color, data)
        self.drawing = False
        self.start_point = None
        self.current_end = None

    def set_tool(self, key, shape, color):
        self.tool_key = key
        self.tool_shape = shape
        self.tool_color = color

    def clear_all(self):
        self.items.clear()
        self.update()
        if self.on_change:
            self.on_change()

    def undo(self):
        if self.items:
            self.items.pop()
            self.update()
            if self.on_change:
                self.on_change()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.drawing = True
            self.start_point = e.pos()
            self.current_end = e.pos()

    def mouseMoveEvent(self, e):
        if self.drawing:
            self.current_end = e.pos()
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or not self.drawing:
            return
        self.drawing = False
        sx, sy = self.start_point.x(), self.start_point.y()
        ex, ey = e.pos().x(), e.pos().y()

        if self.tool_shape == "line":
            if abs(ex - sx) > abs(ey - sy):
                ey = sy
            else:
                ex = sx
            if math.hypot(ex - sx, ey - sy) > 10:
                self.items.append(("line", self.tool_key, self.tool_color, (sx, sy, ex, ey)))

        elif self.tool_shape in ("rect", "area"):
            w, h = abs(ex - sx), abs(ey - sy)
            if w > 5 and h > 5:
                self.items.append((self.tool_shape, self.tool_key, self.tool_color,
                                   (min(sx, ex), min(sy, ey), w, h)))

        elif self.tool_shape == "circle":
            r = int(math.hypot(ex - sx, ey - sy))
            if r > 5:
                self.items.append(("circle", self.tool_key, self.tool_color, (sx, sy, r)))

        self.current_end = None
        self.update()
        if self.on_change:
            self.on_change()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Grid dots
        p.setPen(QPen(QColor(230, 230, 230), 1))
        for x in range(0, self.width(), 30):
            for y in range(0, self.height(), 30):
                p.drawPoint(x, y)

        # Draw items
        for shape, key, color, data in self.items:
            self._draw_item(p, shape, color, data, Qt.SolidLine)

        # Preview
        if self.drawing and self.start_point and self.current_end:
            sx, sy = self.start_point.x(), self.start_point.y()
            ex, ey = self.current_end.x(), self.current_end.y()

            if self.tool_shape == "line":
                if abs(ex - sx) > abs(ey - sy):
                    ey = sy
                else:
                    ex = sx
                self._draw_item(p, "line", self.tool_color, (sx, sy, ex, ey), Qt.DashLine)
                m = math.hypot(ex - sx, ey - sy) * PIXEL_TO_METER
                p.setFont(QFont("Helvetica", 9))
                p.setPen(QPen(self.tool_color))
                p.drawText((sx + ex) // 2 + 8, (sy + ey) // 2 - 8, f"{m:.1f}m")

            elif self.tool_shape in ("rect", "area"):
                self._draw_item(p, self.tool_shape, self.tool_color,
                                (min(sx, ex), min(sy, ey), abs(ex - sx), abs(ey - sy)), Qt.DashLine)
                # 면적 표시
                w_m = abs(ex - sx) * PIXEL_TO_METER
                h_m = abs(ey - sy) * PIXEL_TO_METER
                p.setFont(QFont("Helvetica", 9))
                p.setPen(QPen(self.tool_color))
                label = f"{w_m:.1f}x{h_m:.1f}m"
                if self.tool_shape == "area":
                    label += f" ({w_m * h_m:.1f}m\u00b2)"
                p.drawText(min(sx, ex) + 5, min(sy, ey) - 5, label)

            elif self.tool_shape == "circle":
                r = int(math.hypot(ex - sx, ey - sy))
                self._draw_item(p, "circle", self.tool_color, (sx, sy, r), Qt.DashLine)

        p.end()

    def _draw_item(self, p, shape, color, data, style):
        if shape == "line":
            p.setPen(QPen(color, 3, style))
            p.drawLine(data[0], data[1], data[2], data[3])
        elif shape == "rect":
            p.setPen(QPen(color, 2, style))
            p.setBrush(Qt.NoBrush)
            p.drawRect(data[0], data[1], data[2], data[3])
        elif shape == "area":
            p.setPen(QPen(color, 2, style))
            fill = QColor(color)
            fill.setAlpha(40)
            p.setBrush(fill)
            p.drawRect(data[0], data[1], data[2], data[3])
        elif shape == "circle":
            p.setPen(QPen(color, 2, style))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPoint(data[0], data[1]), data[2], data[2])

    def get_quantities(self) -> dict:
        """Count quantities from drawn items."""
        qty = {}
        for shape, key, color, data in self.items:
            if key not in qty:
                qty[key] = {"count": 0, "length_px": 0.0, "area_px": 0.0, "lines": [], "details": []}
            if shape == "line":
                x1, y1, x2, y2 = data
                px = math.hypot(x2 - x1, y2 - y1)
                qty[key]["length_px"] += px
                qty[key]["lines"].append(round(px, 1))
            elif shape in ("rect", "area"):
                x, y, w, h = data
                area = w * h
                qty[key]["area_px"] += area
                qty[key]["count"] += 1
                w_m = round(w * PIXEL_TO_METER, 2)
                h_m = round(h * PIXEL_TO_METER, 2)
                qty[key]["details"].append(f"{w_m}x{h_m}m")
            else:
                qty[key]["count"] += 1
        return qty


# ── Main App ──────────────────────────────────────────────


class InfraAutoApp(QWidget):
    def __init__(self):
        super().__init__()
        init_db()
        self.current_mode = "building"  # 기본 건축 모드
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("InfraAuto v5 - 통합 견적 플랫폼")
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
        title = QLabel("InfraAuto v5")
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

        undo_btn = QPushButton("↩ 되돌리기")
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

        right.addWidget(self.tabs)

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
            from ml_predictor import get_model_info
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
            from ml_predictor import train_from_file
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
                from ml_predictor import predict as ml_predict
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

    def load_image(self):
        """이미지 로드 및 분석."""
        path, _ = QFileDialog.getOpenFileName(self, "도면 이미지 선택", "",
                                              "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return

        img = cv2.imread(path)
        if img is None:
            QMessageBox.critical(self, "오류", "이미지를 열 수 없습니다.")
            return

        env_type = self.env_combo.currentText()

        if self.current_mode == "building":
            from building_engine import analyze_building_image
            result = analyze_building_image(img, PIXEL_TO_METER, env_type)
        else:
            from engine import analyze_image_with_basis
            result = analyze_image_with_basis(img, PIXEL_TO_METER, env_type)

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

        # 공정 갱신
        self._update_processes(rows, result["grand_total"])

    def export_excel(self):
        """통합 견적서 + 공정내역 Excel 저장."""
        if not hasattr(self, "_current_rows") or not self._current_rows:
            QMessageBox.warning(self, "알림", "먼저 도면을 그려주세요.")
            return

        default_name = "세부금액_총공사금액.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "통합 견적서 저장", default_name, "Excel (*.xlsx)")
        if not path:
            return

        processes = getattr(self, "_current_processes", [])
        summary = getattr(self, "_current_summary", {})

        export_process_excel(
            processes=processes,
            summary=summary,
            file_path=path,
            estimate_rows=self._current_rows,
            grand_total=self._current_total,
        )

        QMessageBox.information(self, "완료",
                                f"통합 견적서 저장 완료!\n{path}\n\n"
                                f"시트 구성:\n"
                                f"  1. 견적서 (자재별 금액)\n"
                                f"  2. 세부공정내역 (공정별 자재비+노무비)\n"
                                f"  3. 공정별요약 (대공정별 집계)")


def main():
    app = QApplication(sys.argv)
    w = InfraAutoApp()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
