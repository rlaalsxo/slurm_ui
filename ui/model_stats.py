import customtkinter as ctk

from services.api_client import get_jobs
from ui.background import BackgroundTaskMixin, run_detached
from ui.date_utils import read_date_range, set_all_range, set_recent_range
from ui.job_utils import (
    aggregate_model_accounts,
    aggregate_model_stats,
    cell,
    format_seconds,
    safe_text,
    success_tag,
)


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
        self._model_line_map = {}
        self._last_range = None
        self._raw_jobs_cache = None

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

        self.textbox.bind("<Double-Button-1>", self._on_double_click)

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

        self._last_range = (start_iso, end_iso)
        self._raw_jobs_cache = None

        self.run_background(
            task=lambda: get_jobs(start=start_iso, end=end_iso),
            on_start=lambda: self._set_loading("Loading model statistics..."),
            on_success=self._set_stats,
            on_error=lambda exc: self._show_error(f"Error fetching stats: {exc}"),
        )

    def _set_stats(self, jobs):
        # raw jobs를 캐시(유저 드릴다운이 재사용)하고 모델별로 집계한다.
        self._raw_jobs_cache = jobs
        self.cached_stats = aggregate_model_stats(jobs)
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
        self._model_line_map = {}

        header = (
            f"{'Model':18} {'Total':8} {'Complete':10} {'Fail':8} {'Cancel':10} "
            f"{'Avg':12} {'Min':12} {'Max':12}\n"
        )
        self.textbox.insert("end", header, "default")
        self.textbox.insert("end", "-" * 96 + "\n", "default")
        self.textbox.insert("end", "  (Double-click a model row to see per-user usage)\n\n", "default")

        for stat in sorted_stats:
            line_idx = int(self.textbox.index("end-1c").split(".")[0])
            self._model_line_map[line_idx] = stat.get("model")
            self.textbox.insert("end", self._format_stat_line(stat), self._stat_tag(stat))

        self._update_sort_buttons()

    def _sort_value(self, item):
        if self.current_sort_key == "avg_time":
            return item.get("avg_sec", 0)
        return item.get(self.current_sort_key, 0)

    def _stat_tag(self, stat):
        return success_tag(stat.get("completed", 0), stat.get("total", 0))

    def _format_stat_line(self, stat):
        return (
            f"{cell(stat.get('model'), 18)} "
            f"{stat.get('total', 0):8} "
            f"{stat.get('completed', 0):10} "
            f"{stat.get('failed', 0):8} "
            f"{stat.get('cancelled', 0):10} "
            f"{format_seconds(stat.get('avg_sec', 0)):12} "
            f"{format_seconds(stat.get('min_sec', 0)):12} "
            f"{format_seconds(stat.get('max_sec', 0)):12}\n"
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

    def _on_double_click(self, event):
        index = self.textbox.index(f"@{event.x},{event.y}")
        line_num = int(index.split(".")[0])
        model = self._model_line_map.get(line_num)
        if not model or not self._last_range:
            return
        self._show_account_stats_popup(model)

    def _show_account_stats_popup(self, model):
        popup = ctk.CTkToplevel(self)
        popup.title(f"Account Stats: {model}")
        popup.geometry("720x560")
        popup.attributes("-topmost", True)
        popup.after(300, lambda: popup.attributes("-topmost", False))

        textbox = ctk.CTkTextbox(popup, font=ctk.CTkFont(family="Consolas", size=13))
        textbox.pack(fill="both", expand=True, padx=10, pady=10)

        textbox.tag_config("good", foreground="#00ff66")
        textbox.tag_config("warn", foreground="#ffcc00")
        textbox.tag_config("bad", foreground="#ff6666")
        textbox.tag_config("title", foreground="#66aaff")
        textbox.tag_config("default", foreground="#cccccc")

        textbox.insert("end", f"Loading per-account stats for {model}...", "default")

        if self._raw_jobs_cache is not None:
            self._render_account_stats(textbox, model, self._raw_jobs_cache)
            return

        start_iso, end_iso = self._last_range
        run_detached(
            popup,
            task=lambda: get_jobs(start=start_iso, end=end_iso),
            on_success=lambda jobs: self._on_raw_jobs_loaded(textbox, model, jobs),
            on_error=lambda exc: self._render_account_stats_error(textbox, exc),
        )

    def _on_raw_jobs_loaded(self, textbox, model, jobs):
        self._raw_jobs_cache = jobs
        self._render_account_stats(textbox, model, jobs)

    def _render_account_stats(self, textbox, model, jobs):
        textbox.delete("1.0", "end")

        rows = sorted(
            aggregate_model_accounts(jobs, model),
            key=lambda item: item["total"],
            reverse=True,
        )

        textbox.insert("end", f"  Model: {model}\n", "title")
        textbox.insert("end", "  (min / max / avg are over COMPLETED jobs)\n\n", "default")

        header = (
            f"{'Account':16} {'Total':8} {'Complete':10} {'Fail':8} {'Cancel':10} "
            f"{'Avg':12} {'Min':12} {'Max':12}\n"
        )
        textbox.insert("end", header, "default")
        textbox.insert("end", "-" * 92 + "\n", "default")

        if not rows:
            textbox.insert("end", "\nNo jobs found for this model.\n", "default")
            return

        for row in rows:
            textbox.insert("end", self._format_account_line(row), success_tag(row["completed"], row["total"]))

    def _format_account_line(self, row):
        return (
            f"{cell(row['account'], 16)} "
            f"{row['total']:8} "
            f"{row['completed']:10} "
            f"{row['failed']:8} "
            f"{row['cancelled']:10} "
            f"{format_seconds(row['avg_sec']):12} "
            f"{format_seconds(row['min_sec']):12} "
            f"{format_seconds(row['max_sec']):12}\n"
        )

    def _render_account_stats_error(self, textbox, exc):
        textbox.delete("1.0", "end")
        textbox.insert("end", f"Error fetching per-account stats: {exc}", "bad")

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
        self._model_line_map = {}
        self._last_range = None
        self._raw_jobs_cache = None
