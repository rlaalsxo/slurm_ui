import customtkinter as ctk
from ui.dashboard import Dashboard

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class SlurmMonitorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Slurm Monitor Dashboard")
        self.geometry("1600x900")
        self.dashboard = Dashboard(self)
        self.dashboard.pack(fill="both", expand=True)

if __name__ == "__main__":
    app = SlurmMonitorApp()
    app.mainloop()
