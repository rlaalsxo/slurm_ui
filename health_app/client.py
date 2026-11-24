"""node_manager(노드 점검·재부팅 서비스, 37번:8600) 호출. 주소와 토큰은 .env 의 NODE_MANAGER_URL / NODE_MANAGER_TOKEN.

MAIN/TEST 전환과 상관없이 두 클러스터와 37번을 한 번에 본다.
"""
import os

import requests

from services import api_client  # noqa: F401 — .env 를 먼저 읽는다

NODE_MANAGER_URL = os.getenv("NODE_MANAGER_URL", "").rstrip("/")
NODE_MANAGER_TOKEN = os.getenv("NODE_MANAGER_TOKEN", "")
TOKEN_HEADER = "X-Node-Manager-Token"
READ_TIMEOUT_SECONDS = 15
CHECK_TIMEOUT_SECONDS = 120  # 지금 점검은 SSH·부하 검사가 끝날 때까지 기다린다

_session = requests.Session()


def _request(method, path, timeout=READ_TIMEOUT_SECONDS, **kwargs):
    if not NODE_MANAGER_URL or not NODE_MANAGER_TOKEN:
        raise ValueError(".env 에 NODE_MANAGER_URL / NODE_MANAGER_TOKEN 이 없습니다")
    response = _session.request(method, f"{NODE_MANAGER_URL}{path}", timeout=timeout,
                                headers={TOKEN_HEADER: NODE_MANAGER_TOKEN}, **kwargs)
    if response.status_code == 409:
        raise ValueError(response.json().get("detail", "요청을 받을 수 없습니다"))
    response.raise_for_status()
    return response.json()


def get_health():
    return _request("GET", "/health")


def get_hosts():
    return _request("GET", "/hosts")


def get_host(name, limit=24):
    return _request("GET", f"/hosts/{name}", params={"limit": limit})


def get_metrics(name, hours=24):
    """그래프용 1분 지표. hours: 6 / 24 / 168."""
    return _request("GET", f"/hosts/{name}/metrics", params={"hours": hours})


def check_host(name, load_test=False):
    return _request("POST", f"/hosts/{name}/check", timeout=CHECK_TIMEOUT_SECONDS,
                    params={"load_test": str(load_test).lower()})


def check_all():
    return _request("POST", "/check")


def request_reboot(name, mode):
    """mode: when_idle(job 이 없을 때) / after_jobs(먼저 drain 하고 job 이 끝나면)."""
    return _request("POST", f"/hosts/{name}/reboot", params={"mode": mode})


def cancel_reboot(name):
    return _request("DELETE", f"/hosts/{name}/reboot")


def explain_node_fail(host, at):
    """host 노드에서 at(epoch 초)에 NODE_FAIL 로 끝난 job 의 원인 {cause, summary, evidence}. node_manager 가 안 보는 노드면 404."""
    return _request("GET", "/explain", params={"host": host, "at": at})


def get_reboots(limit=50):
    return _request("GET", "/reboots", params={"limit": limit})
