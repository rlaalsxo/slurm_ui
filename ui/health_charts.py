"""Health 탭 그래프 — node_manager 1분 지표(/hosts/{name}/metrics)를 작은 그래프 6개로 그린다.

한 그래프에 한 가지 수치만(축 하나). 색은 GPU0·GPU1 두 가지만 고정(검증 통과: dark #3987e5·#d95926, 배경 #1a1a19).
글자는 데이터 색을 쓰지 않고 회색 잉크만. 마우스를 올리면 모든 그래프에 같은 시각 세로선 + 값 상자.
"""
import bisect
import datetime
import math

import customtkinter as ctk
import matplotlib
from matplotlib import dates as mdates
from matplotlib import font_manager
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, MaxNLocator


def _korean_font():
    """설치된 한글 글꼴 하나(Windows 맑은 고딕). 없는 글꼴을 목록에 두면 matplotlib 이 경고를 쏟는다."""
    installed = {font.name for font in font_manager.fontManager.ttflist}
    return next((name for name in ("Malgun Gothic", "AppleGothic", "NanumGothic") if name in installed), "DejaVu Sans")


matplotlib.rcParams["font.family"] = [_korean_font(), "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

SURFACE = "#1a1a19"
INK_PRIMARY, INK_SECONDARY, INK_MUTED = "#ffffff", "#c3c2b7", "#898781"
GRID, BASELINE = "#2c2c2a", "#383835"
TOOLTIP_BG = "#262624"
GPU_COLORS = ("#3987e5", "#d95926")   # 범주 1·2번 — GPU 번호마다 고정(정렬이 바뀌어도 색은 따라가지 않는다)
SINGLE_COLOR = GPU_COLORS[0]
WARNING = "#fab219"                    # 상태색(경고) — 기준선에만, 글자와 함께
GPU_TEMP_REFERENCE = 83                # NVIDIA 지포스 목표 온도. 넘으면 클럭을 내리기 시작한다
RANGES = {"6시간": 6, "24시간": 24, "7일": 168}
GAP_FACTOR = 2.5                       # 수집 간격의 이 배 넘게 비면 선을 끊는다(꺼진 동안을 이어 그리지 않게)

# (제목, 데이터 위치, 키, 값 단위, 고정 범위)
PANELS = (
    ("GPU 온도 (°C)", "gpu", "temp", "°C", None),
    ("GPU 사용률 (%)", "gpu", "util", "%", (0, 100)),
    ("GPU 메모리 (%)", "gpu", "mem_pct", "%", (0, 100)),
    ("CPU 온도 (°C)", "host", "cpu_temp", "°C", None),
    ("CPU 부하 (코어당 %)", "host", "load_pct", "%", None),
    ("RAM 사용 (%)", "host", "mem_pct", "%", (0, 100)),
)
# 기간별 시간 눈금: 6시간은 1시간, 24시간은 6시간, 7일은 하루 간격. locator 는 축마다 새로 만든다(공유하면 꼬인다).
TIME_TICKS = {6: (lambda: mdates.HourLocator(interval=1), "%H:%M"),
              24: (lambda: mdates.HourLocator(byhour=range(0, 24, 6)), "%H:%M"),
              168: (lambda: mdates.DayLocator(), "%m-%d")}


def line_points(rows, key, bucket_seconds):
    """[{at, key}] → (시각 목록, 값 목록). 수집이 끊긴 구간엔 NaN 을 넣어 선을 끊는다."""
    times, values, previous = [], [], None
    for row in rows:
        value = row.get(key)
        if previous is not None and row["at"] - previous > bucket_seconds * GAP_FACTOR:
            times.append(datetime.datetime.fromtimestamp(previous + bucket_seconds))
            values.append(math.nan)
        times.append(datetime.datetime.fromtimestamp(row["at"]))
        values.append(math.nan if value is None else float(value))
        previous = row["at"]
    return times, values


def with_load_percent(host_rows):
    """부하(load1)를 코어 수로 나눠 %로 — 코어 수가 노드마다 달라 그대로는 비교가 안 된다."""
    return [{**row, "load_pct": row["load1"] / row["cpus"] * 100 if row.get("load1") is not None and row.get("cpus") else None}
            for row in host_rows]


def panel_series(series, where, key):
    """[(이름, 색, 시각, 값)]. GPU 는 번호 순(색 고정), 호스트 지표는 한 줄."""
    bucket = series.get("bucket_seconds", 60)
    if where == "host":
        return [("", SINGLE_COLOR, *line_points(with_load_percent(series.get("host", [])), key, bucket))]
    return [(f"GPU{index}", GPU_COLORS[int(index) % len(GPU_COLORS)], *line_points(rows, key, bucket))
            for index, rows in sorted(series.get("gpus", {}).items(), key=lambda item: int(item[0]))]


def _finite(values):
    return [value for value in values if not math.isnan(value)]


def value_range(lines, fixed, reference=None):
    if fixed:
        return fixed
    values = [value for _, _, _, ys in lines for value in _finite(ys)] + ([reference] if reference else [])
    if not values:
        return 0, 100
    low, high = min(values), max(values)
    pad = max(5.0, (high - low) * 0.15)
    return max(0.0, math.floor((low - pad) / 10) * 10), math.ceil((high + pad) / 10) * 10


class MetricsCharts(ctk.CTkFrame):
    def __init__(self, master, on_range_change):
        super().__init__(master, fg_color=SURFACE, corner_radius=8)
        bar = ctk.CTkFrame(self, fg_color=SURFACE)
        bar.pack(fill="x", padx=12, pady=(10, 0))
        self.title_label = ctk.CTkLabel(bar, text="호스트를 고르면 최근 수치가 나옵니다", text_color=INK_SECONDARY,
                                        font=ctk.CTkFont(size=13, weight="bold"))
        self.title_label.pack(side="left")
        self.range_picker = ctk.CTkSegmentedButton(bar, values=list(RANGES), command=lambda _: on_range_change())
        self.range_picker.set("24시간")
        self.range_picker.pack(side="right")

        self.figure = Figure(facecolor=SURFACE, dpi=100, layout="constrained")
        self.axes = [self.figure.add_subplot(2, 3, i + 1) for i in range(len(PANELS))]
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().configure(background=SURFACE, highlightthickness=0)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=6, pady=6)
        self._hover = []  # [(axes, 단위, [(이름, 시각, 값)])]
        self._crosshairs, self._tooltip = [], None
        self.canvas.mpl_connect("motion_notify_event", self._on_move)
        self.canvas.mpl_connect("axes_leave_event", lambda _: self._hide_hover())
        self.show_message("")

    @property
    def hours(self):
        return RANGES[self.range_picker.get()]

    # ---------------------------------------------------------------- 그리기

    def _style(self, ax, title):
        ax.set_facecolor(SURFACE)
        ax.set_title(title, loc="left", color=INK_SECONDARY, fontsize=10, pad=6)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(BASELINE)
        ax.grid(axis="y", color=GRID, linewidth=1)
        ax.set_axisbelow(True)
        ax.tick_params(colors=INK_MUTED, labelsize=8, length=0, pad=4)

    def show_message(self, message):
        self.figure.clear()
        self.axes = [self.figure.add_subplot(2, 3, i + 1) for i in range(len(PANELS))]
        for ax, (title, *_rest) in zip(self.axes, PANELS):
            self._style(ax, title)
            ax.set_xticks([])
            ax.set_yticks([])
        if message:
            self.figure.text(0.5, 0.5, message, ha="center", va="center", color=INK_MUTED, fontsize=11)
        self._hover, self._crosshairs, self._tooltip = [], [], None
        self.canvas.draw_idle()

    def show(self, host_name, series):
        self.figure.clear()
        self.axes = [self.figure.add_subplot(2, 3, i + 1) for i in range(len(PANELS))]
        self._hover, self._crosshairs, self._tooltip = [], [], None
        self.title_label.configure(text=f"{host_name} — 최근 {self.range_picker.get()}")
        gpu_count = len(series.get("gpus", {}))
        if gpu_count > 1:  # 두 줄 이상이면 범례가 늘 있다(색만으로 구분하게 두지 않는다)
            handles = [Line2D([], [], color=GPU_COLORS[i % len(GPU_COLORS)], linewidth=2) for i in range(gpu_count)]
            self.figure.legend(handles, [f"GPU{i}" for i in range(gpu_count)], loc="outside upper right", ncols=gpu_count,
                               frameon=False, labelcolor=INK_SECONDARY, fontsize=9, handlelength=1.6)
        ticks = TIME_TICKS.get(series.get("hours", 24), TIME_TICKS[24])
        for ax, (title, where, key, unit, fixed) in zip(self.axes, PANELS):
            self._style(ax, title)
            lines = [line for line in panel_series(series, where, key) if _finite(line[3])]
            if not lines:
                ax.set_xticks([])
                ax.set_yticks([])
                empty = "GPU 없음" if where == "gpu" and not gpu_count else "수집된 값 없음"
                ax.text(0.5, 0.5, empty, transform=ax.transAxes, ha="center", va="center", color=INK_MUTED, fontsize=9)
                continue
            reference = GPU_TEMP_REFERENCE if (where, key) == ("gpu", "temp") else None
            self._draw_panel(ax, lines, unit, value_range(lines, fixed, reference), reference, ticks)
        self.canvas.draw_idle()

    def _draw_panel(self, ax, lines, unit, y_range, reference, ticks):
        for name, color, times, values in lines:
            ax.plot(times, values, color=color, linewidth=2, solid_capstyle="round", solid_joinstyle="round")
            if unit == "%" and len(lines) == 1:
                # 은은한 면은 한 줄일 때만 — 두 면이 겹치면 색이 섞여 탁해진다
                ax.fill_between(times, values, color=color, alpha=0.10, linewidth=0)
        if reference:
            ax.axhline(reference, color=WARNING, linewidth=1, alpha=0.6)
            ax.text(1.0, reference, f" {reference}°C 기준", transform=ax.get_yaxis_transform(), color=INK_MUTED,
                    fontsize=7, va="bottom", ha="right")
        self._end_labels(ax, lines, unit, y_range)
        ax.set_ylim(*y_range)
        ax.yaxis.set_major_locator(FixedLocator([0, 50, 100]) if y_range == (0, 100) else MaxNLocator(3))
        make_locator, time_format = ticks
        ax.xaxis.set_major_locator(make_locator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter(time_format))
        start = min(times[0] for _, _, times, _ in lines)
        end = max(times[-1] for _, _, times, _ in lines)
        ax.set_xlim(start, end + (end - start) * 0.12)  # 오른쪽에 끝값 숫자 자리를 둔다(옆 그래프로 넘치지 않게)
        self._hover.append((ax, unit, [(name, times, values) for name, _, times, values in lines]))
        self._crosshairs.append(ax.axvline(lines[0][2][0], color=INK_MUTED, linewidth=1, visible=False))

    def _end_labels(self, ax, lines, unit, y_range):
        """선 끝에 지금 값(점 + 숫자). 끝값이 서로 붙으면 겹쳐 쓰지 않고 범례·값 상자에 맡긴다."""
        ends = []
        for name, color, times, values in lines:
            last = next(((t, v) for t, v in zip(reversed(times), reversed(values)) if not math.isnan(v)), None)
            if last:
                ends.append((color, *last))
                ax.plot([last[0]], [last[1]], marker="o", markersize=7, color=color,
                        markeredgecolor=SURFACE, markeredgewidth=2, zorder=5)  # 표면색 고리
        crowded = len(ends) > 1 and abs(ends[0][2] - ends[1][2]) < (y_range[1] - y_range[0]) * 0.08
        if crowded:
            return
        for _, time, value in ends:
            ax.annotate(f"{value:.0f}{'°' if unit == '°C' else unit}", (time, value), xytext=(6, 0),
                        textcoords="offset points", va="center", color=INK_PRIMARY, fontsize=8, annotation_clip=False)

    # ---------------------------------------------------------------- 마우스 올리기

    def _hide_hover(self):
        for line in self._crosshairs:
            line.set_visible(False)
        if self._tooltip is not None:
            self._tooltip.set_visible(False)
        self.canvas.draw_idle()

    def _on_move(self, event):
        target = next((entry for entry in self._hover if entry[0] is event.inaxes), None)
        if target is None or event.xdata is None:
            self._hide_hover()
            return
        ax, unit, lines = target
        when = mdates.num2date(event.xdata).replace(tzinfo=None)
        times = lines[0][1]
        index = min(max(bisect.bisect_left(times, when), 0), len(times) - 1)
        moment = times[index]
        for crosshair in self._crosshairs:
            crosshair.set_xdata([moment, moment])
            crosshair.set_visible(True)
        rows = [moment.strftime("%m-%d %H:%M")]
        for name, line_times, values in lines:
            position = min(bisect.bisect_left(line_times, moment), len(line_times) - 1)
            value = values[position]
            shown = "-" if math.isnan(value) else f"{value:.0f}{unit}"
            rows.append(f"{name or ax.get_title(loc='left').split(' (')[0]}  {shown}")  # 한 줄짜리는 그래프 이름으로
        if self._tooltip is not None:
            self._tooltip.remove()
        right_half = (event.x - ax.bbox.x0) / max(ax.bbox.width, 1) > 0.55  # 오른쪽이면 상자를 왼쪽에(잘리지 않게)
        self._tooltip = ax.annotate("\n".join(rows), (moment, ax.get_ylim()[1]), xytext=(-8 if right_half else 8, -4),
                                    textcoords="offset points", ha="right" if right_half else "left",
                                    va="top", fontsize=8, color=INK_PRIMARY, annotation_clip=False,
                                    bbox={"boxstyle": "round,pad=0.4", "facecolor": TOOLTIP_BG,
                                          "edgecolor": (1, 1, 1, 0.10), "linewidth": 1})
        self.canvas.draw_idle()
