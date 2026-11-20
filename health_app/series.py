"""그래프 데이터 손질 — node_manager 1분 지표(/hosts/{name}/metrics)를 그래프 6개의 선으로. 화면 코드 없는 순수 함수."""
import math

from health_app.theme import GPU_COLORS, SINGLE_COLOR

GPU_TEMP_REFERENCE = 83   # NVIDIA 지포스 목표 온도. 넘으면 클럭을 내리기 시작한다
RANGES = {"6시간": 6, "24시간": 24, "7일": 168}
DEFAULT_RANGE = "24시간"
GAP_FACTOR = 2.5          # 수집 간격의 이 배 넘게 비면 선을 끊는다(꺼진 동안을 이어 그리지 않게)

# (제목, 데이터 위치, 키, 값 단위, 고정 범위)
PANELS = (
    ("GPU 온도 (°C)", "gpu", "temp", "°C", None),
    ("GPU 사용률 (%)", "gpu", "util", "%", (0, 100)),
    ("GPU 메모리 (%)", "gpu", "mem_pct", "%", (0, 100)),
    ("CPU 온도 (°C)", "host", "cpu_temp", "°C", None),
    ("CPU 부하 (코어당 %)", "host", "load_pct", "%", None),
    ("RAM 사용 (%)", "host", "mem_pct", "%", (0, 100)),
)


def line_points(rows, key, bucket_seconds):
    """[{at, key}] → (epoch 초 목록, 값 목록). 수집이 끊긴 구간엔 NaN 을 넣어 선을 끊는다."""
    times, values, previous = [], [], None
    for row in rows:
        value = row.get(key)
        if previous is not None and row["at"] - previous > bucket_seconds * GAP_FACTOR:
            times.append(float(previous + bucket_seconds))
            values.append(math.nan)
        times.append(float(row["at"]))
        values.append(math.nan if value is None else float(value))
        previous = row["at"]
    return times, values


def with_load_percent(host_rows):
    """부하(load1)를 코어 수로 나눠 %로 — 코어 수가 노드마다 달라 그대로는 비교가 안 된다."""
    return [{**row, "load_pct": row["load1"] / row["cpus"] * 100 if row.get("load1") is not None and row.get("cpus") else None}
            for row in host_rows]


def panel_series(series, where, key):
    """[(이름, 색, 시각, 값)]. GPU 는 번호 순(색 고정), 호스트 지표는 이름 없는 한 줄."""
    bucket = series.get("bucket_seconds", 60)
    if where == "host":
        return [("", SINGLE_COLOR, *line_points(with_load_percent(series.get("host", [])), key, bucket))]
    return [(f"GPU{index}", GPU_COLORS[int(index) % len(GPU_COLORS)], *line_points(rows, key, bucket))
            for index, rows in sorted(series.get("gpus", {}).items(), key=lambda item: int(item[0]))]


def finite(values):
    return [value for value in values if not math.isnan(value)]


def value_range(lines, fixed, reference=None):
    """y 범위. 고정 범위가 없으면 값에 여유를 두고 10 단위로 — 기준선이 있으면 늘 보이게 포함한다."""
    if fixed:
        return fixed
    values = [value for _, _, _, ys in lines for value in finite(ys)] + ([reference] if reference else [])
    if not values:
        return 0, 100
    low, high = min(values), max(values)
    pad = max(5.0, (high - low) * 0.15)
    return max(0.0, math.floor((low - pad) / 10) * 10), math.ceil((high + pad) / 10) * 10


def finite_runs(times, values):
    """NaN 으로 끊긴 구간별 [(시각들, 값들)] — 면 채우기를 구간마다 따로 해야 끊긴 곳이 바닥으로 이어지지 않는다."""
    runs, current = [], ([], [])
    for moment, value in zip(times, values):
        if math.isnan(value):
            if current[0]:
                runs.append(current)
            current = ([], [])
            continue
        current[0].append(moment)
        current[1].append(value)
    if current[0]:
        runs.append(current)
    return runs


def nearest_index(times, moment):
    """moment 에 가장 가까운 점의 위치. 비어 있으면 None."""
    if not times:
        return None
    return min(range(len(times)), key=lambda i: abs(times[i] - moment))
