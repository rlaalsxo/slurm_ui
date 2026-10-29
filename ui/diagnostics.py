"""Read-only diagnostics popup; controller and telemetry failures are independent."""
import json
import customtkinter as ctk
from services.api_client import get_job_diagnostics, telemetry_transport_warning
from services.diagnostics_summary import format_attempts
from ui.background import run_detached


def show_job_diagnostics(master, job):
    executor_id = job.get("job_id")
    popup = ctk.CTkToplevel(master)
    popup.title(f"Job diagnostics: {executor_id}")
    popup.geometry("1050x700")
    state = {"payload": None, "raw": False}
    toggle = ctk.CTkButton(popup, text="Raw JSON", width=100)
    toggle.pack(anchor="ne", padx=10, pady=(10, 0))
    textbox = ctk.CTkTextbox(popup, font=("Consolas", 12))
    textbox.pack(fill="both", expand=True, padx=10, pady=10)
    textbox.insert("end", "Loading execution attempts and diagnostic summaries…")

    def show(text):
        textbox.delete("1.0", "end")
        textbox.insert("end", text)

    def redraw():
        if state["payload"] is None:
            return
        raw = state["raw"]
        text = json.dumps(state["payload"], ensure_ascii=False, indent=2) if raw else format_attempts(state["payload"])
        warning = telemetry_transport_warning()
        show(f"⚠ {warning}\n\n{text}" if warning else text)
        toggle.configure(text="Summary" if raw else "Raw JSON")

    def flip():
        state["raw"] = not state["raw"]
        redraw()

    def loaded(payload):
        state["payload"] = payload
        redraw()

    toggle.configure(command=flip)
    run_detached(popup, task=lambda: get_job_diagnostics(job), on_success=loaded,
                 on_error=lambda exc: show(f"Diagnostics unavailable: {exc}"))
