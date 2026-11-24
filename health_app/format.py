"""Health 표·상세 문구 — node_manager 응답(/hosts, /hosts/{name})을 사람이 읽는 값으로 바꾼다. 화면 코드 없는 순수 함수."""
import datetime
import re

STATUS_LABELS = {"ok": "정상", "warn": "주의", "fail": "이상", None: "미점검"}
REBOOT_STATE_LABELS = {
    "waiting": "job 대기", "draining": "drain·job 대기", "rebooting": "재부팅 중", "verifying": "검증 중",
    "done": "완료", "failed": "실패", "cancelled": "취소",
}
REBOOT_MODE_LABELS = {"auto": "자동", "when_idle": "수동", "after_jobs": "수동(job 후)"}
ROLE_LABELS = {"slurm_node": "노드", "storage": "저장소·MSA"}
BOOT_CAUSE_LABELS = {"node_manager": "node_manager 재부팅", "clean": "정상 재부팅(사람·OS 업데이트)",
                     "abrupt": "갑자기 꺼짐(전원·하드웨어·커널)", "unexpected": "예고 없음(종료 기록 확인 불가)", "first": ""}
BOOT_WARN_CAUSES = {"abrupt", "unexpected"}
EVENT_KIND_LABELS = {"boot": "부팅", "slurm": "Slurm", "unreachable": "접속 끊김", "reachable": "접속 회복"}
EVENT_WARN_KINDS = {"unreachable"}
MAX_BOOT_LINES, MAX_EVENT_LINES = 10, 15
COLUMNS = ("이름", "역할", "Slurm", "가동", "GPU0 링크", "GPU1 링크", "GPU 온도", "GPU 사용", "CPU", "부하", "RAM",
           "마운트", "서비스", "재부팅", "상태")
NUMERIC_COLUMNS = {"GPU 온도", "GPU 사용", "CPU", "부하", "RAM"}
STATUS_ORDER = {"fail": 0, "warn": 1, "ok": 2}   # 상태로 정렬하면 나쁜 것부터


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
    # 세대는 부하 중(부하 검사·job 사용 중)에만 안다. 아직 모르면 'G?' 로 비워 두지 않는다.
    return f"{words[0].replace('Gen', 'G')} {words[1]}" if detail.startswith("Gen") else f"G? {words[0]}"


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


def _pair(values, unit):
    """GPU 두 장 값을 '71°/64°' 한 칸에. 값이 없으면 '-'."""
    shown = [f"{value:.0f}{unit}" for value in values if value is not None]
    return "/".join(shown) if shown else "-"


def metric_cells(host):
    """1분 수집 지표의 지금 값: GPU 온도, GPU 사용률, CPU 온도, 부하(코어당 %), RAM. 5분 넘게 없으면 '-'."""
    metrics = host.get("metrics") or {}
    gpus = metrics.get("gpus") or []
    load = metrics.get("load1")
    cpus = metrics.get("cpus")
    load_pct = f"{load / cpus * 100:.0f}%" if load is not None and cpus else "-"
    cpu_temp = metrics.get("cpu_temp")
    ram = metrics.get("mem_pct")
    return (_pair([gpu.get("temp") for gpu in gpus], "°"), _pair([gpu.get("util") for gpu in gpus], "%"),
            f"{cpu_temp:.0f}°" if cpu_temp is not None else "-", load_pct, f"{ram:.0f}%" if ram is not None else "-")


def host_cells(host):
    """표 한 줄 — COLUMNS 순서. 빈 값은 '-'."""
    role = ROLE_LABELS.get(host.get("role"), host.get("role"))
    cluster = f"/{host['cluster']}" if host.get("cluster") else ""
    values = (host["name"], f"{role}{cluster}", host.get("slurm_state"), uptime_label(host.get("uptime_seconds")),
              gpu_cell(host, 0), gpu_cell(host, 1), *metric_cells(host), mount_cell(host), service_cell(host), reboot_cell(host),
              STATUS_LABELS.get(host.get("status"), host.get("status")))
    return tuple("-" if value in (None, "") else str(value) for value in values)


def sort_key(column, host, text):
    """열 정렬 기준. 숫자 칸은 숫자로('8.7d' 와 '23h' 를 글자로 비교하면 어긋난다), 이름은 connects-2 < connects-10."""
    if column == "가동":
        return host.get("uptime_seconds") or -1
    if column == "상태":
        return STATUS_ORDER.get(host.get("status"), len(STATUS_ORDER))
    if column in NUMERIC_COLUMNS:
        numbers = [float(number) for number in re.findall(r"\d+(?:\.\d+)?", text)]
        return max(numbers) if numbers else -1
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text))


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


def boot_lines(boots):
    """[부팅 이력] — 최근 순. 정상 종료 기록(last -x)으로 '사람·OS 가 재부팅'과 '갑자기 꺼짐'을 나눈다.
    우리가 하지 않은 재부팅엔 꺼지기 직전 10분의 GPU 전력·온도 요약이 한 줄 더 붙는다."""
    if not boots:
        return []
    lines = [("", "default"), ("[부팅 이력 — 최근 순, 직전 기록 = 그 전 부팅이 멈춘 무렵]", "title")]
    for boot in boots[:MAX_BOOT_LINES]:
        tag = "warn" if boot["cause"] in BOOT_WARN_CAUSES else "default"
        before = f"직전 기록 {time_label(boot['down_at'], True)}" if boot.get("down_at") else ""
        lines.append((f"  {time_label(boot['up_at'], True)} 켜짐   {before:<20} {BOOT_CAUSE_LABELS.get(boot['cause'], boot['cause'])}",
                      tag))
        if boot.get("before_stop"):
            lines.append((f"      └ {boot['before_stop']}", tag))
    return lines


def event_lines(events):
    """[최근 사건] — 37번에서 본 접속 끊김·회복, 부팅, Slurm 상태가 나빠지거나 돌아온 때."""
    if not events:
        return []
    lines = [("", "default"), ("[최근 사건]", "title")]
    for event in events[:MAX_EVENT_LINES]:
        label = EVENT_KIND_LABELS.get(event["kind"], event["kind"])
        warn = event["kind"] in EVENT_WARN_KINDS or any(word in event["detail"] for word in ("갑자기 꺼짐", "예고 없음"))
        lines.append((f"  {time_label(event['at'], True)}  {label:<6} {event['detail']}", "warn" if warn else "default"))
    return lines


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
    lines += boot_lines(detail.get("boots")) + event_lines(detail.get("events"))
    if detail.get("reboots"):
        lines += [("", "default"), ("[재부팅 이력]", "title")]
        tags = {"done": "ok", "failed": "fail", "cancelled": "default"}
        for reboot in detail["reboots"]:
            lines.append((f"  {time_label(reboot['created_at'], True)}  {REBOOT_MODE_LABELS.get(reboot['mode'], reboot['mode']):<8}"
                          f" {REBOOT_STATE_LABELS.get(reboot['state'], reboot['state']):<10} {reboot['detail']}",
                          tags.get(reboot["state"], "warn")))
    return lines
