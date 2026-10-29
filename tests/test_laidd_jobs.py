"""LAIDD 잡 구분과 로그 조회 경로.

- 컨트롤러가 내려주는 `qos == "laidd"` 로 LAIDD 잡을 알아본다(없으면 Curieus 쪽).
- 로그는 두 서버가 같은 계약(`GET /slurm/logs/{id}` → presigned URL)을 쓴다. LAIDD 잡만 LAIDD 서버로,
  읽기 전용 토큰을 `X-API-Key` 로 실어 보내고 리다이렉트는 따라가지 않는다.
"""
import pytest

from services import api_client
from services.laidd import is_laidd_job
from ui.job_utils import matches_service, service_label

LAIDD_JOB = {"job_id": "901", "qos": "laidd", "internal_job_id": "pub1", "account": "acct-1", "source": "slurm"}
CURIEUS_JOB = {"job_id": "902", "qos": "normal", "internal_job_id": "77", "account": "12", "model_id": "boltz", "source": "slurm"}


# ── 판정 ───────────────────────────────────────────────────────

@pytest.mark.parametrize("job", [LAIDD_JOB, {"qos": " LAIDD "}])
def test_jobs_with_the_laidd_qos_are_laidd(job):
    assert is_laidd_job(job)


@pytest.mark.parametrize("job", [CURIEUS_JOB, {}, None, {"qos": None}, {"qos": ""}, {"source": "vessl"}])
def test_everything_else_is_not_laidd(job):
    assert not is_laidd_job(job)


def test_first_column_names_laidd_jobs_and_keeps_the_run_location_for_the_rest():
    assert service_label(LAIDD_JOB) == "LAIDD"
    assert service_label(CURIEUS_JOB) == "SLURM"
    assert service_label({"source": "vessl"}) == "VESSL"


def test_service_filter_splits_the_two_services_and_all_keeps_everything():
    jobs = [LAIDD_JOB, CURIEUS_JOB, {"source": "vessl"}]
    assert [matches_service(j, "All") for j in jobs] == [True, True, True]
    assert [matches_service(j, "LAIDD") for j in jobs] == [True, False, False]
    assert [matches_service(j, "Curieus") for j in jobs] == [False, True, True]


# ── 로그 조회 ─────────────────────────────────────────────────

@pytest.fixture
def calls(monkeypatch):
    """_request_json 과 로그 본문 다운로드를 가로채 어디로 무엇을 보냈는지 기록한다."""
    recorded = {"json": [], "download": []}

    def fake_request_json(method, url, **kwargs):
        recorded["json"].append({"method": method, "url": url, **kwargs})
        return {"url": "https://storage.test/signed"}

    class _Response:
        text = "LOG BODY"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(api_client, "_request_json", fake_request_json)
    monkeypatch.setattr(api_client._session, "get", lambda url, **kw: recorded["download"].append(url) or _Response())
    monkeypatch.setattr(api_client, "SERVER_URL_MAIN", "http://curieus.test")
    api_client.set_env("MAIN")
    monkeypatch.setenv("SERVER_URL_LAIDD_MAIN", "http://laidd.test:8005/")
    monkeypatch.setenv("LAIDD_LOG_TOKEN_MAIN", "ops-token")
    return recorded


def test_a_laidd_job_asks_the_laidd_server_with_the_token_and_its_public_id(calls):
    assert api_client.get_job_log("901", LAIDD_JOB) == "LOG BODY"

    request = calls["json"][0]
    assert request["url"] == "http://laidd.test:8005/slurm/logs/901"
    assert request["params"] == {"job_id": "pub1"}
    assert request["headers"] == {"X-API-Key": "ops-token"}
    assert request["allow_redirects"] is False
    assert calls["download"] == ["https://storage.test/signed"]


def test_a_curieus_job_still_asks_the_curieus_server_without_a_token(calls):
    api_client.get_job_log("902", CURIEUS_JOB)

    request = calls["json"][0]
    assert request["url"] == "http://curieus.test/slurm/logs/902"
    assert request["params"] == {"user_id": "12", "job_id": "77", "model_id": "boltz"}
    # LAIDD 토큰은 절대 안 실린다. 컨트롤러 키도 (설정 안 됐거나 다른 호스트라) 비어 있다.
    assert "X-API-Key" not in request.get("headers", {})


def test_a_laidd_job_never_reaches_the_curieus_server(calls):
    api_client.get_job_log("901", LAIDD_JOB)
    assert all("curieus.test" not in r["url"] for r in calls["json"])


@pytest.mark.parametrize("missing", ["SERVER_URL_LAIDD_MAIN", "LAIDD_LOG_TOKEN_MAIN"])
def test_a_laidd_log_needs_both_the_server_url_and_the_token(calls, monkeypatch, missing):
    monkeypatch.delenv(missing)
    with pytest.raises(ValueError, match="SERVER_URL_LAIDD"):
        api_client.get_job_log("901", LAIDD_JOB)
    assert calls["json"] == []


@pytest.mark.parametrize("url", ["ftp://laidd.test", "http://user:pass@laidd.test", "http://laidd.test?x=1", "http://"])
def test_the_token_is_not_sent_to_a_malformed_server_url(calls, monkeypatch, url):
    monkeypatch.setenv("SERVER_URL_LAIDD_MAIN", url)
    with pytest.raises(ValueError, match="valid configured"):
        api_client.get_job_log("901", LAIDD_JOB)
    assert calls["json"] == []
