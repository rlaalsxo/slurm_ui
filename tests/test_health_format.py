"""Health 탭 문구. 입력은 node_manager /hosts 응답 형태(2026-11-19 실제 첫 점검 결과 기반)."""
from ui.health_format import (detail_lines, display_width, gpu_cell, header_line, host_line, mount_cell, reboot_cell, service_cell,
                              summary_line, uptime_label)

CONNECTS_2 = {
    "name": "connects-2", "address": "192.168.55.2", "role": "slurm_node", "cluster": "test", "status": "fail",
    "since": 1, "last_check_at": 1_763_541_892, "uptime_seconds": 5 * 86400 + 3600, "slurm_state": "MIXED",
    "reboot_allowed": True, "reboot_auto": False, "reboot": None,
    "items": [
        {"name": "mount:/media/connects/PD/docker_images", "status": "ok", "detail": "ok"},
        {"name": "unit:slurmd", "status": "ok", "detail": "active"},
        {"name": "docker", "status": "ok", "detail": "27.3.1"},
        {"name": "gpu0.width", "status": "fail", "detail": "x8 (기대 x16)"},
        {"name": "gpu1", "status": "ok", "detail": "Gen4 x4 (부하 중)"},
    ],
}
CONNECTS_10 = {
    "name": "connects-10", "address": "192.168.55.10", "role": "slurm_node", "cluster": "main", "status": "ok",
    "last_check_at": 1_763_541_900, "uptime_seconds": 3 * 3600, "slurm_state": "IDLE+DRAIN",
    "reboot_allowed": True, "reboot_auto": True,
    "reboot": {"id": 3, "mode": "auto", "state": "verifying", "attempt": 1, "detail": "다시 켜짐 — 검증 대기",
               "created_at": 1_763_541_000, "updated_at": 1_763_541_900},
    "items": [
        {"name": "gpu0", "status": "ok", "detail": "x16 (쉬는 중, 세대는 부하 검사 때)"},
        {"name": "gpu1.gen", "status": "fail", "detail": "부하 중 Gen1 (기대 Gen4)"},
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
    assert (gpu_cell(CONNECTS_10, 0), gpu_cell(CONNECTS_10, 1)) == ("x16", "G1 ✗")
    assert gpu_cell(STORAGE, 0) == "-"


def test_group_cells():
    assert (mount_cell(CONNECTS_2), service_cell(CONNECTS_2)) == ("OK", "OK")
    assert mount_cell(CONNECTS_10) == "✗"
    assert (mount_cell(STORAGE), service_cell(STORAGE)) == ("OK", "OK")


def test_reboot_cell():
    assert reboot_cell(CONNECTS_2) == "수동만"
    assert reboot_cell(CONNECTS_10) == "자동 검증 중"
    assert reboot_cell(STORAGE) == "안 함"


def test_rows_line_up_with_the_header():
    lines = [header_line(), host_line(CONNECTS_2), host_line(CONNECTS_10), host_line(STORAGE)]
    assert len({display_width(line) for line in lines}) == 1  # 한글은 두 칸으로 센다
    assert host_line(CONNECTS_2).startswith("connects-2    노드/test") and host_line(CONNECTS_2).rstrip().endswith("이상")
    assert "저장소·MSA" in host_line(STORAGE)


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
