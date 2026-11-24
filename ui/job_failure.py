"""Job History 에서 NODE_FAIL·TIMEOUT 이 왜 났는지 보여 줄 문구 — 화면 코드 없는 순수 함수."""
import datetime

from ui.job_utils import format_seconds, job_elapsed_seconds, normalized_state, safe_text

NODE_FAIL, TIMEOUT = "node_fail", "timeout"

TIMEOUT_TEXT = (
    "Slurm 시간 제한(TimeLimit)을 넘겨 종료됐습니다.\n"
    "플랫폼 job 은 한 번 자동으로 다시 돌고, 또 넘기면 에러로 끝납니다(서버 TIMEOUT 재시도).\n"
    "반복되면 입력 크기나 모델의 시간 제한 설정을 확인하세요."
)


def failure_kind(state):
    state = normalized_state(state)
    if state.startswith("NODE_FAIL") or state == "NF":
        return NODE_FAIL
    if state.startswith("TIMEOUT") or state == "TO":
        return TIMEOUT
    return None


def end_epoch(job):
    """'2026-11-23T19:45:49'(컨트롤러 시각, 한국 시간) → epoch 초. 노트북 시간대가 한국 시간이라는 전제."""
    text = safe_text(job.get("end"), "")
    try:
        return datetime.datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def timeout_text(job):
    return f"실행 시간 {format_seconds(job_elapsed_seconds(job))}\n\n{TIMEOUT_TEXT}"


def node_fail_text(answer):
    """node_manager /explain 응답 → 보여 줄 글."""
    lines = [answer.get("summary") or "원인을 판단하지 못했습니다."]
    evidence = answer.get("evidence") or []
    if evidence:
        lines += ["", "같은 시간대 노드 기록:", *(f"  {line}" for line in evidence)]
    return "\n".join(lines)
