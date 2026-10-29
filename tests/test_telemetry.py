import pytest
from services import api_client
from services.diagnostics_summary import format_attempts

CA = "-----BEGIN CERTIFICATE-----\nPRIVATE-CA\n-----END CERTIFICATE-----\n"


@pytest.fixture
def ca_dirs(monkeypatch, tmp_path):
    monkeypatch.delenv("CURIEUS_CA_FILE", raising=False)
    monkeypatch.setattr(api_client, "BASE_DIR", str(tmp_path / "app"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    (tmp_path / "app").mkdir()
    return tmp_path


def test_no_ca_keeps_requests_default(ca_dirs):
    assert api_client.ca_bundle() is True


def test_bundled_ca_is_merged_into_user_app_data(ca_dirs):
    (ca_dirs / "app" / "ca.crt").write_text(CA, encoding="ascii")
    path = api_client.ca_bundle()
    assert path.startswith(str(ca_dirs / "appdata"))  # 공용 임시 폴더가 아니다
    bundle = open(path, encoding="ascii").read()
    assert "PRIVATE-CA" in bundle
    assert bundle.count("BEGIN CERTIFICATE") > 10  # certifi public roots kept for LAIDD/NCP


def test_configured_missing_ca_is_not_silently_ignored(monkeypatch, ca_dirs):
    missing = ca_dirs / "nope.crt"
    monkeypatch.setenv("CURIEUS_CA_FILE", str(missing))
    assert api_client.ca_bundle() == str(missing)


def test_unreadable_ca_does_not_crash_startup(monkeypatch, ca_dirs):
    bad = ca_dirs / "bad.crt"
    bad.write_bytes("한글 is not ascii".encode("utf-8"))
    monkeypatch.setenv("CURIEUS_CA_FILE", str(bad))
    assert api_client.ca_bundle() == str(bad)


def test_presigned_log_download_verifies_tls_by_default(monkeypatch):
    import importlib
    monkeypatch.delenv("VERIFY_PRESIGNED_URL", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    assert importlib.reload(api_client).VERIFY_PRESIGNED_URL is True


def test_summary_shows_peaks_codes_and_kernel_details():
    payload = {"raw_retention_days": 30, "attempts": [{
        "node": "connects-10", "collection_status": "interrupted", "exit_code": None,
        "executor": "slurm", "executor_job_id": "36660", "started_at": "2026-10-29T01:00:00",
        "summary": {
            "devices": {"GPU-abcdef123456": {"name": "RTX 3080 Ti"}, "cpu:hwmon0:temp1": {"name": "coretemp Package"}},
            "peaks": {"GPU-abcdef123456:temperature_c": 87.0, "GPU-abcdef123456:utilization_pct": 100,
                      "GPU-abcdef123456:memory_used_mib": 11800, "GPU-abcdef123456:memory_total_mib": 12288,
                      "GPU-abcdef123456:thermal_throttle": 1.0, "cpu:hwmon0:temp1:temperature_c": 78.5},
            "warnings": ["thermal_warning"],
            "events": [{"timestamp": "2026-10-29T01:30:00+00:00", "code": "nvidia_xid",
                        "detail": {"xid": 79, "pci_bus_id": "0000:01:00", "gpu_uuid": "GPU-abcdef123456"}},
                       {"timestamp": "2026-10-29T01:30:01+00:00", "code": "pcie_aer_error",
                        "detail": {"severity": "Uncorrected", "pci_bus_id": "0000:01:00.0"}}],
        }}]}
    text = format_attempts(payload)
    assert "node=connects-10" in text and "status=interrupted" in text
    assert "peak 87.0C" in text and "THROTTLED" in text and "VRAM 11800/12288 MiB" in text
    assert "coretemp Package: peak 78.5C" in text
    assert "nvidia_xid x1" in text and "xid=79" in text and "severity=Uncorrected" in text
    assert "summaries are permanent" in text


def test_summary_without_attempts_points_to_registration():
    assert "No execution attempts" in format_attempts({"attempts": []})


@pytest.mark.parametrize("url", ["ftp://remote.example", "http://user:pass@remote.example", "http://remote.example?token=x", "http://remote.example#fragment", "http://"])
def test_diagnostics_rejects_invalid_server_urls(monkeypatch, url):
    monkeypatch.setenv("LOG_MANAGER_URL_MAIN", url)
    monkeypatch.setenv("LOG_MANAGER_READ_KEY_MAIN", "secret")
    with pytest.raises(ValueError, match="valid configured"):
        api_client._telemetry_get("/telemetry/nodes")


@pytest.mark.parametrize("url", ["http://remote.example:8501", "https://remote.example"])
def test_diagnostics_sends_read_key_without_redirects(monkeypatch, url):
    monkeypatch.setenv("LOG_MANAGER_URL_MAIN", url)
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


@pytest.mark.parametrize("url,warn", [("http://106.248.49.108:8501", True), ("https://106.248.49.108:8501", False),
                                      ("http://127.0.0.1:8501", False)])
def test_remote_http_shows_insecure_warning(monkeypatch, url, warn):
    monkeypatch.setenv("LOG_MANAGER_URL_MAIN", url)
    monkeypatch.setattr(api_client, "_current_env", "MAIN")
    assert bool(api_client.telemetry_transport_warning()) is warn


def test_nodes_tab_marks_insecure_transport(monkeypatch):
    monkeypatch.setenv("LOG_MANAGER_URL_MAIN", "http://remote.example:8501")
    monkeypatch.setattr(api_client, "_current_env", "MAIN")
    monkeypatch.setattr(api_client, "get_nodes", lambda: [{"name": "node1"}])
    monkeypatch.setattr(api_client, "_telemetry_get", lambda *_a, **_k: {"nodes": [
        {"node": "node1", "source": "host", "stale": False, "timestamp": "t",
         "devices": [{"uuid": "GPU-1", "metrics": {"temperature_c": 60}}]}]})
    assert api_client.get_nodes_with_telemetry()[0]["diagnostics"].startswith("INSECURE HTTP")


def test_controller_calls_send_api_key_without_redirects(monkeypatch):
    monkeypatch.setattr(api_client, "_current_env", "TEST")
    monkeypatch.setenv("SLURM_CONTROLLER_API_KEY_TEST", "ui-key")
    calls = []
    monkeypatch.setattr(api_client, "_request_json", lambda *args, **kwargs: calls.append(kwargs) or [])
    api_client.get_nodes()
    api_client.drain_node("connects-10")
    assert all(call["headers"] == {"X-API-Key": "ui-key"} for call in calls)
    assert all(call["allow_redirects"] is False for call in calls)


def test_controller_key_is_not_sent_to_other_hosts(monkeypatch):
    monkeypatch.setattr(api_client, "_current_env", "TEST")
    monkeypatch.setattr(api_client, "URL_TEST", "https://controller:8500")
    monkeypatch.setenv("SLURM_CONTROLLER_API_KEY_TEST", "ui-key")
    assert api_client._controller_headers("https://controller:8500") == {"X-API-Key": "ui-key"}
    assert api_client._controller_headers("https://other-backend") == {}


def test_no_controller_key_sends_no_header(monkeypatch):
    monkeypatch.setattr(api_client, "_current_env", "TEST")
    monkeypatch.delenv("SLURM_CONTROLLER_API_KEY_TEST", raising=False)
    assert api_client._controller_headers() == {}
