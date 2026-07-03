import datetime
import re
from collections import defaultdict


ALL_MODELS = "All"


def safe_text(value, default="-"):
    if value is None or value == "":
        return default
    return str(value)


def cell(value, width, default="-"):
    return f"{safe_text(value, default)[:width]:{width}}"


def source_label(source):
    return "VESSL" if safe_text(source, "slurm").lower() == "vessl" else "SLURM"


def normalized_state(state):
    return safe_text(state, "").upper().strip()


def is_completed(state):
    return normalized_state(state) in ("COMPLETED", "CD")


def is_failed(state):
    return normalized_state(state) in ("FAILED", "F")


def is_cancelled(state):
    state = normalized_state(state)
    return state.startswith("CANCELLED") or state == "CA"


def extract_model(job_name):
    name = safe_text(job_name, "unknown")
    if "_" not in name:
        return name
    return name.rsplit("_", 1)[0] or "unknown"


def model_key(job_name):
    """모델명 추출. 기본은 백엔드 /job-stats와 동일하게 첫 세그먼트(_/- 기준, 소문자).

    단, dynoGen 작업은 변이별로 나눈다. dynoGen 잡 이름은
    `dynogen_<variant>_<job_id>` 형태이고 job_id는 UUID(언더스코어 없음)라,
    마지막 `_<job_id>`만 떼면 `dynogen_<variant>` 전체 변이가 복원된다.
    변이 목록을 하드코딩하지 않으므로 신규 변이도 자동 대응된다.

    batch/extern 같은 SLURM 내부 스텝은 통계에서 제외되므로 None을 반환한다.
    (routers/slurm_statistics.py 참조)
    """
    name = safe_text(job_name, "")
    if not name or name in ("batch", "extern"):
        return None
    first = re.split(r"[_\-]", name)[0].lower()
    if first == "dynogen":
        return name.rsplit("_", 1)[0].lower()
    return first


def job_elapsed_seconds(job):
    """Job 실행시간(초). 백엔드가 주는 elapsed_raw를 우선 사용하고,
    없거나 파싱 실패 시 start/end로 계산해 폴백한다."""
    try:
        seconds = int(job.get("elapsed_raw"))
        if seconds > 0:
            return seconds
    except (TypeError, ValueError):
        pass
    return int(parse_duration_seconds(job.get("start"), job.get("end")))


def parse_duration_seconds(start_str, end_str):
    start_str = safe_text(start_str, "")
    end_str = safe_text(end_str, "")
    if not start_str or not end_str or start_str == "-" or end_str == "-":
        return 0

    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            start = datetime.datetime.strptime(start_str[:19], fmt)
            end = datetime.datetime.strptime(end_str[:19], fmt)
            return max(0, (end - start).total_seconds())
        except ValueError:
            continue
    return 0


def format_seconds(seconds):
    seconds = int(seconds)
    if seconds <= 0:
        return "0:00:00"

    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if days > 0:
        return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours}:{minutes:02d}:{secs:02d}"


def hms_to_seconds(value):
    try:
        hours, minutes, seconds = map(int, safe_text(value, "0:00:00").split(":"))
        return hours * 3600 + minutes * 60 + seconds
    except (TypeError, ValueError):
        return 0


def success_tag(completed, total):
    rate = completed / total if total else 0
    if rate > 0.9:
        return "good"
    if rate > 0.6:
        return "warn"
    return "bad"


def aggregate_jobs_by_account(jobs):
    accounts = defaultdict(lambda: {
        "total": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
        "total_seconds": 0,
        "models": defaultdict(int),
        "nodes": defaultdict(lambda: {"jobs": 0, "seconds": 0}),
    })

    for job in jobs:
        account = safe_text(job.get("account"), "unknown")
        state = job.get("state")
        data = accounts[account]

        data["total"] += 1
        if is_completed(state):
            data["completed"] += 1
        elif is_failed(state):
            data["failed"] += 1
        elif is_cancelled(state):
            data["cancelled"] += 1

        duration = parse_duration_seconds(job.get("start"), job.get("end"))
        data["total_seconds"] += duration
        data["models"][extract_model(job.get("job_name"))] += 1

        node = safe_text(job.get("node_list"))
        data["nodes"][node]["jobs"] += 1
        data["nodes"][node]["seconds"] += duration

    return [
        {
            "account": name,
            "total": data["total"],
            "completed": data["completed"],
            "failed": data["failed"],
            "cancelled": data["cancelled"],
            "total_seconds": data["total_seconds"],
            "models": dict(data["models"]),
            "nodes": {node: dict(info) for node, info in data["nodes"].items()},
        }
        for name, data in accounts.items()
    ]


def aggregate_model_users(jobs, model):
    """특정 모델(백엔드 모델명 기준)에 속한 Job들을 유저별로 집계한다.

    min/max/avg 실행시간은 모두 '완료(COMPLETED)' Job 기준으로 계산한다
    (실행시간이 의미 있는 집합으로 통일; 완료 0건이면 0).
    """
    users = defaultdict(lambda: {
        "total": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
        "completed_seconds": [],
    })

    for job in jobs:
        if model_key(job.get("job_name")) != model:
            continue

        user = safe_text(job.get("user"), "unknown")
        state = job.get("state")
        data = users[user]

        data["total"] += 1
        if is_completed(state):
            data["completed"] += 1
            seconds = job_elapsed_seconds(job)
            if seconds > 0:
                data["completed_seconds"].append(seconds)
        elif is_failed(state):
            data["failed"] += 1
        elif is_cancelled(state):
            data["cancelled"] += 1

    result = []
    for user, data in users.items():
        times = data["completed_seconds"]
        result.append({
            "user": user,
            "total": data["total"],
            "completed": data["completed"],
            "failed": data["failed"],
            "cancelled": data["cancelled"],
            "avg_sec": (sum(times) / len(times)) if times else 0,
            "min_sec": min(times) if times else 0,
            "max_sec": max(times) if times else 0,
        })
    return result


def aggregate_model_stats(jobs):
    """raw jobs를 모델별로 집계한다.

    model_key로 그룹핑하되 dynoGen은 변이별로 나뉜다.
    avg/min/max 실행시간은 모두 '완료(COMPLETED)' Job만 대상으로 계산한다
    (실패/취소 Job은 시간 통계에서 제외; 완료 0건이면 0).
    시간은 초 단위로 반환한다. (유저 드릴다운 aggregate_model_users와 동일 기준)
    """
    stats = defaultdict(lambda: {
        "total": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
        "completed_times": [],
    })

    for job in jobs:
        model = model_key(job.get("job_name"))
        if model is None:
            continue

        state = job.get("state")
        data = stats[model]

        data["total"] += 1
        if is_completed(state):
            data["completed"] += 1
            seconds = job_elapsed_seconds(job)
            if seconds > 0:
                data["completed_times"].append(seconds)
        elif is_failed(state):
            data["failed"] += 1
        elif is_cancelled(state):
            data["cancelled"] += 1

    result = []
    for model, data in stats.items():
        times = data["completed_times"]
        result.append({
            "model": model,
            "total": data["total"],
            "completed": data["completed"],
            "failed": data["failed"],
            "cancelled": data["cancelled"],
            "avg_sec": (sum(times) / len(times)) if times else 0,
            "min_sec": min(times) if times else 0,
            "max_sec": max(times) if times else 0,
        })
    return result
