"""호스트 하나의 그래프 6개(pyqtgraph). 한 그래프에 한 가지 수치만(축 하나), GPU 색은 번호마다 고정.

- 마우스 휠: 시간축 확대·축소(6개가 같이 움직임). 기간 버튼을 다시 누르면 원래대로.
- 마우스를 올리면 6개 모두에 같은 시각 세로선 + 올린 그래프에 값 상자.
- 1분마다 새로 그려도 사용자가 확대해 둔 범위는 유지한다.
- CPU 그래프는 코어마다 색이 다른 선. 값 상자에 바쁜 코어 순으로 값과 그 코어를 잡은 Slurm job 이 나온다.
"""
import datetime
import math
import time

import pyqtgraph as pg
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from health_app.series import (CORE_PANEL, DEFAULT_RANGE, GPU_TEMP_REFERENCE, PANELS, RANGES, finite_runs, jobs_on_core,
                               nearest_index, panel_series, running_jobs, value_range)
from health_app.theme import (BASELINE, GPU_COLORS, GRID, INK_MUTED, INK_PRIMARY, INK_SECONDARY, SURFACE, TOOLTIP_BG, UI_FONT,
                              WARNING)

pg.setConfigOptions(antialias=True, background=SURFACE, foreground=INK_MUTED)

END_ROOM = 0.10          # 오른쪽 끝 값 글자 자리(x 범위 비율)
FILL_ALPHA = 26          # 한 줄짜리 % 그래프의 은은한 면(10%)
LABEL_GAP = 0.09         # 끝 값 글자 두 개가 겹치지 않게 벌리는 최소 간격(y 범위 비율)
MAX_END_LABELS = 3       # 선이 많으면(코어별) 지금 값이 큰 몇 개만 끝에 적는다
MAX_TOOLTIP_ROWS = 8     # 코어별 값 상자는 바쁜 순으로 이만큼, 나머지는 한 줄로 묶는다
MANY_LINES_WIDTH = 1.2   # 코어별처럼 선이 많을 때 선 굵기
CORE_PANEL_INDEX = next(index for index, panel in enumerate(PANELS) if panel[1] == CORE_PANEL)


def _short_unit(unit):
    return "°" if unit == "°C" else unit


class _TimeAxis(pg.DateAxisItem):
    """시간축 글자: 하루 넘는 간격은 '11-20', 그 안은 '14:00'(자정만 날짜). 기본값은 'Fri 20' 처럼 영어 요일이 나온다."""

    def tickStrings(self, values, scale, spacing):
        labels = []
        for value in values:
            moment = datetime.datetime.fromtimestamp(value)
            is_midnight = (moment.hour, moment.minute) == (0, 0)
            labels.append(moment.strftime("%m-%d" if spacing >= 86400 or is_midnight else "%H:%M"))
        return labels


def spread_labels(values, low, high, min_gap):
    """끝 값 글자 y 위치: 서로 min_gap 이상 떨어지고, 그래프 위아래 가장자리에 잘리지 않게(입력 순서대로 돌려준다)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    edge = min_gap / 2
    placed = []
    for i in order:
        y = max(values[i], low + edge, placed[-1] + min_gap if placed else low + edge)
        placed.append(y)
    overflow = (placed[-1] - (high - edge)) if placed else 0
    if overflow > 0:
        placed = [y - overflow for y in placed]
    result = [0.0] * len(values)
    for position, i in enumerate(order):
        result[i] = placed[position]
    return result


class MetricsCharts(QWidget):
    range_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("charts")   # 바탕색은 이 위젯에만 — 이름 없이 주면 버튼까지 덮어 선택 표시가 사라진다
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#charts {{ background: {SURFACE}; }}")
        self._lines = [[] for _ in PANELS]      # 그래프별 [(이름, 단위, 시각, 값)] — 값 상자용
        self._shown_key, self._default_x = None, None
        self._vlines, self._tips = [], []
        self._cores = None                      # node_manager metrics 의 cores — 코어를 잡은 job 을 찾을 때

        header = QHBoxLayout()
        header.setContentsMargins(12, 10, 12, 0)
        self.title_label = QLabel("호스트를 고르면 최근 수치가 나옵니다")
        self.title_label.setStyleSheet(f"background: transparent; color: {INK_SECONDARY}; font-weight: bold; font-size: 11pt;")
        self.legend_label = QLabel("")
        self.legend_label.setTextFormat(Qt.TextFormat.RichText)
        self.legend_label.setStyleSheet("background: transparent;")
        header.addWidget(self.title_label)
        header.addSpacing(24)
        header.addWidget(self.legend_label)
        header.addStretch(1)
        self._range_group = QButtonGroup(self)
        for name in RANGES:
            button = QPushButton(name, objectName="range", checkable=True, checked=name == DEFAULT_RANGE)
            button.setToolTip("다시 누르면 확대를 풀고 처음 범위로")
            self._range_group.addButton(button)
            header.addWidget(button)
        self._range_group.buttonClicked.connect(self._on_range_clicked)

        self.graphs = pg.GraphicsLayoutWidget()
        self.graphs.ci.layout.setSpacing(14)
        self.graphs.ci.setContentsMargins(8, 6, 14, 8)
        self.plots = []
        for index, (title, *_rest) in enumerate(PANELS):
            plot = self.graphs.addPlot(row=index // 3, col=index % 3,
                                       axisItems={"bottom": _TimeAxis(orientation="bottom")})
            self._style(plot, title)
            if self.plots:
                plot.setXLink(self.plots[0])
            self.plots.append(plot)
        self.graphs.scene().sigMouseMoved.connect(self._on_move)
        self.graphs.viewport().installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header)
        layout.addWidget(self.graphs, 1)
        self.show_message("")

    @property
    def hours(self):
        return RANGES[self._range_group.checkedButton().text()]

    def _on_range_clicked(self, _button):
        self._shown_key = None   # 같은 버튼을 다시 눌러도 확대를 푼다
        self.range_changed.emit()

    # ---------------------------------------------------------------- 그리기

    @staticmethod
    def _style(plot, title):
        plot.setTitle(title, color=INK_SECONDARY, size="10pt", justify="left")
        plot.setMenuEnabled(False)
        plot.hideButtons()
        plot.setMouseEnabled(x=True, y=False)
        plot.showGrid(x=False, y=True, alpha=1.0)
        tick_font = QFont(UI_FONT, 8)
        left, bottom = plot.getAxis("left"), plot.getAxis("bottom")
        left.setPen(pg.mkPen(GRID))          # 가로 격자는 아주 옅게, 세로축 선은 따로 안 보이게
        bottom.setPen(pg.mkPen(BASELINE))
        for axis in (left, bottom):
            axis.setTextPen(pg.mkPen(INK_MUTED))
            axis.setStyle(tickLength=0, tickTextOffset=6, tickFont=tick_font)
        left.setWidth(34)

    def _reset_plots(self):
        self._vlines, self._tips = [], []
        for plot, (title, *_rest) in zip(self.plots, PANELS):
            plot.clear()
            plot.setTitle(title, color=INK_SECONDARY, size="10pt", justify="left")
            vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(INK_MUTED, width=1))
            vline.hide()
            plot.addItem(vline, ignoreBounds=True)
            tip = pg.TextItem("", color=INK_PRIMARY, fill=pg.mkBrush(TOOLTIP_BG), border=pg.mkPen(BASELINE))
            tip.setZValue(100)
            tip.hide()
            plot.addItem(tip, ignoreBounds=True)
            self._vlines.append(vline)
            self._tips.append(tip)

    def show_message(self, message):
        self._reset_plots()
        self._lines = [[] for _ in PANELS]
        self._cores = None
        self._default_x = self._time_window()
        self.plots[0].setXRange(*self._default_x, padding=0)
        for plot in self.plots:
            plot.setYRange(0, 100, padding=0)
            if message:
                plot.addItem(self._centered_text(plot, message))
        self.legend_label.setText("")

    def _time_window(self):
        """지금부터 고른 기간만큼 + 오른쪽 끝 값 글자 자리."""
        now = time.time()
        start = now - self.hours * 3600
        return start, now + (now - start) * END_ROOM

    @staticmethod
    def _centered_text(plot, text):
        (x0, x1), (y0, y1) = plot.viewRange()
        item = pg.TextItem(text, color=INK_MUTED, anchor=(0.5, 0.5))
        item.setPos((x0 + x1) / 2, (y0 + y1) / 2)
        return item

    def plot_series(self, host_name, series):
        key = (host_name, self.hours)
        kept_x = self.plots[0].viewRange()[0] if key == self._shown_key and self._is_zoomed() else None
        self._reset_plots()
        self.title_label.setText(f"{host_name} — 최근 {self._range_group.checkedButton().text()}")
        self.legend_label.setText(self._legend(len(series.get("gpus", {}))))
        cores = series.get("cores")
        self._cores = cores if cores and cores.get("cores") else None

        self._default_x = self._time_window()
        for index, (plot, (title, where, data_key, unit, fixed)) in enumerate(zip(self.plots, PANELS)):
            lines = panel_series(series, where, data_key)
            reference = GPU_TEMP_REFERENCE if (where, data_key) == ("gpu", "temp") else None
            self._lines[index] = [(name, unit, times, values) for name, _color, times, values in lines]
            self._draw_panel(plot, lines, unit, value_range(lines, fixed, reference), reference)
        self._title_running_jobs()
        x0, x1 = kept_x or self._default_x
        self.plots[0].setXRange(x0, x1, padding=0)
        self._shown_key = key

    def _title_running_jobs(self):
        """CPU 그래프 제목 끝에 지금 도는 job 과 그 코어: '· job 44952 (0,2,4,6)'."""
        running = running_jobs(self._cores, time.time()) if self._cores else []
        if running:
            title = PANELS[CORE_PANEL_INDEX][0] + "  · " + ", ".join(f"job {job} ({cores})" for job, cores in running)
            self.plots[CORE_PANEL_INDEX].setTitle(title, color=INK_SECONDARY, size="10pt", justify="left")

    def _is_zoomed(self):
        if self._default_x is None:
            return False
        x0, x1 = self.plots[0].viewRange()[0]
        return abs(x0 - self._default_x[0]) > 60 or abs(x1 - self._default_x[1]) > 60

    @staticmethod
    def _legend(gpu_count):
        """두 줄 이상이면 범례가 늘 있다(색만으로 구분하게 두지 않는다). 글자는 회색, 색은 옆의 선 조각만."""
        if gpu_count < 2:
            return ""
        keys = [f'<span style="color:{GPU_COLORS[i % len(GPU_COLORS)]}; font-size:14pt;">━</span>'
                f'<span style="color:{INK_SECONDARY};"> GPU{i}</span>' for i in range(gpu_count)]
        return "&nbsp;&nbsp;&nbsp;".join(keys)

    def _draw_panel(self, plot, lines, unit, y_range, reference):
        low, high = y_range
        has_data = any(not math.isnan(value) for *_rest, values in lines for value in values)
        if not has_data:
            plot.setYRange(low, high, padding=0)
            plot.setXRange(*self._default_x, padding=0)
            plot.addItem(self._centered_text(plot, "데이터 없음"))
            return
        if unit == "%" and len(lines) == 1:   # 은은한 면은 한 줄일 때만 — 두 면이 겹치면 색이 섞여 탁해진다
            _name, color, times, values = lines[0]
            fill = QColor(color)
            fill.setAlpha(FILL_ALPHA)
            for run_times, run_values in finite_runs(times, values):
                plot.plot(run_times, run_values, pen=None, fillLevel=low, brush=fill)
        width = 2 if len(lines) <= len(GPU_COLORS) else MANY_LINES_WIDTH
        for _name, color, times, values in lines:
            plot.plot(times, values, pen=pg.mkPen(color, width=width), connect="finite")
        if reference is not None:
            plot.addItem(pg.InfiniteLine(
                pos=reference, angle=0, movable=False, pen=pg.mkPen(WARNING, width=1, style=Qt.PenStyle.DashLine),
                label=f"{reference}°C 기준", labelOpts={"position": 0.97, "color": INK_MUTED, "anchors": [(1, 1), (1, 1)]}))
        plot.setYRange(low, high, padding=0)
        self._end_labels(plot, lines, unit, y_range)

    @staticmethod
    def _end_labels(plot, lines, unit, y_range):
        """선 끝의 점 + 지금 값. 두 값이 가까우면 글자만 위아래로 벌린다. 선이 많으면 지금 값이 큰 몇 개만."""
        ends = []
        for name, color, times, values in lines:
            last = next((i for i in range(len(values) - 1, -1, -1) if not math.isnan(values[i])), None)
            if last is not None:
                ends.append((values[last], times[last], color, name))
        many = len(lines) > len(GPU_COLORS)
        if many:
            ends = sorted(ends, key=lambda end: end[0], reverse=True)[:MAX_END_LABELS]
        label_ys = spread_labels([value for value, *_rest in ends], *y_range,
                                 min_gap=(y_range[1] - y_range[0]) * LABEL_GAP)
        for (value, moment, color, name), label_y in zip(ends, label_ys):
            plot.addItem(pg.ScatterPlotItem([moment], [value], size=8, brush=pg.mkBrush(color),
                                            pen=pg.mkPen(SURFACE, width=2)))
            prefix = f"{name.replace('코어 ', '#')}: " if many else ""   # '#3: 98%' — 어느 코어인지
            text = pg.TextItem(f"{prefix}{value:.0f}{_short_unit(unit)}", color=INK_SECONDARY, anchor=(-0.15, 0.5))
            text.setPos(moment, label_y)
            plot.addItem(text)

    # ---------------------------------------------------------------- 마우스

    def eventFilter(self, watched, event):
        if watched is self.graphs.viewport() and event.type() == QEvent.Type.Leave:
            self._hide_hover()
        return super().eventFilter(watched, event)

    def _hide_hover(self):
        for item in self._vlines + self._tips:
            item.hide()

    def _on_move(self, scene_pos):
        hovered = next((i for i, plot in enumerate(self.plots) if plot.vb.sceneBoundingRect().contains(scene_pos)), None)
        if hovered is None or not any(self._lines):
            self._hide_hover()
            return
        moment = self.plots[hovered].vb.mapSceneToView(scene_pos).x()
        for vline in self._vlines:
            vline.setPos(moment)
            vline.show()
        for tip in self._tips:
            tip.hide()
        text = self._tooltip_text(hovered, moment)
        if not text:
            return
        tip, plot = self._tips[hovered], self.plots[hovered]
        (x0, x1), (_y0, y1) = plot.viewRange()
        tip.setText(text)   # 글자를 먼저 바꿔야 상자 크기가 새 글자에 맞는다
        tip.setAnchor((1.05, 0) if moment > x0 + (x1 - x0) * 0.6 else (-0.05, 0))  # 오른쪽 끝에선 왼쪽으로
        tip.setPos(moment, y1)
        tip.show()

    def _tooltip_text(self, panel_index, moment):
        values_at, stamp = [], None
        panel_name = PANELS[panel_index][0].split(" (")[0]
        for name, unit, times, values in self._lines[panel_index]:
            index = nearest_index(times, moment)
            if index is None or math.isnan(values[index]):
                continue
            stamp = times[index]
            values_at.append((name or panel_name, unit, values[index]))   # 한 줄짜리는 그래프 이름으로
        if not values_at:
            return ""
        if panel_index == CORE_PANEL_INDEX and len(values_at) > len(GPU_COLORS):
            rows = self._core_rows(values_at, moment)
        else:
            rows = [f"{name}  {value:.0f}{unit}" for name, unit, value in values_at]
        return "\n".join([datetime.datetime.fromtimestamp(stamp).strftime("%m-%d %H:%M"), *rows])

    def _core_rows(self, values_at, moment):
        """바쁜 코어부터 '코어 3  98%  job 44952', 나머지는 '그 밖 12개 ≤ 5%'."""
        ordered = sorted(values_at, key=lambda row: row[2], reverse=True)
        rows = []
        for name, unit, value in ordered[:MAX_TOOLTIP_ROWS]:
            jobs = jobs_on_core(self._cores, int(name.split()[-1]), moment) if self._cores else []
            rows.append(f"{name:<6} {value:>3.0f}{unit}" + (f"  job {', '.join(jobs)}" if jobs else ""))
        rest = ordered[MAX_TOOLTIP_ROWS:]
        if rest:
            rows.append(f"그 밖 {len(rest)}개 ≤ {rest[0][2]:.0f}{rest[0][1]}")
        return rows
