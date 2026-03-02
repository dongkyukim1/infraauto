"""PyInstaller 호환 경로 헬퍼."""
import os
import sys


def get_base_dir():
    """번들 또는 소스 실행 시 데이터 파일 기본 경로."""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    # 소스 실행 시 프로젝트 루트 (core/ 상위)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_data_path(filename):
    """데이터 파일 경로 반환."""
    return os.path.join(get_base_dir(), filename)


def get_writable_dir():
    """쓰기 가능한 디렉토리 (DB, 모델 저장용)."""
    if getattr(sys, 'frozen', False):
        # 번들 실행 시 앱 옆에 저장
        app_dir = os.path.dirname(sys.executable)
        # .app 번들이면 Contents/MacOS 상위로
        if app_dir.endswith("Contents/MacOS"):
            app_dir = os.path.dirname(os.path.dirname(os.path.dirname(app_dir)))
        data_dir = os.path.join(app_dir, "InfraAuto_data")
        os.makedirs(data_dir, exist_ok=True)
        return data_dir
    # 소스 실행 시 프로젝트 루트 (core/ 상위)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
