import customtkinter as ctk

from services.api_client import get_job_log, get_jobs
from ui.background import BackgroundTaskMixin, run_detached
from ui.date_utils import read_date_range, set_recent_range
from ui.job_utils import (
    ACCOUNT_COLUMN_WIDTH,
    ACCOUNT_ID_COLUMN_WIDTH,
    ALL_ACCOUNTS,
    ALL_EMAILS,
    ALL_MODELS,
    ALL_SERVICES,
    ALL_STATUSES,
    SERVICE_CURIEUS,
    SERVICE_LAIDD,
    STATUS_FILTER_VALUES,
    account_email,
    account_filter_values,
    account_id,
    cell,
    email_filter_values,
    extract_model,
    format_seconds,
    history_line_tag,
    is_completed,
    is_failed,
    job_elapsed_seconds,
    matches_account,
    matches_email,
    matches_service,
    matches_status,
    normalized_state,
    safe_text,
    service_label,
)
from ui.scroll_option_menu import ScrollableOptionMenu


class JobsHistoryFrame(BackgroundTaskMixin, ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self._init_background_tasks()
        self._jobs_cache = []
        self._job_line_map = {}

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

        # 필터는 칸 폭이 날짜 줄과 달라서 따로 프레임에 둔다(grid 열을 같이 쓰면 위 버튼 사이가 벌어진다).
        filter_frame = ctk.CTkFrame(control_frame, fg_color="transparent")
        filter_frame.grid(row=1, column=0, columnspan=8, sticky="w")
        self.model_filter_var, self.model_filter_menu = self._add_filter(filter_frame, "Model:", [ALL_MODELS], 180)
        self.account_filter_var, self.account_filter_menu = self._add_filter(filter_frame, "Account:", [ALL_ACCOUNTS], 120)
        self.email_filter_var, self.email_filter_menu = self._add_filter(filter_frame, "Email:", [ALL_EMAILS], 240)
        # 컨트롤러를 Curieus 와 LAIDD 가 함께 쓴다. QOS 로 가른 서비스 필터(계정 필터처럼 목록이 늘지 않는 고정 값).
        self.service_filter_var, self.service_filter_menu = self._add_filter(
            filter_frame, "Service:", [ALL_SERVICES, SERVICE_LAIDD, SERVICE_CURIEUS], 110)
        self.status_filter_var, self.status_filter_menu = self._add_filter(filter_frame, "Status:", STATUS_FILTER_VALUES, 110)

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
        self.textbox.tag_config("laidd_completed", foreground="#4dd0e1")
        self.textbox.tag_config("laidd_failed", foreground="#ff8a65")
        self.textbox.tag_config("laidd_cancelled", foreground="#ffd180")
        self.textbox.tag_config("laidd_default", foreground="#80cbc4")

        self.textbox.bind("<Double-Button-1>", self._on_double_click)
        self.textbox.bind("<Button-3>", self._on_diagnostics_click)

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

    def _add_filter(self, parent, label_text, values, width):
        label = ctk.CTkLabel(parent, text=label_text)
        label.pack(side="left", padx=(10, 5), pady=5)
        variable = ctk.StringVar(value=values[0])
        menu = ScrollableOptionMenu(
            parent, values=values, variable=variable, width=width, command=lambda _: self.display_history())
        menu.pack(side="left", padx=(0, 5), pady=5)
        menu.bind_wheel_cycle(label)
        return variable, menu

    def _set_jobs(self, jobs):
        self._jobs_cache = jobs
        models = sorted({extract_model(job.get("job_name")) for job in jobs})
        self._set_filter_values(self.model_filter_menu, self.model_filter_var, [ALL_MODELS] + models)
        self._set_filter_values(self.account_filter_menu, self.account_filter_var, account_filter_values(jobs))
        self._set_filter_values(self.email_filter_menu, self.email_filter_var, email_filter_values(jobs))
        self.display_history()

    @staticmethod
    def _set_filter_values(menu, variable, values):
        """새 기간에도 있는 값이면 선택을 유지하고, 없으면 All 로 돌린다."""
        current = variable.get()
        menu.configure(values=values)
        variable.set(current if current in values else values[0])

    def _get_filtered_jobs(self):
        selected_model = self.model_filter_var.get()
        selected_account = self.account_filter_var.get()
        selected_email = self.email_filter_var.get()
        selected_service = self.service_filter_var.get()
        selected_status = self.status_filter_var.get()
        return [
            job for job in self._jobs_cache
            if (selected_model == ALL_MODELS or extract_model(job.get("job_name")) == selected_model)
            and matches_account(job, selected_account)
            and matches_email(job, selected_email)
            and matches_service(job, selected_service)
            and matches_status(job, selected_status)
        ]

    def display_history(self):
        jobs = self._get_filtered_jobs()

        self.textbox.delete("1.0", "end")
        self._job_line_map = {}

        header = (
            f"{'Source':8} {'JobID':10} {'Name':20} {'User':10} {'Account':{ACCOUNT_ID_COLUMN_WIDTH}} "
            f"{'Email':{ACCOUNT_COLUMN_WIDTH}} {'State':10} {'Start':19} {'End':19} {'Elapsed':13} {'Node':12}\n"
        )
        self.textbox.insert("end", header, "default")
        self.textbox.insert("end", "-" * (150 + ACCOUNT_ID_COLUMN_WIDTH + ACCOUNT_COLUMN_WIDTH - 10) + "\n", "default")

        active_filters = []
        if self.model_filter_var.get() != ALL_MODELS:
            active_filters.append(f"Model={self.model_filter_var.get()}")
        if self.account_filter_var.get() != ALL_ACCOUNTS:
            active_filters.append(f"Account={self.account_filter_var.get()}")
        if self.email_filter_var.get() != ALL_EMAILS:
            active_filters.append(f"Email={self.email_filter_var.get()}")
        if self.service_filter_var.get() != ALL_SERVICES:
            active_filters.append(f"Service={self.service_filter_var.get()}")
        if self.status_filter_var.get() != ALL_STATUSES:
            active_filters.append(f"Status={self.status_filter_var.get()}")
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
            self.textbox.insert("end", self._format_job_line(job), history_line_tag(job))

        if not jobs:
            self.textbox.insert("end", "\nNo jobs found for the selected period and model filter.\n", "default")

    def _format_job_line(self, job):
        return (
            f"{service_label(job):8} "
            f"{cell(job.get('job_id'), 10)} "
            f"{cell(job.get('job_name'), 20)} "
            f"{cell(job.get('user'), 10)} "
            f"{cell(account_id(job), ACCOUNT_ID_COLUMN_WIDTH)} "
            f"{cell(account_email(job), ACCOUNT_COLUMN_WIDTH)} "
            f"{cell(job.get('state'), 10)} "
            f"{cell(job.get('start'), 19)} "
            f"{cell(job.get('end'), 19)} "
            f"{cell(format_seconds(job_elapsed_seconds(job)), 13)} "
            f"{cell(job.get('node_list'), 12)}\n"
        )

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

    def _on_diagnostics_click(self, event):
        line = int(self.textbox.index(f"@{event.x},{event.y}").split(".")[0])
        job = self._job_line_map.get(line)
        if job:
            from ui.diagnostics import show_job_diagnostics
            show_job_diagnostics(self, job)

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
        from ui.diagnostics import show_job_diagnostics
        ctk.CTkButton(popup, text="Execution diagnostics", command=lambda: show_job_diagnostics(popup, job)).pack(padx=10, pady=5)
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
        self._set_filter_values(self.model_filter_menu, self.model_filter_var, [ALL_MODELS])
        self._set_filter_values(self.account_filter_menu, self.account_filter_var, [ALL_ACCOUNTS])
        self._set_filter_values(self.email_filter_menu, self.email_filter_var, [ALL_EMAILS])
        self.service_filter_var.set(ALL_SERVICES)
        self.status_filter_var.set(ALL_STATUSES)
        self.textbox.insert(
            "end",
            "Job History tab has been reset.\n"
            "Please set a new date range and click [Fetch].\n",
            "default",
        )
