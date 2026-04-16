import customtkinter as ctk
import os
import sys
import logging
import traceback
from ui.dashboard import Dashboard

# 로그 파일 설정
def get_log_path():
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), "slurm_ui_error.log")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "slurm_ui_error.log")

logging.basicConfig(
    filename=get_log_path(),
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class SlurmMonitorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Slurm Monitor Dashboard")
        self.geometry("1600x900")

        # 아이콘 설정
        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(sys._MEIPASS, "curie.ico")
        else:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "curie.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)
            self.after(200, lambda: self.iconbitmap(icon_path))
        self.dashboard = Dashboard(self)
        self.dashboard.pack(fill="both", expand=True)

        self.report_callback_exception = self._on_tk_error

    def _on_tk_error(self, exc_type, exc_value, exc_tb):
        error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.error(f"Tkinter exception:\n{error_msg}")


if __name__ == "__main__":
    try:
        app = SlurmMonitorApp()
        app.mainloop()
    except Exception:
        logger.critical(f"Fatal exception:\n{traceback.format_exc()}")
        sys.exit(1)
