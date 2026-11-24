"""Job History 의 NODE_FAIL·TIMEOUT 원인 문구."""
from ui.job_failure import NODE_FAIL, TIMEOUT, end_epoch, failure_kind, node_fail_text, timeout_text


def test_failure_kind_covers_long_and_short_state_names():
    assert [failure_kind(s) for s in ("NODE_FAIL", "NF", "TIMEOUT", "to", "FAILED", "COMPLETED", None)] == \
        [NODE_FAIL, NODE_FAIL, TIMEOUT, TIMEOUT, None, None, None]


def test_end_time_and_texts():
    assert end_epoch({"end": "2026-11-23T19:45:49"}) is not None and end_epoch({"end": "-"}) is None
    assert "시간 제한" in timeout_text({"start": "2026-11-23T10:00:00", "end": "2026-11-23T14:00:00"})
    text = node_fail_text({"summary": "노드는 정상이었음 — 컨트롤러가 노드 소식을 못 받음",
                           "evidence": ["11-23 19:45  slurm: IDLE → DOWN"]})
    assert text.splitlines()[0].startswith("노드는 정상") and "  11-23 19:45  slurm: IDLE → DOWN" in text
    assert node_fail_text({}) == "원인을 판단하지 못했습니다."
