"""LAIDD 잡을 알아보는 규칙 — 컨트롤러가 `/slurm/jobs`·`/slurm/queue` 에 내려주는 `qos` 로 판정한다.

LAIDD 는 `/slurm/submit_laidd` 로만 제출되고 그 잡의 QOS 는 항상 `laidd` 다(컨트롤러 `LAIDD_QOS_NAME`).
계정은 사용자별이라 Curieus 계정과 섞여 구분되지 않고, 잡 이름(`{model}_{id}`)도 같은 모양이다.
"""

LAIDD_QOS = "laidd"


def is_laidd_job(job) -> bool:
    """`qos` 가 없는 옛 컨트롤러 응답이나 클라우드(VESSL) 항목은 LAIDD 가 아니다."""
    if not job:
        return False
    return str(job.get("qos") or "").strip().lower() == LAIDD_QOS
