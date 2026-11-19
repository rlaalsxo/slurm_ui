"""Health 탭 표·상세 문구 — node_manager 응답(/hosts, /hosts/{name})을 사람이 읽는 줄로 바꾼다. 화면 코드 없는 순수 함수."""
import datetime
import unicodedata

STATUS_LABELS = {"ok": "정상", "warn": "주의", "fail": "이상", None: "미점검"}
REBOOT_STATE_LABELS = {
    "waiting": "job 대기", "draining": "drain·job 대기", "rebooting": "재부팅 중", "verifying": "검증 중",
    "done": "완료", "failed": "실패", "cancelled": "취소",
}
REBOOT_MODE_LABELS = {"auto": "자동", "when_idle": "수동", "after_jobs": "수동(job 후)"}
ROLE_LABELS = {"slurm_node": "노드", "storage": "저장소·MSA"}
COLUMNS = (("이름", 13), ("역할", 15), ("Slurm", 12), ("가동", 6), ("GPU0", 10), ("GPU1", 10),
           ("마운트", 8), ("서비스", 8), ("재부팅", 16), ("상태", 6))


def display_width(text):
    """고정폭 글꼴에서 한글·전각 문자는 두 칸을 차지한다 — 글자 수로 맞추면 한글이 든 칸부터 표가 어긋난다."""
    return sum(2 if unicodedata.east_asian_width(char) in ("W", "F") else 1 for char in text)


def _cell(text, width):
    text = str(text if text not in (None, "") else "-")
    while display_width(text) > width:
        text = text[:-1]
    return text + " " * (width - display_width(text))


def header_line():
    return " ".join(_cell(name, width) for name, width in COLUMNS)


def uptime_label(seconds):
    if seconds is None:
        return "-"
    days = seconds / 86400
    return f"{days:.1f}d" if days >= 1 else f"{seconds // 3600}h"


def _items(host, prefix):
    return [item for item in host.get("items", []) if item["name"] == prefix or item["name"].startswith(prefix + ".")]


def _gpu_problem(item):
    """칸이 좁아 문제 종류만: 'x8 ✗', 'G1 ✗', '모델 ✗', '없음 ✗', 부하 검사 실패는 '검사실패 !'."""
    mark = "✗" if item["status"] == "fail" else "!"
    kind = item["name"].rsplit(".", 1)[-1] if "." in item["name"] else "missing"
    if kind == "width":
        return f"{item['detail'].split()[0]} {mark}"
    if kind == "gen":
        gen = next((word for word in item["detail"].split() if word.startswith("Gen")), None)
        return f"{gen.replace('Gen', 'G')} {mark}" if gen else f"검사실패 {mark}"
    return {"model": f"모델 {mark}", "missing": f"없음 {mark}"}.get(kind, mark)


def gpu_cell(host, index):
    """정상이면 '세대 x폭'(부하 검사 전이면 'x폭'), 문제면 첫 문제 + ✗."""
    items = _items(host, f"gpu{index}")
    if not items:
        return "-"
    problem = next((item for item in items if item["status"] != "ok"), None)
    if problem:
        return _gpu_problem(problem)
    detail = items[0]["detail"]
    words = detail.split()
    return f"{words[0].replace('Gen', 'G')} {words[1]}" if detail.startswith("Gen") else words[0]


def _group_cell(host, prefixes):
    items = [item for item in host.get("items", []) if item["name"].startswith(prefixes)]
    if not items:
        return "-"
    return "OK" if all(item["status"] == "ok" for item in items) else "✗"


def mount_cell(host):
    return _group_cell(host, ("mount:", "nfs.", "raid"))


def service_cell(host):
    return _group_cell(host, ("unit:", "docker", "nvidia_runtime", "container:", "http:"))


def reboot_cell(host):
    reboot = host.get("reboot")
    if reboot:
        return f"{REBOOT_MODE_LABELS.get(reboot['mode'], reboot['mode'])} {REBOOT_STATE_LABELS.get(reboot['state'], reboot['state'])}"
    if not host.get("reboot_allowed"):
        return "안 함"
    return "자동" if host.get("reboot_auto") else "수동만"


def host_line(host):
    role = ROLE_LABELS.get(host.get("role"), host.get("role"))
    cluster = f"/{host['cluster']}" if host.get("cluster") else ""
    values = (host["name"], f"{role}{cluster}", host.get("slurm_state"), uptime_label(host.get("uptime_seconds")),
              gpu_cell(host, 0), gpu_cell(host, 1), mount_cell(host), service_cell(host), reboot_cell(host),
              STATUS_LABELS.get(host.get("status"), host.get("status")))
    return " ".join(_cell(value, width) for value, (_, width) in zip(values, COLUMNS))


def summary_line(hosts, health=None):
    counts = {key: sum(1 for h in hosts if h.get("status") == key) for key in ("ok", "warn", "fail")}
    checked = [h["last_check_at"] for h in hosts if h.get("last_check_at")]
    last = time_label(max(checked)) if checked else "-"
    reboot_mode = ""
    if health is not None:
        reboot_mode = "  자동 재부팅: " + ("꺼짐" if not health.get("auto_reboot") else
                                         "DRY_RUN(기록만)" if health.get("reboot_dry_run") else "켜짐")
    return (f"전체 {len(hosts)}대  정상 {counts['ok']} · 주의 {counts['warn']} · 이상 {counts['fail']}"
            f"   마지막 점검 {last}{reboot_mode}")


def time_label(epoch, with_date=False):
    if not epoch:
        return "-"
    moment = datetime.datetime.fromtimestamp(epoch)
    return moment.strftime("%m-%d %H:%M" if with_date else "%H:%M")


def detail_lines(detail):
    """선택한 호스트 상세 → [(문구, 태그)]. 태그는 ok/warn/fail/title/default."""
    status = detail.get("status")
    lines = [
        (f"{detail['name']} ({detail['address']})  {ROLE_LABELS.get(detail['role'], detail['role'])}"
         f"{'/' + detail['cluster'] if detail.get('cluster') else ''}", "title"),
        (f"상태 {STATUS_LABELS.get(status, status)} (그대로 {time_label(detail.get('since'), True)}부터)"
         f"   마지막 점검 {time_label(detail.get('last_check_at'), True)}   가동 {uptime_label(detail.get('uptime_seconds'))}"
         f"   Slurm {detail.get('slurm_state') or '-'}", status or "default"),
        (f"재부팅: {reboot_cell(detail)}" + (f" — {detail['reboot']['detail']}" if detail.get("reboot") else ""), "default"),
        ("", "default"),
        ("[항목]", "title"),
    ]
    marks = {"ok": "✓", "warn": "!", "fail": "✗"}
    for item in detail.get("items", []):
        lines.append((f"  {marks.get(item['status'], '?')} {item['name']:<32} {item['detail']}", item["status"]))
    if detail.get("expected_gpus"):
        lines += [("", "default"), ("[기대 GPU — 레인 폭은 꽂힌 슬롯 기준]", "title")]
        for gpu in detail["expected_gpus"]:
            lines.append((f"  GPU{gpu['index']}: {gpu['model']}  x{gpu['width']}  Gen{gpu['gen']}", "default"))
    if detail.get("history"):
        recent = "  ".join(f"{time_label(row['at'])} {STATUS_LABELS.get(row['status'], row['status'])}"
                           for row in detail["history"][:12])
        lines += [("", "default"), ("[최근 점검]", "title"), (f"  {recent}", "default")]
    if detail.get("reboots"):
        lines += [("", "default"), ("[재부팅 이력]", "title")]
        tags = {"done": "ok", "failed": "fail", "cancelled": "default"}
        for reboot in detail["reboots"]:
            lines.append((f"  {time_label(reboot['created_at'], True)}  {REBOOT_MODE_LABELS.get(reboot['mode'], reboot['mode']):<8}"
                          f" {REBOOT_STATE_LABELS.get(reboot['state'], reboot['state']):<10} {reboot['detail']}",
                          tags.get(reboot["state"], "warn")))
    return lines
