import customtkinter as ctk
from services.api_client import get_job_stats
import datetime
import threading

class ModelStatsFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.current_sort_key = "total"
        self.sort_reverse = True
        self.cached_stats = []

        # ------------------------
        # 🔹 상단 날짜 선택 패널
        # ------------------------
        control_frame = ctk.CTkFrame(self)
        control_frame.pack(fill="x", padx=10, pady=(10, 5))

        self.start_label = ctk.CTkLabel(control_frame, text="Start (YYYY-MM-DD):")
        self.start_label.grid(row=0, column=0, padx=5, pady=5)
        self.start_entry = ctk.CTkEntry(control_frame, width=120)
        self.start_entry.grid(row=0, column=1, padx=5, pady=5)

        self.end_label = ctk.CTkLabel(control_frame, text="End (YYYY-MM-DD):")
        self.end_label.grid(row=0, column=2, padx=5, pady=5)
        self.end_entry = ctk.CTkEntry(control_frame, width=120)
        self.end_entry.grid(row=0, column=3, padx=5, pady=5)

        # 빠른 선택 버튼
        self.last7_btn = ctk.CTkButton(control_frame, text="Last 7 days", width=80, command=lambda: self.set_range(7))
        self.last7_btn.grid(row=0, column=4, padx=5)
        self.last30_btn = ctk.CTkButton(control_frame, text="Last 30 days", width=80, command=lambda: self.set_range(30))
        self.last30_btn.grid(row=0, column=5, padx=5)
        self.all_btn = ctk.CTkButton(control_frame, text="All", width=80, command=self.set_all)
        self.all_btn.grid(row=0, column=6, padx=5)

        # 조회 버튼
        self.fetch_btn = ctk.CTkButton(control_frame, text="Fetch Stats", width=110, command=self.fetch_stats)
        self.fetch_btn.grid(row=0, column=7, padx=5)

        # ------------------------
        # 🔹 정렬 버튼 패널
        # ------------------------
        sort_frame = ctk.CTkFrame(self)
        sort_frame.pack(fill="x", padx=10, pady=(0, 5))

        ctk.CTkLabel(sort_frame, text="Sort by:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(10, 5))
        self.sort_buttons = {}
        for key, text in [
            ("total", "Total Runs"),
            ("avg_time", "Average Time"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
        ]:
            btn = ctk.CTkButton(sort_frame, text=text, width=100, command=lambda k=key: self.sort_by(k))
            btn.pack(side="left", padx=3)
            self.sort_buttons[key] = btn

        # ------------------------
        # 🔹 결과 표시 영역
        # ------------------------
        self.textbox = ctk.CTkTextbox(
            self, height=550, font=ctk.CTkFont(family="Consolas", size=13)
        )
        self.textbox.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        # 색상 태그
        self.textbox.tag_config("good", foreground="#00ff66")
        self.textbox.tag_config("warn", foreground="#ffcc00")
        self.textbox.tag_config("bad", foreground="#ff6666")
        self.textbox.tag_config("default", foreground="#cccccc")
        self.textbox.tag_config("vessl", foreground="#bb86fc")

        # 초기 정렬 표시 업데이트
        self._update_sort_buttons()

    # ------------------------
    # 🔹 날짜 설정 함수
    # ------------------------
    def set_range(self, days):
        end = datetime.date.today()
        start = end - datetime.timedelta(days=days)
        self.start_entry.delete(0, "end")
        self.start_entry.insert(0, start.isoformat())
        self.end_entry.delete(0, "end")
        self.end_entry.insert(0, end.isoformat())
        self.fetch_stats()

    def set_all(self):
        self.start_entry.delete(0, "end")
        self.start_entry.insert(0, "2000-01-01")
        self.end_entry.delete(0, "end")
        self.end_entry.insert(0, datetime.date.today().isoformat())
        self.fetch_stats()

    # ------------------------
    # 🔹 데이터 조회 (비동기)
    # ------------------------
    def fetch_stats(self):
        threading.Thread(target=self._fetch_stats_thread, daemon=True).start()

    def _fetch_stats_thread(self):
        try:
            self.textbox.delete("1.0", "end")
            self.textbox.insert("end", "Loading model statistics...\n", "default")

            start_str, end_str = self.start_entry.get().strip(), self.end_entry.get().strip()
            if not start_str or not end_str:
                self.textbox.insert("end", "\n⚠️ Please enter both start and end dates.\n", "warn")
                return

            start_iso = datetime.datetime.strptime(start_str, "%Y-%m-%d").isoformat()
            end_iso = (datetime.datetime.strptime(end_str, "%Y-%m-%d") + datetime.timedelta(days=1)).isoformat()

            stats = get_job_stats(start=start_iso, end=end_iso)
            self.cached_stats = stats
            self.display_stats()

        except Exception as e:
            self.textbox.delete("1.0", "end")
            self.textbox.insert("end", f"❌ Error fetching stats: {e}\n", "bad")

    # ------------------------
    # 🔹 데이터 표시 및 정렬
    # ------------------------
    def display_stats(self):
        if not self.cached_stats:
            self.textbox.delete("1.0", "end")
            self.textbox.insert("end", "No data available.\n", "default")
            return

        key = self.current_sort_key
        reverse = self.sort_reverse

        def key_func(item):
            if key == "avg_time":
                t = item.get("avg_time", "00:00:00")
                try:
                    h, m, s = map(int, t.split(":"))
                    return h * 3600 + m * 60 + s
                except:
                    return 0
            return item.get(key, 0)

        sorted_stats = sorted(self.cached_stats, key=key_func, reverse=reverse)

        self.textbox.delete("1.0", "end")
        # ✅ 열 간격 확장 + Complete 라벨 적용
        header = (
            f"{'Source':8} {'Model':18} {'Total':8} {'Complete':10} {'Fail':8} {'Cancel':10} "
            f"{'Avg':12} {'Min':12} {'Max':12}\n"
        )
        self.textbox.insert("end", header, "default")
        self.textbox.insert("end", "-" * 105 + "\n", "default")

        for s in sorted_stats:
            source = s.get("source", "slurm")
            source_label = source.upper() if "/" not in source else source.upper()
            success_rate = s["completed"] / s["total"] if s["total"] else 0
            if "vessl" in source:
                tag = "vessl"
            else:
                tag = "good" if success_rate > 0.9 else "warn" if success_rate > 0.6 else "bad"
            line = (
                f"{source_label[:8]:8} "
                f"{s['model'][:18]:18} "
                f"{s['total']:8} "
                f"{s['completed']:10} "
                f"{s['failed']:8} "
                f"{s['cancelled']:10} "
                f"{s['avg_time'][:12]:12} "
                f"{s['min_time'][:12]:12} "
                f"{s['max_time'][:12]:12}\n"
            )
            self.textbox.insert("end", line, tag)

        self._update_sort_buttons()

    # ------------------------
    # 🔹 정렬 로직
    # ------------------------
    def sort_by(self, key):
        if self.current_sort_key == key:
            self.sort_reverse = not self.sort_reverse
        else:
            self.current_sort_key = key
            self.sort_reverse = True
        self.display_stats()

    def _update_sort_buttons(self):
        """현재 정렬 상태를 ▲▼ 아이콘으로 표시"""
        for key, btn in self.sort_buttons.items():
            text = {
                "total": "Total Runs",
                "avg_time": "Average Time",
                "completed": "Completed",
                "failed": "Failed",
                "cancelled": "Cancelled"
            }[key]

            if key == self.current_sort_key:
                arrow = "▲" if not self.sort_reverse else "▼"
                btn.configure(text=f"{text} {arrow}")
            else:
                btn.configure(text=text)

    # ------------------------
    # 🔹 새로고침 (환경 전환 시 호출)
    # ------------------------
    def refresh(self):
        """대시보드의 전체 새로고침 시 호출"""
        self.textbox.delete("1.0", "end")
        self.textbox.insert(
            "end",
            "Model Stats tab has been reset.\n"
            "Please set a date range and click [Fetch Stats].\n",
            "default"
        )
        self.cached_stats = []
