"""Health 그래프 데이터 손질 — 끊긴 구간, 코어당 부하, 축 범위, GPU 색 고정, 정렬 기준."""
import math

from health_app.format import sort_key
from health_app.series import finite_runs, line_points, nearest_index, panel_series, value_range, with_load_percent
from health_app.theme import GPU_COLORS


def test_line_breaks_where_collection_stopped():
    """재부팅 등으로 수집이 끊긴 구간을 직선으로 이어 그리지 않는다."""
    rows = [{"at": 0, "v": 1}, {"at": 240, "v": 2}, {"at": 3600, "v": 3}]
    times, values = line_points(rows, "v", bucket_seconds=240)
    assert times == [0.0, 240.0, 480.0, 3600.0] and math.isnan(values[2]) and values[-1] == 3.0


def test_missing_values_become_gaps():
    _, values = line_points([{"at": 0, "v": None}, {"at": 60, "v": 5}], "v", 60)
    assert math.isnan(values[0]) and values[1] == 5.0


def test_load_is_shown_per_core():
    rows = with_load_percent([{"at": 0, "load1": 8.0, "cpus": 16}, {"at": 60, "load1": 2.0, "cpus": None}])
    assert rows[0]["load_pct"] == 50.0 and rows[1]["load_pct"] is None


def test_gpu_colors_follow_the_gpu_number_not_the_order():
    series = {"bucket_seconds": 60, "gpus": {"1": [{"at": 0, "temp": 40}], "0": [{"at": 0, "temp": 60}]}}
    lines = panel_series(series, "gpu", "temp")
    assert [(name, color) for name, color, _, _ in lines] == [("GPU0", GPU_COLORS[0]), ("GPU1", GPU_COLORS[1])]


def test_storage_without_gpus_has_no_gpu_lines():
    assert panel_series({"bucket_seconds": 60, "gpus": {}, "host": []}, "gpu", "temp") == []


def test_value_range_pads_and_includes_the_reference_line():
    lines = [("GPU0", "#000", [], [40.0, 72.0])]
    assert value_range(lines, None, reference=83) == (30.0, 90)  # 기준선(83°C)이 늘 보이게
    assert value_range(lines, (0, 100)) == (0, 100)
    assert value_range([("x", "#000", [], [math.nan])], None) == (0, 100)


def test_fill_runs_split_at_gaps():
    nan = math.nan
    assert finite_runs([0, 1, 2, 3, 4], [1, 2, nan, 4, 5]) == [([0, 1], [1, 2]), ([3, 4], [4, 5])]
    assert finite_runs([0], [nan]) == []


def test_nearest_index():
    assert nearest_index([0, 60, 120], 100) == 2 and nearest_index([], 5) is None


def test_sort_keys_compare_numbers_not_text():
    assert sort_key("가동", {"uptime_seconds": 23 * 3600}, "23h") < sort_key("가동", {"uptime_seconds": 8 * 86400}, "8.0d")
    assert sort_key("GPU 온도", {}, "48°/92°") == 92 and sort_key("RAM", {}, "-") == -1
    assert sort_key("이름", {}, "connects-2") < sort_key("이름", {}, "connects-10")
    assert sort_key("상태", {"status": "fail"}, "이상") < sort_key("상태", {"status": "ok"}, "정상")
