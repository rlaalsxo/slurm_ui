import customtkinter as ctk
from ui.nodes import NodesFrame
from ui.jobs_live import JobsLiveFrame
from ui.jobs_history import JobsHistoryFrame
from ui.model_stats import ModelStatsFrame   # ✅ 새로 추가
from services import api_client


class Dashboard(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)

        # ======================
        # 🌐 Environment 전환 바
        # ======================
        env_frame = ctk.CTkFrame(self)
        env_frame.pack(fill="x", padx=20, pady=(15, 5))

        env_label = ctk.CTkLabel(
            env_frame,
            text="🌐 Environment:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        env_label.pack(side="left", padx=(10, 5))

        self.env_var = ctk.StringVar(value="MAIN")

        # MAIN 라디오 버튼
        self.main_button = ctk.CTkRadioButton(
            env_frame,
            text="MAIN",
            variable=self.env_var,
            value="MAIN",
            command=self.change_env
        )
        self.main_button.pack(side="left", padx=10)

        # TEST 라디오 버튼
        self.test_button = ctk.CTkRadioButton(
            env_frame,
            text="TEST",
            variable=self.env_var,
            value="TEST",
            command=self.change_env
        )
        self.test_button.pack(side="left", padx=10)

        # 전체 새로고침 버튼
        self.refresh_all_button = ctk.CTkButton(
            env_frame,
            text="🔁 전체 새로고침",
            width=150,
            command=self.refresh_all
        )
        self.refresh_all_button.pack(side="right", padx=10)

        # 현재 환경 표시
        self.current_env_label = ctk.CTkLabel(
            env_frame,
            text=f"현재 환경: {self.env_var.get()}",
            text_color="#00ff88"
        )
        self.current_env_label.pack(side="right", padx=10)

        # ======================
        # 🧭 탭 구성
        # ======================
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=20, pady=20)

        # --- 개별 탭 생성 ---
        self.nodes_tab = self.tabview.add("🖥️ Nodes")
        self.jobs_tab = self.tabview.add("🔄 Running Jobs")
        self.history_tab = self.tabview.add("📜 Job History")
        self.stats_tab = self.tabview.add("📊 Model Stats")  # ✅ 추가된 탭

        # --- 각 탭에 프레임 장착 ---
        self.nodes_frame = NodesFrame(self.nodes_tab)
        self.nodes_frame.pack(fill="both", expand=True)

        self.jobs_frame = JobsLiveFrame(self.jobs_tab)
        self.jobs_frame.pack(fill="both", expand=True)

        self.history_frame = JobsHistoryFrame(self.history_tab)
        self.history_frame.pack(fill="both", expand=True)

        self.stats_frame = ModelStatsFrame(self.stats_tab)  # ✅ 새 탭 프레임 추가
        self.stats_frame.pack(fill="both", expand=True)

    # ======================
    # 🌐 환경 전환 로직
    # ======================
    def change_env(self):
        env = self.env_var.get().upper()
        api_client.set_env(env)

        color = "#00ff88" if env == "MAIN" else "#ffaa00"
        self.current_env_label.configure(text=f"현재 환경: {env}", text_color=color)

        print(f"✅ Switched environment to {env}")
        self.refresh_all()  # 전환 시 자동 새로고침

    # ======================
    # 🔄 전체 새로고침
    # ======================
    def refresh_all(self):
        """모든 탭 데이터 새로고침"""
        try:
            print("🔁 전체 새로고침 중...")

            # 노드 탭 새로고침
            if hasattr(self.nodes_frame, "refresh"):
                self.nodes_frame.refresh()

            # 실시간 잡 새로고침
            if hasattr(self.jobs_frame, "refresh"):
                self.jobs_frame.refresh()

            # 잡 히스토리 초기화
            if hasattr(self.history_frame, "refresh"):
                self.history_frame.refresh()

            # 모델 통계 초기화
            if hasattr(self.stats_frame, "refresh"):
                self.stats_frame.refresh()

            print("✅ 전체 새로고침 완료")

        except Exception as e:
            print(f"⚠️ 전체 새로고침 중 오류: {e}")
