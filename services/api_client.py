import requests
import datetime
import os
import sys
from dotenv import load_dotenv

from services.laidd import is_laidd_job

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
VERIFY_PRESIGNED_URL = os.getenv("VERIFY_PRESIGNED_URL", "false").lower() in ("1", "true", "yes")

# Curieus 서버 URL (로그 조회용)
SERVER_URL_MAIN = os.getenv("SERVER_URL_MAIN", "")
SERVER_URL_TEST = os.getenv("SERVER_URL_TEST", "")
_session = requests.Session()

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


def get_current_env():
    return _current_env


def get_server_url():
    """현재 환경에 따른 Curieus 서버 URL 반환 (로그 조회용)"""
    return SERVER_URL_TEST if _current_env == "TEST" else SERVER_URL_MAIN


def _request_json(method, url, timeout=10, **kwargs):
    res = _session.request(method, url, timeout=timeout, **kwargs)
    res.raise_for_status()
    return res.json()


def _slurm_url(path):
    return f"{get_base_url()}{path}"


# ==========================
# API 함수들
# ==========================
def get_nodes():
    return _request_json("GET", _slurm_url("/slurm/nodes"), timeout=5)


def _require_plain_http_url(url, purpose):
    """키를 실어 보낼 주소의 모양을 확인한다 — 사용자 정보·쿼리·조각이 붙은 주소는 거절한다."""
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(f"{purpose} requires a valid configured HTTP or HTTPS server URL")


def _telemetry_get(path, **params):
    suffix = get_current_env()
    url = os.getenv(f"LOG_MANAGER_URL_{suffix}", "").rstrip("/")
    key = os.getenv(f"LOG_MANAGER_READ_KEY_{suffix}", "")
    if not url or not key:
        raise ValueError("Configure LOG_MANAGER_URL_MAIN/TEST and LOG_MANAGER_READ_KEY_MAIN/TEST")
    _require_plain_http_url(url, "Diagnostics")
    return _request_json("GET", url+path, params={"environment": suffix, **params},
                         headers={"X-API-Key": key}, timeout=10, allow_redirects=False)


def get_nodes_with_telemetry():
    nodes = get_nodes()
    try:
        samples = _telemetry_get("/telemetry/nodes")["nodes"]
        by_node = {}
        for sample in samples:
            existing = by_node.get(sample["node"])
            if existing is None or sample["source"] == "host":
                by_node[sample["node"]] = sample
        for node in nodes:
            sample = by_node.get(node["name"])
            if not sample:
                node["diagnostics"] = "No samples"
                continue
            temperatures, warnings = [], []
            for device in sample.get("devices", []):
                metrics = device.get("metrics", {})
                temp = metrics.get("temperature_c")
                if temp is not None:
                    temperatures.append(f"{device['uuid']}={temp:.1f}C")
                limit = metrics.get("temperature_limit_c")
                if metrics.get("thermal_throttle") or (temp is not None and limit is not None and temp >= limit):
                    warnings.append("THERMAL WARNING")
            node["diagnostics"] = ("STALE " if sample["stale"] else "") + ", ".join(temperatures + warnings)
            node["last_sample"] = sample["timestamp"]
    except (requests.RequestException, ValueError, KeyError):
        for node in nodes:
            node["diagnostics"] = "Diagnostics unavailable"
    return nodes


def get_job_diagnostics(job):
    from urllib.parse import quote
    job_id = job.get("internal_job_id") or job.get("job_id")
    return _telemetry_get(f"/telemetry/jobs/{quote(str(job_id), safe='')}/attempts", executor_job_id=str(job.get("job_id")))


def get_queue():
    return _request_json("GET", _slurm_url("/slurm/queue"), timeout=5)


def get_jobs(start=None, end=None):
    if not start or not end:
        now = datetime.datetime.now()
        start = (now - datetime.timedelta(days=7)).isoformat()
        end = now.isoformat()

    return _request_json(
        "GET",
        _slurm_url("/slurm/jobs"),
        params={"start": start, "end": end},
        timeout=10,
    )


def get_job_status(job_id):
    return _request_json("GET", _slurm_url(f"/slurm/status/{job_id}"), timeout=5)

def get_job_stats(start=None, end=None):
    """모델별 Job 통계 조회"""
    if not start or not end:
        now = datetime.datetime.now()
        start = (now - datetime.timedelta(days=30)).isoformat()
        end = now.isoformat()

    return _request_json(
        "GET",
        _slurm_url("/slurm/job-stats"),
        params={"start": start, "end": end},
        timeout=15,
    )


def _laidd_log_endpoint():
    """LAIDD 서버 주소와 읽기 전용 토큰. 둘 중 하나라도 비어 있으면 설정 오류다."""
    suffix = get_current_env()
    url = os.getenv(f"SERVER_URL_LAIDD_{suffix}", "").rstrip("/")
    token = os.getenv(f"LAIDD_LOG_TOKEN_{suffix}", "")
    if not url or not token:
        raise ValueError("Configure SERVER_URL_LAIDD_MAIN/TEST and LAIDD_LOG_TOKEN_MAIN/TEST in .env")
    _require_plain_http_url(url, "LAIDD log lookup")
    return url, token


def _presigned_log_url(job_id, job):
    """로그를 받을 presigned URL. LAIDD 잡은 LAIDD 서버에, 나머지는 Curieus 서버에 묻는다.

    두 서버가 같은 계약(`GET /slurm/logs/{executor_job_id}` → `{"url": ...}`)을 쓰므로 이후 단계는 같다.
    LAIDD 쪽은 사용자 세션이 없는 도구라 `X-API-Key` 로 인증하고, 키가 리다이렉트로 새지 않게 따라가지 않는다.
    """
    if is_laidd_job(job):
        url, token = _laidd_log_endpoint()
        return _request_json(
            "GET",
            f"{url}/slurm/logs/{job_id}",
            params={"job_id": job.get("internal_job_id")} if job.get("internal_job_id") else {},
            headers={"X-API-Key": token},
            timeout=10,
            allow_redirects=False,
        )["url"]

    url = get_server_url()
    if not url:
        raise ValueError("SERVER_URL not configured in .env")
    params = {}
    if job:
        params = {
            "user_id": job.get("user_id") or job.get("account"),
            "job_id": job.get("internal_job_id"),
            "model_id": job.get("model_id"),
        }
        params = {key: value for key, value in params.items() if value not in (None, "")}
    return _request_json(
        "GET",
        f"{url}/slurm/logs/{job_id}",
        params=params,
        timeout=10,
    )["url"]


def get_job_log(job_id, job=None):
    """SLURM Job 로그 조회 (Presigned URL 방식)"""
    presigned_url = _presigned_log_url(job_id, job)
    log_res = _session.get(presigned_url, timeout=30, verify=VERIFY_PRESIGNED_URL)
    log_res.raise_for_status()
    return log_res.text


def get_node_detail(node_name):
    return _request_json("GET", _slurm_url(f"/slurm/node/{node_name}"), timeout=5)


def drain_node(node_name):
    return _request_json("POST", _slurm_url(f"/slurm/node/{node_name}/drain"), timeout=10)


def resume_node(node_name):
    return _request_json("POST", _slurm_url(f"/slurm/node/{node_name}/resume"), timeout=10)

