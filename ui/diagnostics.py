"""Read-only diagnostics popup; controller and telemetry failures are independent."""
import json
import customtkinter as ctk
from services.api_client import get_job_diagnostics
from ui.background import run_detached


def show_job_diagnostics(master, job):
    executor_id = job.get("job_id")
    popup = ctk.CTkToplevel(master)
    popup.title(f"Job diagnostics: {executor_id}")
    popup.geometry("1050x700")
    textbox = ctk.CTkTextbox(popup, font=("Consolas", 12))
    textbox.pack(fill="both", expand=True, padx=10, pady=10)
    textbox.insert("end", "Loading execution attempts and diagnostic summaries…")
    def render(value):
        textbox.delete("1.0", "end")
        textbox.insert("end", value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2))
    run_detached(popup, task=lambda: get_job_diagnostics(job), on_success=render,
                 on_error=lambda exc: render(f"Diagnostics unavailable: {exc}"))
