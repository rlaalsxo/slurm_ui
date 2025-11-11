import requests
import datetime
import os
import sys
from dotenv import load_dotenv

# ==========================
# 환경 설정 로드 (PyInstaller 대응)
# ==========================
def get_base_dir():
    if getattr(sys, 'frozen', False):
        # PyInstaller로 빌드된 실행파일이면 _MEIPASS 사용
        return sys._MEIPASS
    # 개발 중일 때는 현재 파일 기준으로 경로 계산
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = get_base_dir()
ENV_PATH = os.path.join(BASE_DIR, ".env")

# .env 로드
load_dotenv(ENV_PATH)

# ==========================
# 환경변수 읽기
# ==========================
URL_MAIN = os.getenv("SLURM_CONTROLLER_URL_MAIN", "http://127.0.0.1:8000")
URL_TEST = os.getenv("SLURM_CONTROLLER_URL_TEST", "http://127.0.0.1:8001")

_current_env = "MAIN"  # 기본값: MAIN


# ==========================
# 유틸 함수
# ==========================
def set_env(env: str):
    """Slurm 환경 변경 (MAIN / TEST)"""
    global _current_env
    env = env.upper().strip()
    if env not in ("MAIN", "TEST"):
        raise ValueError("env must be 'MAIN' or 'TEST'")
    _current_env = env


def get_base_url():
    """현재 환경에 따른 BASE_URL 반환"""
    return URL_TEST if _current_env == "TEST" else URL_MAIN


# ==========================
# API 함수들
# ==========================
def get_nodes():
    res = requests.get(f"{get_base_url()}/slurm/nodes", timeout=5)
    res.raise_for_status()
    return res.json()


def get_queue():
    res = requests.get(f"{get_base_url()}/slurm/queue", timeout=5)
    res.raise_for_status()
    return res.json()


def get_jobs(start=None, end=None):
    if not start or not end:
        now = datetime.datetime.now()
        start = (now - datetime.timedelta(days=7)).isoformat()
        end = now.isoformat()

    res = requests.get(
        f"{get_base_url()}/slurm/jobs",
        params={"start": start, "end": end},
        timeout=10,
    )
    res.raise_for_status()
    return res.json()


def get_job_status(job_id):
    res = requests.get(f"{get_base_url()}/slurm/status/{job_id}", timeout=5)
    res.raise_for_status()
    return res.json()

def get_job_stats(start=None, end=None):
    """모델별 Job 통계 조회"""
    if not start or not end:
        now = datetime.datetime.now()
        start = (now - datetime.timedelta(days=30)).isoformat()
        end = now.isoformat()

    res = requests.get(
        f"{get_base_url()}/slurm/job-stats",
        params={"start": start, "end": end},
        timeout=15,
    )
    res.raise_for_status()
    return res.json()

