import datetime
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
