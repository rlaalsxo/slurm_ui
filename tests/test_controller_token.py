"""컨트롤러가 CONTROLLER_API_TOKEN 을 켜면 SlurmUI 의 컨트롤러 호출도 같은 값을 X-Controller-Token 으로 낸다(11-06).

로그 조회는 SERVER_URL 로 간다. 운영 .env 는 SERVER_URL 이 컨트롤러 자신이라(컨트롤러가 서버로 넘겨 준다)
그때만 토큰을 싣는다 — 빠뜨려서 로그가 전부 401 이 났다(11-07). 다른 서버로는 싣지 않는다.
"""
import pytest

from services import api_client


class Recorder:
    def __init__(self):
        self.calls = []

    def request(self, method, url, timeout=10, **kwargs):
        self.calls.append((method, url, kwargs.get("headers") or {}))

        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return {}

        return Response()


def test_controller_calls_carry_the_token(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(api_client, "_session", recorder)
    monkeypatch.setattr(api_client, "CONTROLLER_TOKEN", "tok")

    api_client.get_nodes()
    api_client.drain_node("connects-5")
    api_client.resume_node("connects-5")

    assert recorder.calls and all(headers.get("X-Controller-Token") == "tok" for _, _, headers in recorder.calls)
    assert all("/slurm/" in url for _, url, _ in recorder.calls)


def test_no_token_configured_sends_no_header(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(api_client, "_session", recorder)
    monkeypatch.setattr(api_client, "CONTROLLER_TOKEN", None)

    api_client.drain_node("connects-5")

    assert "X-Controller-Token" not in recorder.calls[0][2]


@pytest.fixture
def log_requests(monkeypatch):
    """로그 presigned URL 요청만 기록한다. 컨트롤러 주소는 운영 .env 모양(같은 호스트·포트)으로 둔다."""
    recorded = []

    def fake_request_json(method, url, **kwargs):
        recorded.append({"url": url, **kwargs})
        return {"url": "https://storage.test/signed"}

    monkeypatch.setattr(api_client, "_request_json", fake_request_json)
    monkeypatch.setattr(api_client, "URL_MAIN", "http://223.130.157.152:8500")
    monkeypatch.setattr(api_client, "CONTROLLER_TOKEN", "tok")
    api_client.set_env("MAIN")
    return recorded


def test_log_lookup_through_the_controller_carries_the_token(monkeypatch, log_requests):
    monkeypatch.setattr(api_client, "SERVER_URL_MAIN", "http://223.130.157.152:8500")

    api_client._presigned_log_url("41300", {"user_id": "481", "internal_job_id": "19972", "model_id": "bioemu"})

    request = log_requests[0]
    assert request["url"] == "http://223.130.157.152:8500/slurm/logs/41300"
    assert request["headers"] == {"X-Controller-Token": "tok"}
    assert request["allow_redirects"] is False


@pytest.mark.parametrize("server_url", ["http://curieus.test", "http://223.130.157.152:8000", "https://223.130.157.152:8500"])
def test_log_lookup_to_another_server_does_not_carry_the_token(monkeypatch, log_requests, server_url):
    monkeypatch.setattr(api_client, "SERVER_URL_MAIN", server_url)

    api_client._presigned_log_url("41300", {"user_id": "481"})

    assert "headers" not in log_requests[0]


def test_log_lookup_without_a_token_configured_sends_no_header(monkeypatch, log_requests):
    monkeypatch.setattr(api_client, "SERVER_URL_MAIN", "http://223.130.157.152:8500")
    monkeypatch.setattr(api_client, "CONTROLLER_TOKEN", None)

    api_client._presigned_log_url("41300", {"user_id": "481"})

    assert "headers" not in log_requests[0]
