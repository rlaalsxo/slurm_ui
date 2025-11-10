import customtkinter as ctk
from services.api_client import get_jobs
import datetime
import threading

class JobsHistoryFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)

        # 상단 컨트롤 패널
        control_frame = ctk.CTkFrame(self)
        control_frame.pack(fill="x", padx=10, pady=(10, 5))

        # 시작 날짜 입력
        self.start_label = ctk.CTkLabel(control_frame, text="📅 Start (YYYY-MM-DD):")
        self.start_label.grid(row=0, column=0, padx=5, pady=5)
        self.start_entry = ctk.CTkEntry(control_frame, width=120)
        self.start_entry.grid(row=0, column=1, padx=5, pady=5)

        # 종료 날짜 입력
        self.end_label = ctk.CTkLabel(control_frame, text="📅 End (YYYY-MM-DD):")
        self.end_label.grid(row=0, column=2, padx=5, pady=5)
        self.end_entry = ctk.CTkEntry(control_frame, width=120)
        self.end_entry.grid(row=0, column=3, padx=5, pady=5)

        # 빠른 선택 버튼들
        self.last7_button = ctk.CTkButton(control_frame, text="최근 7일", width=80, command=lambda: self.set_range(7))
        self.last7_button.grid(row=0, column=4, padx=5)
        self.last30_button = ctk.CTkButton(control_frame, text="최근 30일", width=80, command=lambda: self.set_range(30))
        self.last30_button.grid(row=0, column=5, padx=5)
        self.all_button = ctk.CTkButton(control_frame, text="전체", width=80, command=lambda: self.set_range(365))
        self.all_button.grid(row=0, column=6, padx=5)

        # 조회 버튼
        self.fetch_button = ctk.CTkButton(control_frame, text="🔍 조회하기", width=100, command=self.fetch_history)
        self.fetch_button.grid(row=0, column=7, padx=10, pady=5)

        # 결과 표시 텍스트박스 (📌 고정폭 폰트 적용)
        self.textbox = ctk.CTkTextbox(
            self,
            height=550,
            font=ctk.CTkFont(family="Consolas", size=13)
        )
        self.textbox.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        # 색상 태그 정의
        self.textbox.tag_config("completed", foreground="#00ff66")  # 초록
        self.textbox.tag_config("failed", foreground="#ff6666")     # 빨강
        self.textbox.tag_config("cancelled", foreground="#ffcc00")  # 노랑
        self.textbox.tag_config("default", foreground="#cccccc")    # 회색

    # 날짜 범위 빠른 선택
    def set_range(self, days):
        end = datetime.date.today()
        start = end - datetime.timedelta(days=days)
        self.start_entry.delete(0, "end")
        self.start_entry.insert(0, start.isoformat())
        self.end_entry.delete(0, "end")
        self.end_entry.insert(0, end.isoformat())
        self.fetch_history()

    # 조회 함수 (threading으로 비동기 처리)
    def fetch_history(self):
        threading.Thread(target=self._fetch_history_thread, daemon=True).start()

    def _fetch_history_thread(self):
        try:
            self.textbox.delete("1.0", "end")
            self.textbox.insert("end", "⏳ 데이터를 불러오는 중...\n", "default")

            start_str = self.start_entry.get().strip()
            end_str = self.end_entry.get().strip()

            if not start_str or not end_str:
                self.textbox.delete("1.0", "end")
                self.textbox.insert("end", "⚠️ 시작일과 종료일을 모두 입력하세요 (예: 2025-11-01)\n", "failed")
                return

            # ISO 포맷 변환
            start_iso = datetime.datetime.strptime(start_str, "%Y-%m-%d").isoformat()
            end_iso = (datetime.datetime.strptime(end_str, "%Y-%m-%d") + datetime.timedelta(days=1)).isoformat()

            jobs = get_jobs(start=start_iso, end=end_iso)

            # 결과 정리
            self.textbox.delete("1.0", "end")
            header = (
                f"{'JobID':10} {'Name':22} {'User':12} {'Account':12} "
                f"{'State':12} {'Start':20} {'End':20}\n"
            )
            self.textbox.insert("end", header, "default")
            self.textbox.insert("end", "-" * 115 + "\n", "default")

            jobs.sort(key=lambda j: j.get("end") or "", reverse=True)

            for job in jobs:
                tag = self._get_state_tag(job.get("state", ""))
                line = (
                    f"{job.get('job_id', '-')[:10]:10} "
                    f"{job.get('job_name', '-')[:22]:22} "
                    f"{job.get('user', '-')[:12]:12} "
                    f"{job.get('account', '-')[:12]:12} "
                    f"{job.get('state', '-')[:12]:12} "
                    f"{job.get('start', '-')[:20]:20} "
                    f"{job.get('end', '-')[:20]:20}\n"
                )
                self.textbox.insert("end", line, tag)

            if not jobs:
                self.textbox.insert("end", "\n📭 조회된 Job이 없습니다.\n", "default")

        except Exception as e:
            self.textbox.delete("1.0", "end")
            self.textbox.insert("end", f"❌ Error fetching job history: {e}\n", "failed")

    def _get_state_tag(self, state: str):
        s = state.upper()
        if s in ("COMPLETED", "CD"):
            return "completed"
        elif s in ("FAILED", "F"):
            return "failed"
        elif s in ("CANCELLED", "CA"):
            return "cancelled"
        else:
            return "default"

    # ✅ 새로고침 기능 추가
    def refresh(self):
        """대시보드에서 전체 새로고침 시 불리는 함수"""
        self.textbox.delete("1.0", "end")
        self.textbox.insert(
            "end",
            "⚙️ Job History 탭은 새로고침 시 데이터가 초기화됩니다.\n"
            "조회할 기간을 다시 입력 후 [🔍 조회하기] 버튼을 눌러주세요.\n",
            "default"
        )
