"""
InfraAuto - GUI 스타일 및 도구 상수
====================================
글로벌 스타일시트, 도구 정의, 형태 라벨을 정의합니다.
"""

from PyQt5.QtGui import QColor

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

# -- Infra tools --

INFRA_TOOLS = [
    {"key": "conduit",   "label": "관로",   "shape": "line",   "color": QColor(0, 0, 0),       "bgr": (0, 0, 0)},
    {"key": "cable",     "label": "케이블", "shape": "line",   "color": QColor(0, 80, 255),    "bgr": (255, 80, 0)},
    {"key": "earthwork", "label": "토공",   "shape": "line",   "color": QColor(139, 90, 43),   "bgr": (43, 90, 139)},
    {"key": "manhole",   "label": "맨홀",   "shape": "rect",   "color": QColor(0, 0, 0),       "bgr": (0, 0, 0)},
    {"key": "handhole",  "label": "핸드홀", "shape": "rect",   "color": QColor(80, 80, 80),    "bgr": (80, 80, 80)},
    {"key": "pole",      "label": "전주",   "shape": "circle", "color": QColor(220, 30, 30),   "bgr": (30, 30, 220)},
    {"key": "junction",  "label": "접속함", "shape": "rect",   "color": QColor(30, 160, 30),   "bgr": (30, 160, 30)},
]

# -- Building tools --

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

SHAPE_LABELS = {"line": "\u2501", "rect": "\u25a1", "circle": "\u25cb", "area": "\u25a8"}
