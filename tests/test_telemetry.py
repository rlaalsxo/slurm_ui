import pytest
from services import api_client


def test_diagnostics_refuses_plaintext_key_transmission(monkeypatch):
    monkeypatch.setenv("LOG_MANAGER_URL_MAIN", "http://remote.example")
    monkeypatch.setenv("LOG_MANAGER_READ_KEY_MAIN", "secret")
    with pytest.raises(ValueError, match="HTTPS"):
        api_client._telemetry_get("/telemetry/nodes")


def test_diagnostics_sends_read_key_without_redirects(monkeypatch):
    monkeypatch.setenv("LOG_MANAGER_URL_MAIN", "https://remote.example")
    monkeypatch.setenv("LOG_MANAGER_READ_KEY_MAIN", "secret")
    calls = []
    monkeypatch.setattr(api_client, "_request_json", lambda *args, **kwargs: calls.append(kwargs) or {})
    api_client._telemetry_get("/telemetry/nodes")
    assert calls[0]["allow_redirects"] is False
    assert calls[0]["headers"] == {"X-API-Key": "secret"}


def test_controller_nodes_remain_available_when_diagnostics_fail(monkeypatch):
    monkeypatch.setattr(api_client, "get_nodes", lambda: [{"name": "node1"}])
    def fail(*args, **kwargs):
        raise ValueError("not configured")
    monkeypatch.setattr(api_client, "_telemetry_get", fail)
    assert api_client.get_nodes_with_telemetry() == [{"name": "node1", "diagnostics": "Diagnostics unavailable"}]
