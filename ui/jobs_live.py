import customtkinter as ctk
from services.api_client import get_queue

class JobsLiveFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)

        # 상단 영역 (제목 + 버튼)
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", padx=10, pady=(10, 5))

        self.title_label = ctk.CTkLabel(
            top_frame,
            text="Slurm Queue (Live Job Monitor)",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.title_label.pack(side="left", padx=5)

        self.refresh_button = ctk.CTkButton(
            top_frame,
            text="Refresh Now",
            width=150,
            command=self.refresh
        )
        self.refresh_button.pack(side="right", padx=5)

        # 메인 텍스트 박스 (📌 고정폭 폰트 적용)
        self.textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=13)  # 👈 고정폭 폰트
        )
        self.textbox.pack(fill="both", expand=True, padx=10, pady=10)

        # 색상 태그 정의
        self.textbox.tag_config("running", foreground="#00ff66")  # 초록
        self.textbox.tag_config("pending", foreground="#ffcc00")  # 노랑
        self.textbox.tag_config("error", foreground="#ff3333")    # 빨강
        self.textbox.tag_config("default", foreground="#cccccc")  # 기본 회색

        # 자동 새로고침 시작
        self.refresh()

    def refresh(self):
        try:
            jobs = get_queue()

            # 상태 순서 정렬: RUNNING → PENDING → 기타
            state_priority = {"R": 1, "RUNNING": 1, "PD": 2, "PENDING": 2}
            jobs.sort(key=lambda j: state_priority.get(j["state"].upper(), 99))

            self.textbox.delete("1.0", "end")

            # 헤더 (폭 조정)
            header = (
                f"{'JOBID':8} {'PARTITION':14} {'NAME':20} {'USER':12} {'ACCOUNT':12} "
                f"{'ST':4} {'TIME':8} {'NODES':6} NODELIST(REASON)\n"
            )
            self.textbox.insert("end", header, "default")
            self.textbox.insert("end", "-" * 120 + "\n", "default")

            # 데이터 표시
            for job in jobs:
                tag = self._get_state_tag(job["state"])
                line = (
                    f"{job.get('job_id', '-')[:8]:8} "
                    f"{job.get('partition', '-')[:14]:14} "
                    f"{job.get('name', '-')[:20]:20} "
                    f"{job.get('user', '-')[:12]:12} "
                    f"{job.get('account', '-')[:12]:12} "
                    f"{job.get('state', '-')[:4]:4} "
                    f"{job.get('time', '-')[:8]:8} "
                    f"{job.get('nodes', '-')[:6]:6} "
                    f"{job.get('nodelist', '-')}\n"
                )
                self.textbox.insert("end", line, tag)

        except Exception as e:
            self.textbox.delete("1.0", "end")
            self.textbox.insert("end", f"\n Error fetching queue: {e}\n", "error")

        finally:
            # 60초마다 자동 갱신
            self.after(60000, self.refresh)

    def _get_state_tag(self, state: str) -> str:
        """잡 상태별 색상 태그"""
        s = state.upper().strip()
        if s in ("R", "RUNNING"):
            return "running"
        elif s in ("PD", "PENDING"):
            return "pending"
        elif s in ("CA", "CD", "F", "FAILED", "CANCELLED", "TIMEOUT"):
            return "error"
        return "default"
