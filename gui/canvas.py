"""
InfraAuto - 드로잉 캔버스
=========================
도면 그리기 위젯을 정의합니다.
"""

import math

from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QFont, QPainter, QPen, QColor, QCursor

from config import PIXEL_TO_METER


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
