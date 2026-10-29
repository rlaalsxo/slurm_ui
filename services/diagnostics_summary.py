"""log_manager attempts 응답 → 실행 시도별 요약 텍스트(순수 함수)."""
from collections import Counter

_EVENT_DETAIL_KEYS = ("xid", "severity", "count", "pci_bus_id", "gpu_uuid", "line")
_SUMMARY_EVENT_CAP = 100  # log_manager 요약은 최근 100개 이벤트만 보관한다


def _peaks_by_device(peaks):
    result = {}
    for key, value in (peaks or {}).items():
        device, _, metric = key.rpartition(":")
        if device:
            result.setdefault(device, {})[metric] = value
    return result


def _format_number(value, unit, digits=0):
    return "-" if value is None else f"{value:.{digits}f}{unit}"


def _device_lines(summary):
    names = summary.get("devices", {})
    lines = []
    for device, metrics in sorted(_peaks_by_device(summary.get("peaks")).items()):
        temp = _format_number(metrics.get("temperature_c"), "C", 1)
        if device.startswith("cpu:"):
            lines.append(f"  CPU  {names.get(device, {}).get('name') or device}: peak {temp}")
        elif device.startswith("GPU-"):
            name = names.get(device, {}).get("name") or "GPU"
            vram = f"{_format_number(metrics.get('memory_used_mib'), '')}/{_format_number(metrics.get('memory_total_mib'), '')} MiB"
            throttle = "  THROTTLED" if metrics.get("thermal_throttle") else ""
            lines.append(f"  GPU  {name} ({device[:12]}): peak {temp}  util "
                         f"{_format_number(metrics.get('utilization_pct'), '%')}  VRAM {vram}{throttle}")
    return lines


def _event_text(event):
    detail = event.get("detail") or {}
    parts = [f"{key}={detail[key]}" for key in _EVENT_DETAIL_KEYS if detail.get(key) not in (None, "")]
    return f"    {str(event.get('timestamp', ''))[:19]}  {event.get('code')}  {' '.join(parts)}".rstrip()


def format_attempts(payload, recent_events=10):
    attempts = (payload or {}).get("attempts") or []
    if not attempts:
        return "No execution attempts recorded (check controller registration and collector delivery)."
    out = []
    for number, item in enumerate(attempts, 1):
        summary = item.get("summary") or {}
        out.append(f"Attempt {number}  node={item.get('node') or '-'}  status={item.get('collection_status')}  "
                   f"exit={item.get('exit_code') if item.get('exit_code') is not None else '-'}  "
                   f"executor={item.get('executor')}:{item.get('executor_job_id') or '-'}")
        out.append(f"  started {item.get('started_at') or '-'}  ended {item.get('ended_at') or '-'}")
        out.extend(_device_lines(summary))
        if summary.get("warnings"):
            out.append("  Warnings: " + ", ".join(summary["warnings"]))
        events = [e for e in summary.get("events", []) if e.get("code")]
        if events:
            counts = Counter(e["code"] for e in events)
            scope = f" (last {_SUMMARY_EVENT_CAP})" if len(events) >= _SUMMARY_EVENT_CAP else ""
            out.append(f"  Events{scope}: " + ", ".join(f"{code} x{n}" for code, n in sorted(counts.items())))
            out.extend(_event_text(e) for e in events[-recent_events:])
        if summary.get("dropped_count"):
            out.append(f"  Collection gap: {summary['dropped_count']} records lost")
        out.append("")
    retention = payload.get("raw_retention_days")
    out.append(f"Raw samples kept {retention} days; summaries are permanent." if retention else "")
    return "\n".join(out).rstrip() + "\n"
