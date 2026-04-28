import customtkinter as ctk

from services.api_client import get_jobs
from ui.background import BackgroundTaskMixin
from ui.date_utils import read_date_range, set_all_range, set_recent_range
from ui.job_utils import aggregate_jobs_by_account, cell, format_seconds, success_tag


class AccountStatsFrame(BackgroundTaskMixin, ctk.CTkFrame):
    SORT_LABELS = {
        "total": "Total Jobs",
        "completed": "Completed",
        "failed": "Failed",
        "cancelled": "Cancelled",
        "total_time": "Total Time",
    }

    def __init__(self, master):
        super().__init__(master)
        self._init_background_tasks()
        self.current_sort_key = "total"
        self.sort_reverse = True
        self.cached_accounts = []
        self.raw_jobs = []
        self._account_line_map = {}

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

        sort_frame = ctk.CTkFrame(self)
        sort_frame.pack(fill="x", padx=10, pady=(0, 5))

        ctk.CTkLabel(sort_frame, text="Sort by:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(10, 5))
        self.sort_buttons = {}
        for key, text in self.SORT_LABELS.items():
            btn = ctk.CTkButton(sort_frame, text=text, width=140, command=lambda k=key: self.sort_by(k))
            btn.pack(side="left", padx=3)
            self.sort_buttons[key] = btn

        self.textbox = ctk.CTkTextbox(
            self,
            height=550,
            font=ctk.CTkFont(family="Consolas", size=13),
        )
        self.textbox.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.textbox.tag_config("good", foreground="#00ff66")
        self.textbox.tag_config("warn", foreground="#ffcc00")
        self.textbox.tag_config("bad", foreground="#ff6666")
        self.textbox.tag_config("info", foreground="#66aaff")
        self.textbox.tag_config("default", foreground="#cccccc")

        self.textbox.bind("<Button-1>", self._on_click)
        self._update_sort_buttons()

    def set_range(self, days):
        set_recent_range(self.start_entry, self.end_entry, days)
        self.fetch_stats()

    def set_all(self):
        set_all_range(self.start_entry, self.end_entry)
        self.fetch_stats()

    def fetch_stats(self):
        try:
            start_iso, end_iso = read_date_range(self.start_entry, self.end_entry)
        except ValueError as exc:
            self._show_error(str(exc))
            return

        self.run_background(
            task=lambda: get_jobs(start=start_iso, end=end_iso),
            on_start=lambda: self._set_loading("Loading account statistics..."),
            on_success=self._set_jobs,
            on_error=lambda exc: self._show_error(f"Error fetching stats: {exc}"),
        )

    def _set_jobs(self, jobs):
        self.raw_jobs = jobs
        self.cached_accounts = aggregate_jobs_by_account(jobs)
        self.display_stats()

    def display_stats(self):
        if not self.cached_accounts:
            self.textbox.delete("1.0", "end")
            self.textbox.insert("end", "No data available.\n", "default")
            return

        sorted_accounts = sorted(
            self.cached_accounts,
            key=self._sort_value,
            reverse=self.sort_reverse,
        )

        self.textbox.delete("1.0", "end")
        self._account_line_map = {}

        header = (
            f"{'Account':<15} {'Total':>8} {'Complete':>10} {'Fail':>8} "
            f"{'Cancel':>10} {'Total Time':>14}\n"
        )
        self.textbox.insert("end", header, "default")
        self.textbox.insert("end", "-" * 70 + "\n", "default")
        self.textbox.insert("end", "  (Click an account row to see details)\n\n", "info")

        for account in sorted_accounts:
            line_idx = int(self.textbox.index("end-1c").split(".")[0])
            self._account_line_map[line_idx] = account["account"]
            self.textbox.insert("end", self._format_account_line(account), success_tag(account["completed"], account["total"]))

        self._update_sort_buttons()

    def _sort_value(self, item):
        if self.current_sort_key == "total_time":
            return item.get("total_seconds", 0)
        return item.get(self.current_sort_key, 0)

    def _format_account_line(self, account):
        return (
            f"{cell(account['account'], 15)} "
            f"{account['total']:>8} "
            f"{account['completed']:>10} "
            f"{account['failed']:>8} "
            f"{account['cancelled']:>10} "
            f"{format_seconds(account['total_seconds']):>14}\n"
        )

    def _on_click(self, event):
        index = self.textbox.index(f"@{event.x},{event.y}")
        line_num = int(index.split(".")[0])
        account_name = self._account_line_map.get(line_num)
        if account_name:
            self._show_detail_popup(account_name)

    def _show_detail_popup(self, account_name):
        account = next((item for item in self.cached_accounts if item["account"] == account_name), None)
        if not account:
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

        textbox.insert("end", f"  Account: {account_name}\n", "title")
        textbox.insert("end", f"  Total Jobs: {account['total']}    ", "default")
        textbox.insert("end", f"Completed: {account['completed']}    ", "good")
        textbox.insert("end", f"Failed: {account['failed']}    ", "warn")
        textbox.insert("end", f"Cancelled: {account['cancelled']}\n", "default")
        textbox.insert("end", f"  Total Time: {format_seconds(account['total_seconds'])}\n", "default")
        textbox.insert("end", "\n" + "=" * 55 + "\n\n", "default")

        textbox.insert("end", "  Top 5 Models\n", "title")
        textbox.insert("end", f"  {'Model':<30} {'Jobs':>8}\n", "default")
        textbox.insert("end", "  " + "-" * 40 + "\n", "default")
        for model, count in sorted(account["models"].items(), key=lambda item: item[1], reverse=True)[:5]:
            textbox.insert("end", f"  {cell(model, 30)} {count:>8}\n", "good")

        textbox.insert("end", "\n" + "=" * 55 + "\n\n", "default")
        textbox.insert("end", "  Node Usage\n", "title")
        textbox.insert("end", f"  {'Node':<20} {'Jobs':>8} {'Total Time':>14}\n", "default")
        textbox.insert("end", "  " + "-" * 45 + "\n", "default")
        for node, info in sorted(account["nodes"].items(), key=lambda item: item[1]["seconds"], reverse=True):
            textbox.insert(
                "end",
                f"  {cell(node, 20)} {info['jobs']:>8} {format_seconds(info['seconds']):>14}\n",
                "default",
            )

        textbox.configure(state="disabled")

    def sort_by(self, key):
        if self.current_sort_key == key:
            self.sort_reverse = not self.sort_reverse
        else:
            self.current_sort_key = key
            self.sort_reverse = True
        self.display_stats()

    def _update_sort_buttons(self):
        for key, btn in self.sort_buttons.items():
            text = self.SORT_LABELS[key]
            if key == self.current_sort_key:
                direction = "desc" if self.sort_reverse else "asc"
                btn.configure(text=f"{text} {direction}")
            else:
                btn.configure(text=text)

    def _set_loading(self, message):
        self.textbox.delete("1.0", "end")
        self.textbox.insert("end", f"{message}\n", "default")

    def _show_error(self, message):
        self.textbox.delete("1.0", "end")
        self.textbox.insert("end", f"{message}\n", "bad")

    def refresh(self):
        self.cancel_background_tasks()
        self.textbox.delete("1.0", "end")
        self.textbox.insert(
            "end",
            "Account Stats tab has been reset.\n"
            "Please set a date range and click [Fetch Stats].\n",
            "default",
        )
        self.cached_accounts = []
        self.raw_jobs = []
        self._account_line_map = {}
