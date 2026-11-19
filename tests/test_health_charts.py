"""Health 탭 그래프 데이터 손질 — 끊긴 구간, 코어당 부하, 축 범위, GPU 색 고정."""
import math

from ui.health_charts import GPU_COLORS, line_points, panel_series, value_range, with_load_percent


def test_line_breaks_where_collection_stopped():
    """재부팅 등으로 수집이 끊긴 구간을 직선으로 이어 그리지 않는다."""
    rows = [{"at": 0, "v": 1}, {"at": 240, "v": 2}, {"at": 3600, "v": 3}]
    times, values = line_points(rows, "v", bucket_seconds=240)
    assert len(times) == 4 and math.isnan(values[2]) and values[-1] == 3.0


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


def test_hover_box_names_single_series_by_the_panel_title(tk_root):
    """제목은 왼쪽 정렬이라 get_title() 기본(가운데)은 빈 문자열이다 — 값 상자가 이름 없이 나오던 버그."""
    from types import SimpleNamespace

    from matplotlib import dates as mdates

    from ui.health_charts import MetricsCharts
    charts = MetricsCharts(tk_root, on_range_change=lambda: None)
    try:
        charts.show("n", {"hours": 24, "bucket_seconds": 60, "gpus": {},
                          "host": [{"at": 1_700_000_000 + i * 60, "cpu_temp": 50 + i, "load1": 1, "cpus": 4, "mem_pct": 30}
                                   for i in range(5)]})
        ax = charts.axes[3]
        moment = mdates.date2num(ax.lines[0].get_xdata()[2])
        charts._on_move(SimpleNamespace(inaxes=ax, xdata=moment, x=ax.bbox.x0 + 10))
        assert "CPU 온도  52°C" in charts._tooltip.get_text()
    finally:
        charts.destroy()
