"""Node Health 창 — 위: 전체 호스트 표와 버튼, 아래: 호스트별 도킹 패널(상세 + 그래프).

- 표에서 한 번 누르면 '선택' 패널이 그 호스트를 보여 준다.
- 두 번 누르거나 [따로 보기]를 누르면 그 호스트 전용 패널이 생긴다. 패널은 탭으로 묶이고,
  제목줄을 끌어 나란히 붙이거나 창 밖으로 떼어낼 수 있다(여러 노드를 동시에 보기).
- 버튼은 node_manager 에 요청만 한다(다시 점검·재부팅 예약·취소). 1분마다 스스로 새로 고친다.
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from health_app import client as nm
from health_app.format import COLUMNS, host_cells, sort_key, summary_line
from health_app.host_panel import HostDock
from health_app.tasks import TaskRunner
from health_app.theme import INK_SECONDARY, STATUS_COLORS

AUTO_REFRESH_MS = 60_000
NAME_ROLE = Qt.ItemDataRole.UserRole
SORT_ROLE = Qt.ItemDataRole.UserRole + 1
STATUS_COLUMNS = {"이름", "상태"}   # 이 두 칸만 상태색 — 줄 전체를 칠하면 어느 칸이 문제인지 안 보인다


class _SortableItem(QTableWidgetItem):
    def __lt__(self, other):
        return self.data(SORT_ROLE) < other.data(SORT_ROLE)


def _cell_color(column, text, status):
    if "✗" in text:
        return STATUS_COLORS["fail"]
    if text.endswith("!"):
        return STATUS_COLORS["warn"]
    return STATUS_COLORS.get(status, STATUS_COLORS[None]) if column in STATUS_COLUMNS else INK_SECONDARY


class HealthWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Node Health")
        self.resize(1680, 1000)
        self._runner = TaskRunner(self)
        self._selected = None
        self._pinned = {}   # 호스트 이름 → 따로 띄운 패널

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 4)
        layout.addLayout(self._build_top_bar())
        self.table = self._build_table()
        layout.addWidget(self.table, 1)
        layout.addLayout(self._build_action_bar())
        self.setCentralWidget(central)

        self.setDockOptions(QMainWindow.DockOption.AnimatedDocks | QMainWindow.DockOption.AllowTabbedDocks
                            | QMainWindow.DockOption.AllowNestedDocks)
        self.setTabPosition(Qt.DockWidgetArea.AllDockWidgetAreas, QTabWidget.TabPosition.North)
        self.selected_dock = HostDock("선택한 호스트 (표에서 누르세요)", self)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.selected_dock)
        self.resizeDocks([self.selected_dock], [600], Qt.Orientation.Vertical)

        self._timer = QTimer(self, interval=AUTO_REFRESH_MS, timeout=self.refresh)
        self._timer.start()
        self.refresh()

    # ---------------------------------------------------------------- 화면 만들기

    def _build_top_bar(self):
        bar = QHBoxLayout()
        self.summary_label = QLabel("불러오는 중...")
        self.summary_label.setStyleSheet("font-size: 11pt; font-weight: bold; color: #ffffff;")
        bar.addWidget(self.summary_label)
        bar.addStretch(1)
        for text, handler in (("새로고침", self.refresh), ("지금 전체 점검", self.on_check_all)):
            button = QPushButton(text)
            button.clicked.connect(handler)
            bar.addWidget(button)
        return bar

    def _build_table(self):
        table = QTableWidget(0, len(COLUMNS))
        table.setHorizontalHeaderLabels(COLUMNS)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(26)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setMinimumSectionSize(64)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.setFont(QFont("Consolas", 10))
        table.setSortingEnabled(True)
        table.sortByColumn(0, Qt.SortOrder.AscendingOrder)   # 처음엔 이름순(connects-2, 3, … 10, storage-37)
        table.itemSelectionChanged.connect(self._on_selection_changed)
        table.cellDoubleClicked.connect(lambda row, _column: self.pin(self._name_at(row)))
        return table

    def _build_action_bar(self):
        bar = QHBoxLayout()
        self.selected_label = QLabel("표에서 호스트를 누르세요 (두 번 누르면 따로 보기)")
        self.selected_label.setMinimumWidth(300)
        bar.addWidget(self.selected_label)
        self.action_buttons = []
        for text, handler, name in (("다시 점검(부하 검사 포함)", self.on_check_selected, ""),
                                    ("재부팅: job 없을 때", lambda: self.on_reboot("when_idle"), ""),
                                    ("재부팅: job 끝나면", lambda: self.on_reboot("after_jobs"), ""),
                                    ("예약 취소", self.on_cancel_reboot, "danger"),
                                    ("따로 보기", lambda: self.pin(self._selected), "quiet")):
            button = QPushButton(text, objectName=name, enabled=False)
            button.clicked.connect(handler)
            bar.addWidget(button)
            self.action_buttons.append(button)
        bar.addStretch(1)
        self.toggle_button = QPushButton("상세 접기 ▼", objectName="quiet")
        self.toggle_button.clicked.connect(self.toggle_details)
        bar.addWidget(self.toggle_button)
        return bar

    # ---------------------------------------------------------------- 불러오기

    def refresh(self):
        self._runner.run(lambda: (nm.get_hosts(), nm.get_health()), self._show_hosts, self._show_error)
        for dock in self._docks():
            dock.panel.refresh()

    def _show_hosts(self, result):
        hosts, health = result
        self.summary_label.setText(summary_line(hosts, health))
        self.table.blockSignals(True)   # 다시 채우는 동안 선택이 풀렸다 잡히며 상세를 또 부르지 않게
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(hosts))
        for row, host in enumerate(hosts):
            for column, (title, text) in enumerate(zip(COLUMNS, host_cells(host))):
                item = _SortableItem(text)
                item.setData(NAME_ROLE, host["name"])
                item.setData(SORT_ROLE, sort_key(title, host, text))
                item.setForeground(QColor(_cell_color(title, text, host.get("status"))))
                self.table.setItem(row, column, item)
        self.table.setSortingEnabled(True)
        self._reselect()
        self.table.blockSignals(False)

    def _reselect(self):
        for row in range(self.table.rowCount()):
            if self._name_at(row) == self._selected:
                self.table.selectRow(row)
                return

    def _show_error(self, exc):
        self.summary_label.setText(f"node_manager 에 연결하지 못했습니다: {exc}")

    # ---------------------------------------------------------------- 선택·패널

    def _name_at(self, row):
        item = self.table.item(row, 0)
        return item.data(NAME_ROLE) if item else None

    def _on_selection_changed(self):
        rows = self.table.selectionModel().selectedRows()
        name = self._name_at(rows[0].row()) if rows else None
        if not name or name == self._selected:
            return
        self._selected = name
        self.selected_label.setText(f"선택: {name}")
        for button in self.action_buttons:
            button.setEnabled(True)
        self.selected_dock.setWindowTitle(f"선택: {name}")
        self.selected_dock.show()
        self.selected_dock.raise_()
        self.selected_dock.panel.show_host(name)
        self.toggle_button.setText("상세 접기 ▼")

    def _docks(self):
        return [self.selected_dock, *self._pinned.values()]

    def pin(self, name):
        """그 호스트만 보는 패널을 따로 만든다. 이미 있으면 그 패널을 앞으로."""
        if not name:
            return
        dock = self._pinned.get(name)
        if dock is None:
            dock = HostDock(f"📌 {name}", self)
            dock.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            dock.closed.connect(lambda closed=name: self._pinned.pop(closed, None))
            self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
            self.tabifyDockWidget(self.selected_dock, dock)
            dock.panel.show_host(name)
            self._pinned[name] = dock
        dock.show()
        dock.raise_()
        self.toggle_button.setText("상세 접기 ▼")

    def toggle_details(self):
        """아래 패널을 모두 접으면 표가 창을 채운다. 다시 누르면 그대로 펼친다."""
        docks = self._docks()
        if any(dock.isVisible() for dock in docks):
            for dock in docks:
                dock.hide()
            self.toggle_button.setText("상세 펼치기 ▲")
        else:
            for dock in docks:
                dock.show()
            self.toggle_button.setText("상세 접기 ▼")

    # ---------------------------------------------------------------- 동작

    def _run_action(self, task, done_message):
        def done(_result):
            QMessageBox.information(self, "node_manager", done_message)
            self.refresh()

        self._runner.run(task, done, lambda exc: QMessageBox.critical(self, "node_manager", f"실패: {exc}"))

    def _confirm(self, title, text):
        return QMessageBox.question(self, title, text) == QMessageBox.StandardButton.Yes

    def on_check_all(self):
        self._run_action(nm.check_all, "전체 점검을 시작했습니다. 1~2분 뒤 새로고침하세요.")

    def on_check_selected(self):
        name = self._selected
        self.selected_dock.panel.show_notice(f"{name} 점검 중... (부하 검사 포함, 최대 2분)")
        self._run_action(lambda: nm.check_host(name, load_test=True), f"{name} 점검을 마쳤습니다.")

    def on_reboot(self, mode):
        name = self._selected
        how = "job 이 없으면 바로" if mode == "when_idle" else "지금 drain 하고 job 이 끝나면"
        if self._confirm("재부팅", f"{name} 을(를) {how} 재부팅할까요?\n\n재부팅 뒤 점검을 통과해야 job 을 다시 받습니다."):
            self._run_action(lambda: nm.request_reboot(name, mode),
                             f"{name} 재부팅을 예약했습니다. 진행 상황은 표의 재부팅 칸에 나옵니다.")

    def on_cancel_reboot(self):
        name = self._selected
        if self._confirm("예약 취소", f"{name} 의 재부팅 예약을 취소할까요?"):
            self._run_action(lambda: nm.cancel_reboot(name), f"{name} 재부팅 예약을 취소했습니다.")
