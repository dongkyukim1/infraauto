"""
InfraAuto - GUI 다이얼로그
==========================
LLM 설정 등 다이얼로그 창을 정의합니다.
"""

from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout,
    QPushButton, QLineEdit, QSpinBox,
)

import config


class LLMSettingsDialog(QDialog):
    """Ollama LLM 설정 다이얼로그."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM 설정")
        self.setFixedSize(420, 240)

        layout = QFormLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.url_edit = QLineEdit(config.OLLAMA_BASE_URL)
        layout.addRow("Ollama URL:", self.url_edit)

        self.vision_edit = QLineEdit(config.OLLAMA_VISION_MODEL)
        layout.addRow("비전 모델:", self.vision_edit)

        self.text_edit = QLineEdit(config.OLLAMA_TEXT_MODEL)
        layout.addRow("텍스트 모델:", self.text_edit)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(30, 600)
        self.timeout_spin.setValue(config.OLLAMA_TIMEOUT)
        self.timeout_spin.setSuffix("초")
        layout.addRow("타임아웃:", self.timeout_spin)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("저장")
        save_btn.setStyleSheet("background-color: #2563EB; color: white; border: none; border-radius: 6px; padding: 8px 16px;")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addRow(btn_layout)

        self.setLayout(layout)

    def _save(self):
        config.OLLAMA_BASE_URL = self.url_edit.text().strip()
        config.OLLAMA_VISION_MODEL = self.vision_edit.text().strip()
        config.OLLAMA_TEXT_MODEL = self.text_edit.text().strip()
        config.OLLAMA_TIMEOUT = self.timeout_spin.value()
        config.save_config()
        self.accept()
