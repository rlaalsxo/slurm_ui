import customtkinter as ctk

from services.api_client import get_job_stats
from ui.background import BackgroundTaskMixin
from ui.date_utils import read_date_range, set_all_range, set_recent_range
from ui.job_utils import cell, hms_to_seconds, safe_text, success_tag


class ModelStatsFrame(BackgroundTaskMixin, ctk.CTkFrame):
    SORT_LABELS = {
        "total": "Total Runs",
        "avg_time": "Average Time",
        "completed": "Completed",
        "failed": "Failed",
        "cancelled": "Cancelled",
    }

    def __init__(self, master):
        super().__init__(master)
        self._init_background_tasks()
        self.current_sort_key = "total"
        self.sort_reverse = True
        self.cached_stats = []

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
        self.textbox.tag_config("default", foreground="#cccccc")
        self.textbox.tag_config("vessl", foreground="#bb86fc")

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
            task=lambda: get_job_stats(start=start_iso, end=end_iso),
            on_start=lambda: self._set_loading("Loading model statistics..."),
            on_success=self._set_stats,
            on_error=lambda exc: self._show_error(f"Error fetching stats: {exc}"),
        )

    def _set_stats(self, stats):
        self.cached_stats = stats
        self.display_stats()

    def display_stats(self):
        if not self.cached_stats:
            self.textbox.delete("1.0", "end")
            self.textbox.insert("end", "No data available.\n", "default")
            return

        sorted_stats = sorted(
            self.cached_stats,
            key=self._sort_value,
            reverse=self.sort_reverse,
        )

        self.textbox.delete("1.0", "end")
        header = (
            f"{'Model':18} {'Total':8} {'Complete':10} {'Fail':8} {'Cancel':10} "
            f"{'Avg':12} {'Min':12} {'Max':12}\n"
        )
        self.textbox.insert("end", header, "default")
        self.textbox.insert("end", "-" * 96 + "\n", "default")

        for stat in sorted_stats:
            self.textbox.insert("end", self._format_stat_line(stat), self._stat_tag(stat))

        self._update_sort_buttons()

    def _sort_value(self, item):
        if self.current_sort_key == "avg_time":
            return hms_to_seconds(item.get("avg_time"))
        return item.get(self.current_sort_key, 0)

    def _stat_tag(self, stat):
        if "vessl" in safe_text(stat.get("source"), "slurm").lower():
            return "vessl"
        return success_tag(stat.get("completed", 0), stat.get("total", 0))

    def _format_stat_line(self, stat):
        return (
            f"{cell(stat.get('model'), 18)} "
            f"{stat.get('total', 0):8} "
            f"{stat.get('completed', 0):10} "
            f"{stat.get('failed', 0):8} "
            f"{stat.get('cancelled', 0):10} "
            f"{cell(stat.get('avg_time'), 12)} "
            f"{cell(stat.get('min_time'), 12)} "
            f"{cell(stat.get('max_time'), 12)}\n"
        )

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
            "Model Stats tab has been reset.\n"
            "Please set a date range and click [Fetch Stats].\n",
            "default",
        )
        self.cached_stats = []
