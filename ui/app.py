"""Slurm Monitor 창 실행(Tk)."""
import logging
import os
import traceback

import customtkinter as ctk

from runtime import resource_path
from ui.dashboard import Dashboard

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class SlurmMonitorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Slurm Monitor Dashboard")
        self.geometry("1600x900")

        # 아이콘 설정
        icon_path = resource_path("curie.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)
            self.after(200, lambda: self.iconbitmap(icon_path))
        self.dashboard = Dashboard(self)
        self.dashboard.pack(fill="both", expand=True)

        self.report_callback_exception = self._on_tk_error

    def _on_tk_error(self, exc_type, exc_value, exc_tb):
        error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.error(f"Tkinter exception:\n{error_msg}")


def run():
    SlurmMonitorApp().mainloop()
    return 0
