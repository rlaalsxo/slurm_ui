import customtkinter as ctk

from services.api_client import get_queue
from ui.background import BackgroundTaskMixin
from ui.job_utils import cell, normalized_state, safe_text, source_label


class JobsLiveFrame(BackgroundTaskMixin, ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self._init_background_tasks()
        self._refreshing = False
        self._auto_after_id = None
        self._auto_interval = 60000

        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", padx=10, pady=(10, 5))

        self.title_label = ctk.CTkLabel(
            top_frame,
            text="Slurm Queue (Live Job Monitor)",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.title_label.pack(side="left", padx=5)

        self.refresh_button = ctk.CTkButton(
            top_frame,
            text="Refresh Now",
            width=150,
            command=self.on_manual_refresh,
        )
        self.refresh_button.pack(side="right", padx=5)

        self.textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=13),
        )
        self.textbox.pack(fill="both", expand=True, padx=10, pady=10)

        self.textbox.tag_config("running", foreground="#00ff66")
        self.textbox.tag_config("pending", foreground="#ffcc00")
        self.textbox.tag_config("error", foreground="#ff3333")
        self.textbox.tag_config("default", foreground="#cccccc")
        self.textbox.tag_config("vessl_running", foreground="#bb86fc")
        self.textbox.tag_config("vessl_pending", foreground="#9966cc")

        self.fetch_and_render()
        self.start_auto_refresh()

    def on_manual_refresh(self):
        if not self._refreshing:
            self.fetch_and_render()

    def start_auto_refresh(self):
        if self._auto_after_id is None:
            self._auto_after_id = self.after(self._auto_interval, self._auto_tick)

    def stop_auto_refresh(self):
        if self._auto_after_id is None:
            return
        try:
            self.after_cancel(self._auto_after_id)
        except Exception:
            pass
        finally:
            self._auto_after_id = None

    def _auto_tick(self):
        if not self._refreshing:
            self.fetch_and_render()
        self._auto_after_id = self.after(self._auto_interval, self._auto_tick)

    def fetch_and_render(self):
        self.run_background(
            task=get_queue,
            on_start=self._begin_refresh,
            on_success=self.display_jobs,
            on_error=lambda exc: self._show_error(f"Error fetching queue: {exc}"),
            on_done=self._finish_refresh,
        )

    def display_jobs(self, jobs):
        jobs = sorted(jobs, key=self._state_priority)

        self.textbox.delete("1.0", "end")
        header = (
            f"{'SOURCE':8} {'JOBID':8} {'PARTITION':14} {'NAME':20} {'USER':12} {'ACCOUNT':12} "
            f"{'ST':4} {'TIME':8} {'NODES':6} NODELIST(REASON)\n"
        )
        self.textbox.insert("end", header, "default")
        self.textbox.insert("end", "-" * 130 + "\n", "default")

        for job in jobs:
            self.textbox.insert("end", self._format_job_line(job), self._get_state_tag(job))

    def _state_priority(self, job):
        priorities = {"R": 1, "RUNNING": 1, "PD": 2, "PENDING": 2}
        return priorities.get(normalized_state(job.get("state")), 99)

    def _format_job_line(self, job):
        state = safe_text(job.get("state"))
        return (
            f"{source_label(job.get('source')):8} "
            f"{cell(job.get('job_id'), 8)} "
            f"{cell(job.get('partition'), 14)} "
            f"{cell(job.get('name'), 20)} "
            f"{cell(job.get('user'), 12)} "
            f"{cell(job.get('account'), 12)} "
            f"{state[:4]:4} "
            f"{cell(job.get('time'), 8)} "
            f"{cell(job.get('nodes'), 6)} "
            f"{safe_text(job.get('nodelist'))}\n"
        )

    def _get_state_tag(self, job):
        state = normalized_state(job.get("state"))
        source = safe_text(job.get("source"), "slurm").lower()
        if source == "vessl":
            if state in ("R", "RUNNING"):
                return "vessl_running"
            if state in ("PD", "PENDING"):
                return "vessl_pending"
        if state in ("R", "RUNNING"):
            return "running"
        if state in ("PD", "PENDING"):
            return "pending"
        if state in ("CA", "CD", "F", "FAILED", "CANCELLED", "TIMEOUT"):
            return "error"
        return "default"

    def _begin_refresh(self):
        self._refreshing = True
        self.refresh_button.configure(state="disabled")

    def _finish_refresh(self):
        self.refresh_button.configure(state="normal")
        self._refreshing = False

    def _show_error(self, message):
        self.textbox.delete("1.0", "end")
        self.textbox.insert("end", f"\n {message}\n", "error")

    def refresh(self):
        self.cancel_background_tasks()
        self._refreshing = False
        self.fetch_and_render()

    def destroy(self):
        self.cancel_background_tasks()
        self.stop_auto_refresh()
        super().destroy()
