import customtkinter as ctk
import os
import sys
from ui.dashboard import Dashboard

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

if __name__ == "__main__":
    app = SlurmMonitorApp()
    app.mainloop()
