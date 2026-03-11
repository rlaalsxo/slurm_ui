# ui/account_stats.py
import customtkinter as ctk
from services.api_client import get_jobs
import datetime
import threading
from collections import defaultdict


class AccountStatsFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.current_sort_key = "total"
        self.sort_reverse = True
        self.cached_accounts = []  # 집계된 account 데이터
        self.raw_jobs = []  # 원본 job 리스트

        # ------------------------
        # 상단 날짜 선택 패널
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

        self.last7_btn = ctk.CTkButton(control_frame, text="Last 7 days", width=80, command=lambda: self.set_range(7))
        self.last7_btn.grid(row=0, column=4, padx=5)
        self.last30_btn = ctk.CTkButton(control_frame, text="Last 30 days", width=80, command=lambda: self.set_range(30))
        self.last30_btn.grid(row=0, column=5, padx=5)
        self.all_btn = ctk.CTkButton(control_frame, text="All", width=80, command=self.set_all)
        self.all_btn.grid(row=0, column=6, padx=5)

        self.fetch_btn = ctk.CTkButton(control_frame, text="Fetch Stats", width=110, command=self.fetch_stats)
        self.fetch_btn.grid(row=0, column=7, padx=5)

        # ------------------------
        # 정렬 버튼 패널
        # ------------------------
        sort_frame = ctk.CTkFrame(self)
        sort_frame.pack(fill="x", padx=10, pady=(0, 5))

        ctk.CTkLabel(sort_frame, text="Sort by:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(10, 5))
        self.sort_buttons = {}
        for key, text in [
            ("total", "Total Jobs"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
            ("total_time", "Total Time"),
        ]:
            btn = ctk.CTkButton(sort_frame, text=text, width=100, command=lambda k=key: self.sort_by(k))
            btn.pack(side="left", padx=3)
            self.sort_buttons[key] = btn

        # ------------------------
        # 결과 표시 영역
        # ------------------------
        self.textbox = ctk.CTkTextbox(
            self, height=550, font=ctk.CTkFont(family="Consolas", size=13)
        )
        self.textbox.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.textbox.tag_config("good", foreground="#00ff66")
        self.textbox.tag_config("warn", foreground="#ffcc00")
        self.textbox.tag_config("bad", foreground="#ff6666")
        self.textbox.tag_config("info", foreground="#66aaff")
        self.textbox.tag_config("default", foreground="#cccccc")
        self.textbox.tag_config("clickable", foreground="#66aaff")

        # 클릭 이벤트 바인딩
        self.textbox.bind("<Button-1>", self._on_click)
        # account 행 위치 저장 (line_number -> account_name)
        self._account_line_map = {}

        self._update_sort_buttons()

    # ------------------------
    # 날짜 설정
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
    # 데이터 조회 (비동기)
    # ------------------------
    def fetch_stats(self):
        threading.Thread(target=self._fetch_stats_thread, daemon=True).start()

    def _fetch_stats_thread(self):
        try:
            self.textbox.delete("1.0", "end")
            self.textbox.insert("end", "Loading account statistics...\n", "default")

            start_str = self.start_entry.get().strip()
            end_str = self.end_entry.get().strip()
            if not start_str or not end_str:
                self.textbox.delete("1.0", "end")
                self.textbox.insert("end", "Please enter both start and end dates.\n", "bad")
                return

            start_iso = datetime.datetime.strptime(start_str, "%Y-%m-%d").isoformat()
            end_iso = (datetime.datetime.strptime(end_str, "%Y-%m-%d") + datetime.timedelta(days=1)).isoformat()

            jobs = get_jobs(start=start_iso, end=end_iso)
            self.raw_jobs = jobs
            self.cached_accounts = self._aggregate_by_account(jobs)
            self.after(0, self.display_stats)

        except Exception as e:
            self.after(0, lambda: self._show_error(str(e)))

    def _show_error(self, msg):
        self.textbox.delete("1.0", "end")
        self.textbox.insert("end", f"Error fetching stats: {msg}\n", "bad")

    # ------------------------
    # 집계 로직
    # ------------------------
    @staticmethod
    def _extract_model(job_name):
        if not job_name or "_" not in job_name:
            return job_name or "unknown"
        return job_name.rsplit("_", 1)[0]

    @staticmethod
    def _calc_duration(start_str, end_str):
        if not start_str or not end_str or start_str == "-" or end_str == "-":
            return 0
        try:
            fmt1 = "%Y-%m-%dT%H:%M:%S"
            fmt2 = "%Y-%m-%d %H:%M:%S"
            for fmt in (fmt1, fmt2):
                try:
                    s = datetime.datetime.strptime(start_str[:19], fmt)
                    e = datetime.datetime.strptime(end_str[:19], fmt)
                    return max(0, (e - s).total_seconds())
                except ValueError:
                    continue
            return 0
        except Exception:
            return 0

    def _aggregate_by_account(self, jobs):
        accounts = defaultdict(lambda: {
            "total": 0, "completed": 0, "failed": 0, "cancelled": 0,
            "total_seconds": 0,
            "models": defaultdict(int),
            "nodes": defaultdict(lambda: {"jobs": 0, "seconds": 0}),
        })

        for job in jobs:
            acct = job.get("account", "unknown") or "unknown"
            state = (job.get("state", "") or "").upper()
            a = accounts[acct]

            a["total"] += 1
            if state in ("COMPLETED", "CD"):
                a["completed"] += 1
            elif state in ("FAILED", "F"):
                a["failed"] += 1
            elif state.startswith("CANCELLED") or state == "CA":
                a["cancelled"] += 1

            duration = self._calc_duration(job.get("start"), job.get("end"))
            a["total_seconds"] += duration

            model = self._extract_model(job.get("job_name"))
            a["models"][model] += 1

            node = job.get("node_list", "-") or "-"
            a["nodes"][node]["jobs"] += 1
            a["nodes"][node]["seconds"] += duration

        result = []
        for name, data in accounts.items():
            result.append({
                "account": name,
                "total": data["total"],
                "completed": data["completed"],
                "failed": data["failed"],
                "cancelled": data["cancelled"],
                "total_seconds": data["total_seconds"],
                "models": dict(data["models"]),
                "nodes": {k: dict(v) for k, v in data["nodes"].items()},
            })
        return result

    # ------------------------
    # 표시
    # ------------------------
    @staticmethod
    def _format_time(seconds):
        seconds = int(seconds)
        if seconds <= 0:
            return "0:00:00"
        days = seconds // 86400
        h = (seconds % 86400) // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if days > 0:
            return f"{days}d {h:02d}:{m:02d}:{s:02d}"
        return f"{h}:{m:02d}:{s:02d}"

    def display_stats(self):
        if not self.cached_accounts:
            self.textbox.delete("1.0", "end")
            self.textbox.insert("end", "No data available.\n", "default")
            return

        key = self.current_sort_key
        reverse = self.sort_reverse

        def key_func(item):
            if key == "total_time":
                return item.get("total_seconds", 0)
            return item.get(key, 0)

        sorted_accounts = sorted(self.cached_accounts, key=key_func, reverse=reverse)

        self.textbox.delete("1.0", "end")
        self._account_line_map = {}

        header = (
            f"{'Account':<15} {'Total':>8} {'Complete':>10} {'Fail':>8} "
            f"{'Cancel':>10} {'Total Time':>14}\n"
        )
        self.textbox.insert("end", header, "default")
        self.textbox.insert("end", "-" * 70 + "\n", "default")
        self.textbox.insert("end", "  (Click an account row to see details)\n\n", "info")

        for acct in sorted_accounts:
            success_rate = acct["completed"] / acct["total"] if acct["total"] else 0
            tag = "good" if success_rate > 0.9 else "warn" if success_rate > 0.6 else "bad"

            # 현재 줄 번호 기록
            line_idx = self.textbox.index("end-1c").split(".")[0]
            self._account_line_map[int(line_idx)] = acct["account"]

            line = (
                f"{acct['account'][:15]:<15} {acct['total']:>8} {acct['completed']:>10} "
                f"{acct['failed']:>8} {acct['cancelled']:>10} "
                f"{self._format_time(acct['total_seconds']):>14}\n"
            )
            self.textbox.insert("end", line, tag)

        self._update_sort_buttons()

    # ------------------------
    # 클릭 → 상세 팝업
    # ------------------------
    def _on_click(self, event):
        index = self.textbox.index(f"@{event.x},{event.y}")
        line_num = int(index.split(".")[0])
        account_name = self._account_line_map.get(line_num)
        if account_name:
            self._show_detail_popup(account_name)

    def _show_detail_popup(self, account_name):
        acct_data = None
        for a in self.cached_accounts:
            if a["account"] == account_name:
                acct_data = a
                break
        if not acct_data:
            return

        popup = ctk.CTkToplevel(self)
        popup.title(f"Account Details: {account_name}")
        popup.geometry("600x500")
        popup.attributes("-topmost", True)
        popup.after(300, lambda: popup.attributes("-topmost", False))

        textbox = ctk.CTkTextbox(popup, font=ctk.CTkFont(family="Consolas", size=13))
        textbox.pack(fill="both", expand=True, padx=10, pady=10)

        textbox.tag_config("title", foreground="#66aaff")
        textbox.tag_config("good", foreground="#00ff66")
        textbox.tag_config("default", foreground="#cccccc")
        textbox.tag_config("warn", foreground="#ffcc00")

        # 요약
        textbox.insert("end", f"  Account: {account_name}\n", "title")
        textbox.insert("end", f"  Total Jobs: {acct_data['total']}    ", "default")
        textbox.insert("end", f"Completed: {acct_data['completed']}    ", "good")
        textbox.insert("end", f"Failed: {acct_data['failed']}    ", "warn")
        textbox.insert("end", f"Cancelled: {acct_data['cancelled']}\n", "default")
        textbox.insert("end", f"  Total Time: {self._format_time(acct_data['total_seconds'])}\n", "default")
        textbox.insert("end", "\n" + "=" * 55 + "\n\n", "default")

        # Top 5 모델
        textbox.insert("end", "  Top 5 Models\n", "title")
        textbox.insert("end", f"  {'Model':<30} {'Jobs':>8}\n", "default")
        textbox.insert("end", "  " + "-" * 40 + "\n", "default")

        sorted_models = sorted(acct_data["models"].items(), key=lambda x: x[1], reverse=True)[:5]
        for model, count in sorted_models:
            textbox.insert("end", f"  {model[:30]:<30} {count:>8}\n", "good")

        textbox.insert("end", "\n" + "=" * 55 + "\n\n", "default")

        # 노드별 점유 시간
        textbox.insert("end", "  Node Usage\n", "title")
        textbox.insert("end", f"  {'Node':<20} {'Jobs':>8} {'Total Time':>14}\n", "default")
        textbox.insert("end", "  " + "-" * 45 + "\n", "default")

        sorted_nodes = sorted(acct_data["nodes"].items(), key=lambda x: x[1]["seconds"], reverse=True)
        for node, info in sorted_nodes:
            textbox.insert(
                "end",
                f"  {node[:20]:<20} {info['jobs']:>8} {self._format_time(info['seconds']):>14}\n",
                "default"
            )

        textbox.configure(state="disabled")

    # ------------------------
    # 정렬
    # ------------------------
    def sort_by(self, key):
        if self.current_sort_key == key:
            self.sort_reverse = not self.sort_reverse
        else:
            self.current_sort_key = key
            self.sort_reverse = True
        self.display_stats()

    def _update_sort_buttons(self):
        labels = {
            "total": "Total Jobs",
            "completed": "Completed",
            "failed": "Failed",
            "cancelled": "Cancelled",
            "total_time": "Total Time",
        }
        for key, btn in self.sort_buttons.items():
            text = labels[key]
            if key == self.current_sort_key:
                arrow = "▲" if not self.sort_reverse else "▼"
                btn.configure(text=f"{text} {arrow}")
            else:
                btn.configure(text=text)

    # ------------------------
    # 새로고침
    # ------------------------
    def refresh(self):
        self.textbox.delete("1.0", "end")
        self.textbox.insert(
            "end",
            "Account Stats tab has been reset.\n"
            "Please set a date range and click [Fetch Stats].\n",
            "default"
        )
        self.cached_accounts = []
        self.raw_jobs = []
        self._account_line_map = {}
