"""
InfraAuto - GUI 워커 스레드
============================
비동기 분석 작업을 처리하는 QThread 워커를 정의합니다.
"""

from PyQt5.QtCore import QThread, pyqtSignal


class LLMAnalysisWorker(QThread):
    """비동기 LLM 분석 스레드."""

    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, image_path, mode, env_type, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.mode = mode
        self.env_type = env_type

    def run(self):
        try:
            self.progress.emit("LLM 분석기 초기화 중...")
            from analysis.llm_analyzer import LLMDiagramAnalyzer
            analyzer = LLMDiagramAnalyzer()

            self.progress.emit("도면 분석 중... (OpenCV + LLM)")
            result = analyzer.analyze_diagram(self.image_path, self.mode, self.env_type)

            self.progress.emit("분석 완료")
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
