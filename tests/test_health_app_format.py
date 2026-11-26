"""Health 문구. 입력은 node_manager /hosts 응답 형태(2026-11-19 실제 첫 점검 결과 기반)."""
from health_app.format import (COLUMNS, detail_lines, gpu_cell, host_cells, mount_cell, reboot_cell, service_cell, summary_line,
                               uptime_label)

CONNECTS_2 = {
    "name": "connects-2", "address": "192.168.55.2", "role": "slurm_node", "cluster": "test", "status": "fail",
    "since": 1, "last_check_at": 1_763_541_892, "uptime_seconds": 5 * 86400 + 3600, "slurm_state": "MIXED",
    "reboot_allowed": True, "reboot_auto": False, "reboot": None,
    "items": [
        {"name": "mount:/media/connects/PD/docker_images", "status": "ok", "detail": "ok"},
        {"name": "unit:slurmd", "status": "ok", "detail": "active"},
        {"name": "docker", "status": "ok", "detail": "27.3.1"},
        {"name": "gpu0.width", "status": "fail", "detail": "x8 (기대 x16)"},
        {"name": "gpu1", "status": "ok", "detail": "Gen4 x4 (부하 검사, 평소 Gen1)"},
    ],
}
CONNECTS_10 = {
    "name": "connects-10", "address": "192.168.55.10", "role": "slurm_node", "cluster": "main", "status": "ok",
    "last_check_at": 1_763_541_900, "uptime_seconds": 3 * 3600, "slurm_state": "IDLE+DRAIN",
    "reboot_allowed": True, "reboot_auto": True,
    "reboot": {"id": 3, "mode": "auto", "state": "verifying", "attempt": 1, "detail": "다시 켜짐 — 검증 대기",
               "created_at": 1_763_541_000, "updated_at": 1_763_541_900},
    "items": [
        {"name": "gpu0", "status": "ok", "detail": "x16 (세대 미확인 — 부하 검사 전)"},
        {"name": "gpu1.gen", "status": "fail", "detail": "부하 검사 Gen1 (기대 Gen4, 평소 Gen1)"},
        {"name": "mount:/media/connects/PD", "status": "warn", "detail": "점검 계정(nodeops)이 경로에 못 들어감"},
    ],
}
STORAGE = {
    "name": "storage-37", "address": "192.168.55.37", "role": "storage", "cluster": None, "status": "ok",
    "last_check_at": None, "uptime_seconds": None, "slurm_state": None, "reboot_allowed": False, "reboot_auto": False,
    "reboot": None,
    "items": [{"name": "raid:md0", "status": "ok", "detail": "raid5 4/4 active"},
              {"name": "nfs.exports", "status": "ok", "detail": "모두 내보내는 중"},
              {"name": "container:msa_server", "status": "ok", "detail": "Up 7 hours"}],
}


def test_gpu_cells_show_link_or_the_problem():
    assert (gpu_cell(CONNECTS_2, 0), gpu_cell(CONNECTS_2, 1)) == ("x8 ✗", "G4 x4")
    assert (gpu_cell(CONNECTS_10, 0), gpu_cell(CONNECTS_10, 1)) == ("G? x16", "G1 ✗")
    assert gpu_cell(STORAGE, 0) == "-"


def test_group_cells():
    assert (mount_cell(CONNECTS_2), service_cell(CONNECTS_2)) == ("OK", "OK")
    assert mount_cell(CONNECTS_10) == "✗"
    assert (mount_cell(STORAGE), service_cell(STORAGE)) == ("OK", "OK")


def test_reboot_cell():
    assert reboot_cell(CONNECTS_2) == "수동만"
    assert reboot_cell(CONNECTS_10) == "자동 검증 중"
    assert reboot_cell(STORAGE) == "안 함"


def test_row_has_one_value_per_column():
    rows = [host_cells(CONNECTS_2), host_cells(CONNECTS_10), host_cells(STORAGE)]
    assert {len(row) for row in rows} == {len(COLUMNS)}
    assert host_cells(CONNECTS_2)[:2] == ("connects-2", "노드/test") and host_cells(CONNECTS_2)[-1] == "이상"
    assert host_cells(STORAGE)[1] == "저장소·MSA" and host_cells(STORAGE)[2] == "-"  # Slurm 없음은 빈칸 대신 '-'


def test_summary_counts_and_reboot_mode():
    line = summary_line([CONNECTS_2, CONNECTS_10, STORAGE], {"auto_reboot": True, "reboot_dry_run": True})
    assert line.startswith("전체 3대  정상 2 · 주의 0 · 이상 1") and "자동 재부팅: DRY_RUN(기록만)" in line
    assert "자동 재부팅: 꺼짐" in summary_line([], {"auto_reboot": False})


def test_uptime_label():
    assert (uptime_label(None), uptime_label(3 * 3600), uptime_label(int(3.25 * 86400))) == ("-", "3h", "3.2d")


def test_detail_lists_items_expectations_and_history():
    detail = {**CONNECTS_2,
              "expected_gpus": [{"index": 0, "model": "RTX 3080 Ti", "width": 16, "gen": 4}],
              "history": [{"at": 1_763_541_892, "status": "fail", "items": []}],
              "reboots": [{"id": 1, "mode": "when_idle", "state": "failed", "attempt": 2, "created_at": 1_763_540_000,
                           "updated_at": 1, "detail": "재부팅 후에도 이상"}]}
    lines = detail_lines(detail)
    texts = [text for text, _ in lines]
    assert lines[0] == ("connects-2 (192.168.55.2)  노드/test", "title")
    assert any(text.startswith("  ✗ gpu0.width") and "x8 (기대 x16)" in text for text in texts)
    assert any("GPU0: RTX 3080 Ti  x16  Gen4" in text for text in texts)
    assert any("수동" in text and "실패" in text and "재부팅 후에도 이상" in text for text in texts)
    assert dict(lines)[next(t for t in texts if "gpu0.width" in t)] == "fail"


def test_detail_shows_specs_with_temperature_limits():
    """2026-11-26 실측: connects-3 (ASUS, 7950X, 3080 Ti 300W 상한), 37번(듀얼 Xeon, GPU 온도 안 봄)."""
    from health_app.format import spec_lines
    connects_3 = {"temps": {"cpu_max": 95.0, "gpu_max": 93.0, "warn_margin": 5}, "latest_probe": {"hardware": {
        "board_vendor": "ASUSTeK COMPUTER INC.", "board_name": "PRIME X870-P WIFI",
        "cpu": {"model": "AMD Ryzen 9 7950X 16-Core Processor", "sockets": 1, "cores": 16, "threads": 32},
        "mem_total_kb": 65617772,
        "gpus": [{"index": 0, "name": "NVIDIA GeForce RTX 3080 Ti", "memory_mib": 12288, "power_limit_w": 300.0, "power_default_w": 350.0}]}}}
    texts = [text for text, _ in spec_lines(connects_3)]
    assert texts[1] == "[사양]" and texts[2] == "  보드  ASUS PRIME X870-P WIFI"
    assert "AMD Ryzen 9 7950X 16-Core Processor · 16코어 32스레드" in texts[3] and texts[3].endswith("온도 한계 95°C (주의 90)")
    assert texts[4] == "  RAM   62.6GB (OS 기준)"
    assert "RTX 3080 Ti 12GB · 전력 상한 300W (기본 350W)" in texts[5] and texts[5].endswith("온도 한계 93°C (주의 88)")
    storage = {"temps": {"cpu_max": 104.0, "gpu_max": None}, "latest_probe": {"hardware": {
        "board_vendor": "Supermicro", "board_name": "X11DPi-NT",
        "cpu": {"model": "Intel(R) Xeon(R) Gold 6154 CPU @ 3.00GHz", "sockets": 2, "cores": 36, "threads": 72},
        "gpus": [{"index": 0, "name": "NVIDIA GeForce GTX 1080", "memory_mib": 8192, "power_limit_w": 250.0, "power_default_w": 250.0}]}}}
    texts = [text for text, _ in spec_lines(storage)]
    assert "Intel Xeon Gold 6154 CPU @ 3.00GHz · 2소켓 · 36코어 72스레드" in texts[3]
    assert "GTX 1080 8GB · 전력 250W" in texts[4] and texts[4].endswith("온도 감시 안 함")
    assert spec_lines({})[-1] == ("  다음 정기 점검 뒤에 표시됩니다", "default")


def test_detail_shows_boot_history_and_recent_events():
    from health_app.format import boot_lines, event_lines
    boots = [{"boot_id": "c", "up_at": 1_763_854_060, "down_at": 1_763_853_520, "cause": "abrupt",
              "before_stop": "꺼지기 직전 10분: GPU 전력 합계 최대 681W(00:23)"},
             {"boot_id": "b", "up_at": 1_763_600_000, "down_at": 1_763_599_970, "cause": "clean", "before_stop": None},
             {"boot_id": "a", "up_at": 1_763_000_000, "down_at": None, "cause": "first"}]
    lines = boot_lines(boots)
    assert lines[1][1] == "title" and "갑자기 꺼짐" in lines[2][0] and lines[2][1] == "warn" and "직전 기록" in lines[2][0]
    assert lines[3] == ("      └ 꺼지기 직전 10분: GPU 전력 합계 최대 681W(00:23)", "warn")
    assert "정상 재부팅" in lines[4][0] and lines[4][1] == "default"
    assert lines[5][1] == "default" and "직전 기록" not in lines[5][0] and len(lines) == 6
    events = event_lines([{"at": 1_763_854_000, "kind": "unreachable", "detail": "37번에서 접속 안 됨: timeout"},
                          {"at": 1_763_854_100, "kind": "slurm", "detail": "IDLE → DOWN+DRAIN (Not responding)"}])
    assert [tag for _, tag in events[2:]] == ["warn", "default"] and "접속 끊김" in events[2][0]
    assert boot_lines([]) == [] and event_lines(None) == []
    temps = event_lines([{"at": 1_763_854_100, "kind": "temp", "detail": "GPU0 한계 온도 도달 95°C (한계 93°C)"},
                         {"at": 1_763_854_200, "kind": "temp", "detail": "GPU0 온도 주의: 10분 연속 89°C 이상 (주의 88 · 한계 93°C)"},
                         {"at": 1_763_854_800, "kind": "temp", "detail": "GPU0 온도 정상으로 내려옴 (지금 80°C)"}])
    assert [tag for _, tag in temps[2:]] == ["warn", "warn", "default"] and "온도" in temps[4][0]
