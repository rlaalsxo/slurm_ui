"""Health 탭 — node_manager 의 점검 결과와 재부팅 상태를 본다. 다시 점검·재부팅·예약 취소 버튼은 node_manager 에 요청만 한다."""
from tkinter import messagebox

import customtkinter as ctk

from services import node_manager_client as nm
from ui.background import BackgroundTaskMixin, run_detached
from ui.health_charts import MetricsCharts
from ui.health_format import detail_lines, header_line, host_line, summary_line

AUTO_REFRESH_MS = 60_000
STATUS_COLORS = {"ok": "#00ff66", "warn": "#ffcc00", "fail": "#ff5555", None: "#999999"}


class HealthFrame(BackgroundTaskMixin, ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self._init_background_tasks()
        self._hosts, self._line_to_host, self._selected = [], {}, None
        self._auto_after_id = None
        mono = ctk.CTkFont(family="Consolas", size=13)

        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=10, pady=(10, 5))
        self.summary_label = ctk.CTkLabel(top, text="불러오는 중...", font=ctk.CTkFont(size=14, weight="bold"))
        self.summary_label.pack(side="left", padx=5)
        ctk.CTkButton(top, text="지금 전체 점검", width=130, command=self.on_check_all).pack(side="right", padx=5)
        ctk.CTkButton(top, text="새로고침", width=100, command=self.refresh).pack(side="right", padx=5)

        self.table = ctk.CTkTextbox(self, height=290, font=mono)
        self.table.pack(fill="x", padx=10, pady=5)
        for status, color in STATUS_COLORS.items():
            self.table.tag_config(str(status), foreground=color)
        self.table.tag_config("header", foreground="#66aaff")
        self.table.tag_config("selected", background="#333333")
        self.table.bind("<Button-1>", self._on_table_click)

        actions = ctk.CTkFrame(self)
        actions.pack(fill="x", padx=10, pady=5)
        self.selected_label = ctk.CTkLabel(actions, text="표에서 호스트를 누르세요", width=220, anchor="w")
        self.selected_label.pack(side="left", padx=5)
        self.action_buttons = [
            ctk.CTkButton(actions, text="다시 점검(부하 검사 포함)", width=190, command=self.on_check_selected),
            ctk.CTkButton(actions, text="재부팅: job 없을 때", width=150, command=lambda: self.on_reboot("when_idle")),
            ctk.CTkButton(actions, text="재부팅: job 끝나면", width=150, command=lambda: self.on_reboot("after_jobs")),
            ctk.CTkButton(actions, text="예약 취소", width=100, fg_color="#7a3b3b", command=self.on_cancel_reboot),
        ]
        for button in self.action_buttons:
            button.pack(side="left", padx=5)
            button.configure(state="disabled")

        # 아래: 왼쪽 상세 글, 오른쪽 그래프(최근 6시간/24시간/7일)
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="both", expand=True, padx=10, pady=(5, 10))
        self.detail = ctk.CTkTextbox(bottom, font=mono, width=560)
        self.detail.pack(side="left", fill="y")
        self.charts = MetricsCharts(bottom, on_range_change=lambda: self._load_metrics(self._selected))
        self.charts.pack(side="left", fill="both", expand=True, padx=(8, 0))
        for tag, color in {"ok": "#00ff66", "warn": "#ffcc00", "fail": "#ff5555", "title": "#66aaff", "default": "#cccccc"}.items():
            self.detail.tag_config(tag, foreground=color)

        self.refresh()
        self._auto_after_id = self.after(AUTO_REFRESH_MS, self._auto_tick)

    # ---------------------------------------------------------------- 불러오기

    def refresh(self):
        self.run_background(task=lambda: (nm.get_hosts(), nm.get_health()), on_success=self._show_hosts,
                            on_error=self._show_error)
        if self._selected:
            self._load_detail(self._selected)
            self._load_metrics(self._selected)

    def _auto_tick(self):
        self.refresh()
        self._auto_after_id = self.after(AUTO_REFRESH_MS, self._auto_tick)

    def _show_hosts(self, result):
        self._hosts, health = result
        self.summary_label.configure(text=summary_line(self._hosts, health))
        self.table.delete("1.0", "end")
        self._line_to_host = {}
        self.table.insert("end", header_line() + "\n", "header")
        for host in self._hosts:
            line = int(self.table.index("end-1c").split(".")[0])
            self._line_to_host[line] = host["name"]
            self.table.insert("end", host_line(host) + "\n", str(host.get("status")))
        self._highlight_selected()

    def _show_error(self, exc):
        self.summary_label.configure(text=f"node_manager 에 연결하지 못했습니다: {exc}")

    # ---------------------------------------------------------------- 선택·상세

    def _on_table_click(self, event):
        line = int(self.table.index(f"@{event.x},{event.y}").split(".")[0])
        name = self._line_to_host.get(line)
        if not name:
            return
        self._selected = name
        self.selected_label.configure(text=f"선택: {name}")
        for button in self.action_buttons:
            button.configure(state="normal")
        self._highlight_selected()
        self._load_detail(name)
        self._load_metrics(name)

    def _highlight_selected(self):
        self.table.tag_remove("selected", "1.0", "end")
        for line, name in self._line_to_host.items():
            if name == self._selected:
                self.table.tag_add("selected", f"{line}.0", f"{line}.end")

    def _load_detail(self, name):
        def show(detail):
            if name != self._selected:
                return
            self.detail.delete("1.0", "end")
            for text, tag in detail_lines(detail):
                self.detail.insert("end", text + "\n", tag)

        def fail(exc):
            self.detail.delete("1.0", "end")
            self.detail.insert("end", f"상세를 불러오지 못했습니다: {exc}\n", "fail")

        # 표 새로고침과 따로 돈다 — run_background 는 앞 요청을 버리므로 상세는 독립 스레드로 부른다.
        run_detached(self, task=lambda: nm.get_host(name), on_success=show, on_error=fail)

    def _load_metrics(self, name):
        if not name:
            return
        hours = self.charts.hours

        def show(series):
            if name == self._selected and hours == self.charts.hours:  # 그사이 다른 호스트·기간을 고르면 버린다
                self.charts.show(name, series)

        run_detached(self, task=lambda: nm.get_metrics(name, hours), on_success=show,
                     on_error=lambda exc: self.charts.show_message(f"그래프를 불러오지 못했습니다: {exc}"))

    # ---------------------------------------------------------------- 동작

    def _run_action(self, task, done_message):
        def done(_result):
            messagebox.showinfo("node_manager", done_message)
            self.refresh()

        run_detached(self, task=task, on_success=done,
                     on_error=lambda exc: messagebox.showerror("node_manager", f"실패: {exc}"))

    def on_check_all(self):
        self._run_action(nm.check_all, "전체 점검을 시작했습니다. 1~2분 뒤 새로고침하세요.")

    def on_check_selected(self):
        name = self._selected
        self.detail.delete("1.0", "end")
        self.detail.insert("end", f"{name} 점검 중... (부하 검사 포함, 최대 2분)\n", "default")
        self._run_action(lambda: nm.check_host(name, load_test=True), f"{name} 점검을 마쳤습니다.")

    def on_reboot(self, mode):
        name = self._selected
        how = "job 이 없으면 바로" if mode == "when_idle" else "지금 drain 하고 job 이 끝나면"
        if not messagebox.askyesno("재부팅", f"{name} 을(를) {how} 재부팅할까요?\n\n"
                                            "재부팅 뒤 점검을 통과해야 job 을 다시 받습니다."):
            return
        self._run_action(lambda: nm.request_reboot(name, mode), f"{name} 재부팅을 예약했습니다. 진행 상황은 표의 재부팅 칸에 나옵니다.")

    def on_cancel_reboot(self):
        name = self._selected
        if messagebox.askyesno("예약 취소", f"{name} 의 재부팅 예약을 취소할까요?"):
            self._run_action(lambda: nm.cancel_reboot(name), f"{name} 재부팅 예약을 취소했습니다.")

    def destroy(self):
        self.cancel_background_tasks()
        if self._auto_after_id is not None:
            self.after_cancel(self._auto_after_id)
        super().destroy()
