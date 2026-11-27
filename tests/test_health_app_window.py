"""Node Health 창(Qt) — 화면 없이(offscreen) 표·패널·그래프 동작을 본다. node_manager 는 가짜로 바꾼다."""
import os
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from health_app import client as nm  # noqa: E402

NOW = int(time.time())
HOSTS = [
    {"name": "connects-10", "role": "slurm_node", "cluster": "main", "status": "ok", "uptime_seconds": 8 * 86400,
     "slurm_state": "IDLE", "items": [{"name": "gpu0", "status": "ok", "detail": "Gen4 x16 (job 사용 중)"}],
     "metrics": {"gpus": [{"temp": 48}], "cpu_temp": 30, "load1": 1, "cpus": 16, "mem_pct": 25}},
    {"name": "connects-2", "role": "slurm_node", "cluster": "test", "status": "fail", "uptime_seconds": 23 * 3600,
     "slurm_state": "IDLE", "items": [{"name": "gpu0.width", "status": "fail", "detail": "x8 (기대 x16)"}]},
]
SERIES = {"hours": 24, "bucket_seconds": 60,
          "gpus": {"0": [{"at": NOW - 600 + i * 60, "temp": 60 + i, "util": 50, "mem_pct": 30} for i in range(10)],
                   "1": [{"at": NOW - 600 + i * 60, "temp": 40, "util": 0, "mem_pct": 5} for i in range(10)]},
          "host": [{"at": NOW - 600 + i * 60, "cpu_temp": 50 + i, "load1": 2, "cpus": 16, "mem_pct": 30} for i in range(10)],
          # 코어 0~3 을 job 21895 가 꽉 쓰고 나머지는 거의 쉰다
          "cores": {"start": NOW - 600, "bucket_seconds": 60, "cores": list(range(16)),
                    "pct": [[97] * 10 if core < 4 else [3] * 10 for core in range(16)],
                    "jobs": [{"job": "21895", "cores": [0, 1, 2, 3], "from": NOW - 540, "to": NOW - 60}]}}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(nm, "get_hosts", lambda: HOSTS)
    monkeypatch.setattr(nm, "get_health", lambda: {"auto_reboot": False, "reboot_dry_run": True})
    monkeypatch.setattr(nm, "get_host", lambda name: {**next(h for h in HOSTS if h["name"] == name),
                                                      "address": "192.168.55.10"})
    monkeypatch.setattr(nm, "get_metrics", lambda name, hours: {**SERIES, "hours": hours})


def wait_until(predicate, seconds=3.0):
    """뒤에서 돈 요청의 결과가 메인 스레드로 올 때까지 Qt 이벤트를 돌린다."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def window(qapp, offline):
    from health_app.window import HealthWindow
    health = HealthWindow()
    health.show()
    assert wait_until(lambda: health.table.rowCount() == 2)
    yield health
    health.close()
    health.deleteLater()
    QApplication.processEvents()


def _column(window, title):
    from health_app.format import COLUMNS
    column = COLUMNS.index(title)
    return [window.table.item(row, column).text() for row in range(window.table.rowCount())]


def test_table_shows_hosts_and_colors_only_problem_cells(window):
    assert window.summary_label.text().startswith("전체 2대")
    names = _column(window, "이름")
    gpu0 = _column(window, "GPU0 링크")
    assert gpu0[names.index("connects-2")] == "x8 ✗"
    from health_app.format import COLUMNS
    row = names.index("connects-2")
    assert window.table.item(row, COLUMNS.index("GPU0 링크")).foreground().color().name() == "#ff5555"
    assert window.table.item(row, COLUMNS.index("역할")).foreground().color().name() != "#ff5555"


def test_uptime_sorts_by_time_not_text(window):
    from PySide6.QtCore import Qt

    from health_app.format import COLUMNS
    window.table.sortItems(COLUMNS.index("가동"), Qt.SortOrder.AscendingOrder)
    assert _column(window, "이름") == ["connects-2", "connects-10"]   # 23h < 8.0d


def test_selecting_a_row_fills_the_selected_panel(window):
    window.table.selectRow(0)
    name = window._selected
    panel = window.selected_dock.panel
    assert wait_until(lambda: name in panel.detail.toPlainText() and panel.charts._lines[0])
    assert window.selected_dock.windowTitle() == f"선택: {name}"
    assert all(button.isEnabled() for button in window.action_buttons)


def test_pin_once_per_host_and_closing_forgets_it(window):
    window.pin("connects-2")
    first = window._pinned["connects-2"]
    window.pin("connects-2")
    window.pin("connects-10")
    assert window._pinned["connects-2"] is first and set(window._pinned) == {"connects-2", "connects-10"}
    first.close()
    assert wait_until(lambda: set(window._pinned) == {"connects-10"})


def test_toggle_hides_all_panels_then_shows_them(window):
    window.pin("connects-2")
    window.toggle_details()
    assert not any(dock.isVisible() for dock in window._docks()) and "펼치기" in window.toggle_button.text()
    window.toggle_details()
    assert all(dock.isVisible() for dock in window._docks())


def test_hover_shows_values_of_the_hovered_graph(qapp, offline):
    from health_app.charts import MetricsCharts
    charts = MetricsCharts()
    charts.resize(1200, 600)
    charts.show()
    charts.plot_series("connects-10", SERIES)
    QApplication.processEvents()
    plot = charts.plots[3]   # CPU 온도
    moment = SERIES["host"][2]["at"]
    y = plot.viewRange()[1][0] + 1
    charts._on_move(plot.vb.mapViewToScene(QPointF(moment, y)))
    assert charts._tips[3].isVisible() and "CPU 온도  52°C" in charts._tips[3].textItem.toPlainText()
    assert all(vline.isVisible() for vline in charts._vlines)
    charts.close()


def test_core_heatmap_names_the_core_and_its_job(qapp):
    from health_app.charts import MetricsCharts
    charts = MetricsCharts()
    charts.resize(1200, 800)
    charts.show()
    charts.plot_series("connects-10", SERIES)
    QApplication.processEvents()
    assert "지금: job 21895 (코어 0-3)" in charts.core_plot.titleLabel.text
    plot = charts.core_plot
    charts._on_move(plot.vb.mapViewToScene(QPointF(NOW - 300, 2)))
    text = charts._tips[-1].textItem.toPlainText()
    assert charts._tips[-1].isVisible() and "코어 2  97%" in text and "job 21895" in text
    charts._on_move(plot.vb.mapViewToScene(QPointF(NOW - 300, 9)))
    assert "코어 9  3%" in charts._tips[-1].textItem.toPlainText() and "job" not in charts._tips[-1].textItem.toPlainText()
    charts.plot_series("connects-10", {**SERIES, "cores": {"cores": [], "pct": [], "jobs": []}})   # 배포 전 서버
    assert charts._cores is None
    charts.close()


def test_refresh_keeps_a_zoomed_range_until_the_range_button_is_pressed(qapp):
    from health_app.charts import MetricsCharts
    charts = MetricsCharts()
    charts.plot_series("connects-10", SERIES)
    charts.plots[0].setXRange(NOW - 300, NOW - 100, padding=0)
    charts.plot_series("connects-10", SERIES)
    assert abs(charts.plots[0].viewRange()[0][0] - (NOW - 300)) < 5
    charts._on_range_clicked(None)
    charts.plot_series("connects-10", SERIES)
    assert charts.plots[0].viewRange()[0][0] < NOW - 3600
    charts.close()


def test_end_labels_stay_apart_and_inside_the_graph():
    from health_app.charts import spread_labels
    assert spread_labels([3, 0], 0, 100, min_gap=9) == [13.5, 4.5]    # 바닥의 0% 가 잘리지 않고, 3% 와 겹치지 않는다
    assert spread_labels([99, 98], 0, 100, min_gap=10) == [95.0, 85.0]  # 위쪽 끝도 안으로
    assert spread_labels([70, 40], 30, 90, min_gap=5) == [70, 40]       # 멀리 떨어져 있으면 그대로
