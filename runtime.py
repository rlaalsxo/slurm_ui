"""실행 환경 — exe(PyInstaller onefile)와 소스 실행 모두에서 같은 경로·실행 명령을 준다."""
import os
import sys
from pathlib import Path

HEALTH_FLAG = "--health"   # SlurmUI.exe --health → Node Health 창(Qt)
SOURCE_DIR = Path(__file__).resolve().parent


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def resource_path(name):
    """exe 안에 같이 묶은 파일(아이콘·.env) 경로."""
    return str(Path(sys._MEIPASS) / name) if is_frozen() else str(SOURCE_DIR / name)


def app_dir():
    """exe 가 놓인 폴더(소스 실행이면 저장소 폴더). onefile 의 압축 해제 폴더(_MEIPASS)는 임시라 쓰지 않는다."""
    return Path(sys.executable).parent if is_frozen() else SOURCE_DIR


def log_path():
    """오류 로그는 exe 옆에(사용자가 찾기 쉽게)."""
    return str(app_dir() / "slurm_ui_error.log")


def health_command():
    """Health 창을 새 프로세스로 띄우는 명령. exe 면 자기 자신을 --health 로 다시 실행한다."""
    if is_frozen():
        return [sys.executable, HEALTH_FLAG]
    return [sys.executable, str(SOURCE_DIR / "main.py"), HEALTH_FLAG]


def health_environment():
    # onefile exe 가 자기 자신을 다시 띄우면 기본적으로 부모의 압축 해제 폴더를 같이 쓴다. 부모(SlurmUI)를 먼저 닫으면
    # 그 폴더가 지워져 Health 창이 깨지므로, 독립된 새 인스턴스로 띄운다(PyInstaller 6.9+).
    return {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
