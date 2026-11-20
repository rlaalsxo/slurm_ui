"""호스트 하나: 왼쪽 상세 글, 오른쪽 그래프. 경계는 끌어서 넓힐 수 있다. 창 아래 도킹 패널마다 하나씩 쓴다."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QDockWidget, QHBoxLayout, QPlainTextEdit, QSplitter, QWidget

from health_app import client as nm
from health_app.charts import MetricsCharts
from health_app.format import detail_lines
from health_app.tasks import TaskRunner
from health_app.theme import DETAIL_COLORS, MONO_FONT


class HostPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.host_name = None
        self._runner = TaskRunner(self)
        self.detail = QPlainTextEdit(readOnly=True)
        self.detail.setFont(QFont(MONO_FONT, 10))
        self.charts = MetricsCharts()
        self.charts.range_changed.connect(self._load_metrics)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.detail)
        splitter.addWidget(self.charts)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([520, 1100])
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

    def show_host(self, name):
        self.host_name = name
        self.refresh()

    def refresh(self):
        if self.host_name:
            self._load_detail()
            self._load_metrics()

    def show_notice(self, text, tag="default"):
        self._write([(text, tag)])

    def _write(self, lines):
        self.detail.clear()
        cursor = self.detail.textCursor()
        for text, tag in lines:
            line_format = QTextCharFormat()
            line_format.setForeground(QColor(DETAIL_COLORS.get(tag, DETAIL_COLORS["default"])))
            cursor.insertText(text + "\n", line_format)
        self.detail.moveCursor(QTextCursor.MoveOperation.Start)

    def _load_detail(self):
        name = self.host_name

        def show(detail):
            if name == self.host_name:  # 그사이 다른 호스트를 고르면 버린다
                self._write(detail_lines(detail))

        def fail(exc):
            if name == self.host_name:
                self.show_notice(f"상세를 불러오지 못했습니다: {exc}", "fail")

        self._runner.run(lambda: nm.get_host(name), show, fail)

    def _load_metrics(self):
        name, hours = self.host_name, self.charts.hours
        if not name:
            return

        def show(series):
            if name == self.host_name and hours == self.charts.hours:  # 그사이 다른 호스트·기간을 고르면 버린다
                self.charts.plot_series(name, series)

        self._runner.run(lambda: nm.get_metrics(name, hours), show,
                         lambda exc: self.charts.show_message(f"그래프를 불러오지 못했습니다: {exc}"))


class HostDock(QDockWidget):
    """HostPanel 을 담은 도킹 패널 — 탭으로 묶기, 나란히 붙이기, 떼어내 따로 띄우기가 된다."""

    closed = Signal()   # 사용자가 X 로 닫았을 때만(접기 버튼의 hide 는 아님)

    def __init__(self, title, parent):
        super().__init__(title, parent)
        self.setObjectName(f"dock:{title}")
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable
                         | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.panel = HostPanel(self)
        self.setWidget(self.panel)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)
