# ui/dashboard.py
import platform
import customtkinter as ctk
from ui.nodes import NodesFrame
from ui.jobs_live import JobsLiveFrame
from ui.jobs_history import JobsHistoryFrame
from ui.model_stats import ModelStatsFrame
from ui.account_stats import AccountStatsFrame
from services import api_client


# ==========================================
# ✅ Cross-platform font & theme settings
# ==========================================
if platform.system() == "Windows":
    DEFAULT_FONT_FAMILY = "Consolas"
else:
    DEFAULT_FONT_FAMILY = "DejaVu Sans Mono"

# Global theme (dark / blue)
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Global fonts

# ==========================================
# 🧭 Dashboard Main Frame
# ==========================================
class Dashboard(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        DEFAULT_FONT = ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=13)
        HEADER_FONT = ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=14, weight="bold")
        TITLE_FONT = ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=16, weight="bold")

        # ======================
        # 🌐 Environment Switch Bar
        # ======================
        env_frame = ctk.CTkFrame(self)
        env_frame.pack(fill="x", padx=20, pady=(15, 5))

        env_label = ctk.CTkLabel(
            env_frame,
            text="Environment:",
            font=HEADER_FONT
        )
        env_label.pack(side="left", padx=(10, 5))

        self.env_var = ctk.StringVar(value="MAIN")

        # MAIN radio button
        self.main_button = ctk.CTkRadioButton(
            env_frame,
            text="MAIN",
            variable=self.env_var,
            value="MAIN",
            command=self.change_env,
            font=DEFAULT_FONT
        )
        self.main_button.pack(side="left", padx=10)

        # TEST radio button
        self.test_button = ctk.CTkRadioButton(
            env_frame,
            text="TEST",
            variable=self.env_var,
            value="TEST",
            command=self.change_env,
            font=DEFAULT_FONT
        )
        self.test_button.pack(side="left", padx=10)

        # Refresh all button
        self.refresh_all_button = ctk.CTkButton(
            env_frame,
            text="Refresh All",
            width=150,
            command=self.refresh_all,
            font=DEFAULT_FONT
        )
        self.refresh_all_button.pack(side="right", padx=10)

        # Current environment label
        self.current_env_label = ctk.CTkLabel(
            env_frame,
            text=f"Current Environment: {self.env_var.get()}",
            text_color="#00ff88",
            font=DEFAULT_FONT
        )
        self.current_env_label.pack(side="right", padx=10)

        # ======================
        # 📑 Tab Configuration
        # ======================
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=20, pady=20)

        # --- Tabs ---
        self.nodes_tab = self.tabview.add("Nodes")
        self.jobs_tab = self.tabview.add("Running Jobs")
        self.history_tab = self.tabview.add("Job History")
        self.stats_tab = self.tabview.add("Model Stats")
        self.account_tab = self.tabview.add("Account Stats")

        # --- Frames for each tab ---
        self.nodes_frame = NodesFrame(self.nodes_tab)
        self.nodes_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.jobs_frame = JobsLiveFrame(self.jobs_tab)
        self.jobs_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.history_frame = JobsHistoryFrame(self.history_tab)
        self.history_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.stats_frame = ModelStatsFrame(self.stats_tab)
        self.stats_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.account_frame = AccountStatsFrame(self.account_tab)
        self.account_frame.pack(fill="both", expand=True, padx=5, pady=5)

    # ======================
    # 🌐 Environment Switch Logic
    # ======================
    def change_env(self):
        env = self.env_var.get().upper()
        api_client.set_env(env)

        color = "#00ff88" if env == "MAIN" else "#ffaa00"
        self.current_env_label.configure(text=f"Current Environment: {env}", text_color=color)

        print(f"Switched environment to {env}")
        self.refresh_all()  # Auto-refresh after switching

    # ======================
    # 🔄 Global Refresh
    # ======================
    def refresh_all(self):
        """Refresh all tabs"""
        try:
            print("Refreshing all tabs...")

            # Nodes
            if hasattr(self.nodes_frame, "refresh"):
                self.nodes_frame.refresh()

            # Running Jobs
            if hasattr(self.jobs_frame, "refresh"):
                self.jobs_frame.refresh()

            # Job History
            if hasattr(self.history_frame, "refresh"):
                self.history_frame.refresh()

            # Model Stats
            if hasattr(self.stats_frame, "refresh"):
                self.stats_frame.refresh()

            # Account Stats
            if hasattr(self.account_frame, "refresh"):
                self.account_frame.refresh()

            print("All tabs refreshed successfully")

        except Exception as e:
            print(f"Error during refresh: {e}")
