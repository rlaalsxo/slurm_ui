import customtkinter as ctk

from services.api_client import get_job_log, get_jobs
from ui.background import BackgroundTaskMixin, run_detached
from ui.date_utils import read_date_range, set_recent_range
from ui.job_utils import (
    ALL_ACCOUNTS,
    ALL_MODELS,
    cell,
    extract_model,
    format_seconds,
    is_completed,
    is_failed,
    job_elapsed_seconds,
    normalized_state,
    safe_text,
    source_label,
)


class JobsHistoryFrame(BackgroundTaskMixin, ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self._init_background_tasks()
        self._jobs_cache = []
        self._job_line_map = {}
        self._model_filter_values = [ALL_MODELS]
        self._account_filter_values = [ALL_ACCOUNTS]

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

        self.last7_button = ctk.CTkButton(control_frame, text="Last 7 days", width=80, command=lambda: self.set_range(7))
        self.last7_button.grid(row=0, column=4, padx=5)
        self.last30_button = ctk.CTkButton(control_frame, text="Last 30 days", width=80, command=lambda: self.set_range(30))
        self.last30_button.grid(row=0, column=5, padx=5)
        self.all_button = ctk.CTkButton(control_frame, text="All", width=80, command=lambda: self.set_range(365))
        self.all_button.grid(row=0, column=6, padx=5)

        self.fetch_button = ctk.CTkButton(control_frame, text="Fetch", width=100, command=self.fetch_history)
        self.fetch_button.grid(row=0, column=7, padx=10, pady=5)

        self.model_label = ctk.CTkLabel(control_frame, text="Model:")
        self.model_label.grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.model_filter_var = ctk.StringVar(value=ALL_MODELS)
        self.model_filter_menu = ctk.CTkOptionMenu(
            control_frame,
            values=[ALL_MODELS],
            variable=self.model_filter_var,
            width=180,
            command=lambda _: self.display_history(),
        )
        self.model_filter_menu.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        self._bind_model_filter_wheel()

        self.account_label = ctk.CTkLabel(control_frame, text="Account:")
        self.account_label.grid(row=1, column=2, padx=5, pady=5, sticky="e")
        self.account_filter_var = ctk.StringVar(value=ALL_ACCOUNTS)
        self.account_filter_menu = ctk.CTkOptionMenu(
            control_frame,
            values=[ALL_ACCOUNTS],
            variable=self.account_filter_var,
            width=180,
            command=lambda _: self.display_history(),
        )
        self.account_filter_menu.grid(row=1, column=3, padx=5, pady=5, sticky="w")
        self._bind_account_filter_wheel()

        self.textbox = ctk.CTkTextbox(
            self,
            height=550,
            font=ctk.CTkFont(family="Consolas", size=13),
        )
        self.textbox.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.textbox.tag_config("completed", foreground="#00ff66")
        self.textbox.tag_config("failed", foreground="#ff6666")
        self.textbox.tag_config("cancelled", foreground="#ffcc00")
        self.textbox.tag_config("default", foreground="#cccccc")
        self.textbox.tag_config("vessl_completed", foreground="#bb86fc")
        self.textbox.tag_config("vessl_failed", foreground="#cf6679")
        self.textbox.tag_config("vessl_default", foreground="#9966cc")

        self.textbox.bind("<Double-Button-1>", self._on_double_click)

    def set_range(self, days):
        set_recent_range(self.start_entry, self.end_entry, days)
        self.fetch_history()

    def fetch_history(self):
        try:
            start_iso, end_iso = read_date_range(self.start_entry, self.end_entry)
        except ValueError as exc:
            self._show_error(str(exc))
            return

        self.run_background(
            task=lambda: get_jobs(start=start_iso, end=end_iso),
            on_start=lambda: self._set_loading("Loading job history data..."),
            on_success=self._set_jobs,
            on_error=lambda exc: self._show_error(f"Error fetching job history: {exc}"),
        )

    def _set_jobs(self, jobs):
        self._jobs_cache = jobs
        self._update_model_filter_options(jobs)
        self._update_account_filter_options(jobs)
        self.display_history()

    def _update_model_filter_options(self, jobs):
        current_model = self.model_filter_var.get()
        models = sorted({extract_model(job.get("job_name")) for job in jobs})
        values = [ALL_MODELS] + models

        self._model_filter_values = values
        self.model_filter_menu.configure(values=values)
        self.model_filter_var.set(current_model if current_model in values else ALL_MODELS)

    def _update_account_filter_options(self, jobs):
        current_account = self.account_filter_var.get()
        accounts = sorted({safe_text(job.get("account"), "unknown") for job in jobs})
        values = [ALL_ACCOUNTS] + accounts

        self._account_filter_values = values
        self.account_filter_menu.configure(values=values)
        self.account_filter_var.set(current_account if current_account in values else ALL_ACCOUNTS)

    def _bind_model_filter_wheel(self):
        self.model_filter_menu.bind("<MouseWheel>", self._on_model_filter_wheel)
        self.model_filter_menu.bind("<Button-4>", self._on_model_filter_wheel)
        self.model_filter_menu.bind("<Button-5>", self._on_model_filter_wheel)
        self.model_label.bind("<MouseWheel>", self._on_model_filter_wheel)
        self.model_label.bind("<Button-4>", self._on_model_filter_wheel)
        self.model_label.bind("<Button-5>", self._on_model_filter_wheel)

    def _on_model_filter_wheel(self, event):
        if len(self._model_filter_values) <= 1:
            return "break"

        current_model = self.model_filter_var.get()
        try:
            index = self._model_filter_values.index(current_model)
        except ValueError:
            index = 0

        step = 1 if getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0 else -1
        next_index = (index + step) % len(self._model_filter_values)
        self.model_filter_var.set(self._model_filter_values[next_index])
        self.display_history()
        return "break"

    def _bind_account_filter_wheel(self):
        self.account_filter_menu.bind("<MouseWheel>", self._on_account_filter_wheel)
        self.account_filter_menu.bind("<Button-4>", self._on_account_filter_wheel)
        self.account_filter_menu.bind("<Button-5>", self._on_account_filter_wheel)
        self.account_label.bind("<MouseWheel>", self._on_account_filter_wheel)
        self.account_label.bind("<Button-4>", self._on_account_filter_wheel)
        self.account_label.bind("<Button-5>", self._on_account_filter_wheel)

    def _on_account_filter_wheel(self, event):
        if len(self._account_filter_values) <= 1:
            return "break"

        current_account = self.account_filter_var.get()
        try:
            index = self._account_filter_values.index(current_account)
        except ValueError:
            index = 0

        step = 1 if getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0 else -1
        next_index = (index + step) % len(self._account_filter_values)
        self.account_filter_var.set(self._account_filter_values[next_index])
        self.display_history()
        return "break"

    def _get_filtered_jobs(self):
        selected_model = self.model_filter_var.get()
        selected_account = self.account_filter_var.get()
        return [
            job for job in self._jobs_cache
            if (selected_model == ALL_MODELS or extract_model(job.get("job_name")) == selected_model)
            and (selected_account == ALL_ACCOUNTS or safe_text(job.get("account"), "unknown") == selected_account)
        ]

    def display_history(self):
        jobs = self._get_filtered_jobs()

        self.textbox.delete("1.0", "end")
        self._job_line_map = {}

        header = (
            f"{'Source':8} {'JobID':10} {'Name':20} {'User':10} {'Account':10} "
            f"{'State':10} {'Start':19} {'End':19} {'Elapsed':13} {'Node':12}\n"
        )
        self.textbox.insert("end", header, "default")
        self.textbox.insert("end", "-" * 149 + "\n", "default")

        active_filters = []
        if self.model_filter_var.get() != ALL_MODELS:
            active_filters.append(f"Model={self.model_filter_var.get()}")
        if self.account_filter_var.get() != ALL_ACCOUNTS:
            active_filters.append(f"Account={self.account_filter_var.get()}")
        if active_filters:
            self.textbox.insert(
                "end",
                f"  Filter: {', '.join(active_filters)} ({len(jobs)}/{len(self._jobs_cache)} jobs)\n",
                "default",
            )
        self.textbox.insert("end", "  (Double-click a COMPLETED/FAILED job to view log)\n\n", "default")

        for job in sorted(jobs, key=lambda item: safe_text(item.get("start"), ""), reverse=True):
            line_idx = int(self.textbox.index("end-1c").split(".")[0])
            self._job_line_map[line_idx] = job
            self.textbox.insert("end", self._format_job_line(job), self._get_state_tag(job))

        if not jobs:
            self.textbox.insert("end", "\nNo jobs found for the selected period and model filter.\n", "default")

    def _format_job_line(self, job):
        return (
            f"{source_label(job.get('source')):8} "
            f"{cell(job.get('job_id'), 10)} "
            f"{cell(job.get('job_name'), 20)} "
            f"{cell(job.get('user'), 10)} "
            f"{cell(job.get('account'), 10)} "
            f"{cell(job.get('state'), 10)} "
            f"{cell(job.get('start'), 19)} "
            f"{cell(job.get('end'), 19)} "
            f"{cell(format_seconds(job_elapsed_seconds(job)), 13)} "
            f"{cell(job.get('node_list'), 12)}\n"
        )

    def _get_state_tag(self, job):
        state = normalized_state(job.get("state"))
        source = safe_text(job.get("source"), "slurm").lower()

        if source == "vessl":
            if is_completed(state):
                return "vessl_completed"
            if is_failed(state):
                return "vessl_failed"
            return "vessl_default"

        if is_completed(state):
            return "completed"
        if is_failed(state):
            return "failed"
        if state.startswith("CANCELLED") or state == "CA":
            return "cancelled"
        return "default"

    def _on_double_click(self, event):
        index = self.textbox.index(f"@{event.x},{event.y}")
        line_num = int(index.split(".")[0])
        job = self._job_line_map.get(line_num)
        if not job:
            return

        state = normalized_state(job.get("state"))
        job_id = safe_text(job.get("job_id"), "")
        if is_completed(state) or is_failed(state):
            self._show_log_popup(job)
            return

        self._show_message_popup(
            "Log Not Available",
            f"Job {job_id} ({state}) does not have a log.\n\n"
            "Only COMPLETED or FAILED jobs have logs.",
        )

    def _show_message_popup(self, title, message):
        popup = ctk.CTkToplevel(self)
        popup.title(title)
        popup.geometry("400x150")
        popup.attributes("-topmost", True)
        popup.after(300, lambda: popup.attributes("-topmost", False))

        label = ctk.CTkLabel(popup, text=message, font=ctk.CTkFont(size=13))
        label.pack(expand=True, padx=20, pady=20)

        btn = ctk.CTkButton(popup, text="OK", width=100, command=popup.destroy)
        btn.pack(pady=(0, 15))

    def _show_log_popup(self, job):
        job_id = safe_text(job.get("job_id"), "")
        popup = ctk.CTkToplevel(self)
        popup.title(f"Job Log: {job_id}")
        popup.geometry("900x600")
        popup.attributes("-topmost", True)
        popup.after(300, lambda: popup.attributes("-topmost", False))

        textbox = ctk.CTkTextbox(popup, font=ctk.CTkFont(family="Consolas", size=12))
        textbox.pack(fill="both", expand=True, padx=10, pady=10)
        textbox.insert("end", f"Loading log for job {job_id}...")

        run_detached(
            popup,
            task=lambda: get_job_log(job_id, job),
            on_success=lambda content: self._update_log_textbox(textbox, content),
            on_error=lambda exc: self._update_log_textbox(textbox, f"Error fetching log: {exc}"),
        )

    def _update_log_textbox(self, textbox, content):
        textbox.delete("1.0", "end")
        textbox.insert("end", content)

    def _set_loading(self, message):
        self.textbox.delete("1.0", "end")
        self.textbox.insert("end", f"{message}\n", "default")

    def _show_error(self, message):
        self.textbox.delete("1.0", "end")
        self.textbox.insert("end", f"{message}\n", "failed")

    def refresh(self):
        self.cancel_background_tasks()
        self.textbox.delete("1.0", "end")
        self._jobs_cache = []
        self._job_line_map = {}
        self._model_filter_values = [ALL_MODELS]
        self.model_filter_menu.configure(values=[ALL_MODELS])
        self.model_filter_var.set(ALL_MODELS)
        self._account_filter_values = [ALL_ACCOUNTS]
        self.account_filter_menu.configure(values=[ALL_ACCOUNTS])
        self.account_filter_var.set(ALL_ACCOUNTS)
        self.textbox.insert(
            "end",
            "Job History tab has been reset.\n"
            "Please set a new date range and click [Fetch].\n",
            "default",
        )
