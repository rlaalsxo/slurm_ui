# ui/jobs_history.py
import customtkinter as ctk
from services.api_client import get_jobs, get_job_log
import datetime
import threading

class JobsHistoryFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)

        # 상단 컨트롤 패널
        control_frame = ctk.CTkFrame(self)
        control_frame.pack(fill="x", padx=10, pady=(10, 5))

        # 시작 날짜 입력
        self.start_label = ctk.CTkLabel(control_frame, text="Start (YYYY-MM-DD):")
        self.start_label.grid(row=0, column=0, padx=5, pady=5)
        self.start_entry = ctk.CTkEntry(control_frame, width=120)
        self.start_entry.grid(row=0, column=1, padx=5, pady=5)

        # 종료 날짜 입력
        self.end_label = ctk.CTkLabel(control_frame, text="End (YYYY-MM-DD):")
        self.end_label.grid(row=0, column=2, padx=5, pady=5)
        self.end_entry = ctk.CTkEntry(control_frame, width=120)
        self.end_entry.grid(row=0, column=3, padx=5, pady=5)

        # 빠른 선택 버튼들
        self.last7_button = ctk.CTkButton(control_frame, text="Last 7 days", width=80, command=lambda: self.set_range(7))
        self.last7_button.grid(row=0, column=4, padx=5)
        self.last30_button = ctk.CTkButton(control_frame, text="Last 30 days", width=80, command=lambda: self.set_range(30))
        self.last30_button.grid(row=0, column=5, padx=5)
        self.all_button = ctk.CTkButton(control_frame, text="All", width=80, command=lambda: self.set_range(365))
        self.all_button.grid(row=0, column=6, padx=5)

        # 조회 버튼
        self.fetch_button = ctk.CTkButton(control_frame, text="Fetch", width=100, command=self.fetch_history)
        self.fetch_button.grid(row=0, column=7, padx=10, pady=5)

        # 결과 표시 텍스트박스 (📘 고정폭 폰트 적용)
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
        self.textbox.tag_config("vessl_completed", foreground="#bb86fc")  # 보라 (VESSL 완료)
        self.textbox.tag_config("vessl_failed", foreground="#cf6679")     # 연분홍 (VESSL 실패)
        self.textbox.tag_config("vessl_default", foreground="#9966cc")    # 연보라 (VESSL 기타)

        # job 데이터 캐싱 (더블클릭 시 사용)
        self._jobs_cache = []
        self._job_line_map = {}  # line_number -> job dict

        # 더블클릭 이벤트 바인딩
        self.textbox.bind("<Double-Button-1>", self._on_double_click)

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
            self.textbox.insert("end", "Loading job history data...\n", "default")

            start_str = self.start_entry.get().strip()
            end_str = self.end_entry.get().strip()

            if not start_str or not end_str:
                self.textbox.delete("1.0", "end")
                self.textbox.insert("end", "Please enter both start and end dates (e.g., 2025-11-01)\n", "failed")
                return

            # ISO 포맷 변환
            start_iso = datetime.datetime.strptime(start_str, "%Y-%m-%d").isoformat()
            end_iso = (datetime.datetime.strptime(end_str, "%Y-%m-%d") + datetime.timedelta(days=1)).isoformat()

            jobs = get_jobs(start=start_iso, end=end_iso)

            # 결과 정리
            self.textbox.delete("1.0", "end")
            self._jobs_cache = jobs
            self._job_line_map = {}

            header = (
                f"{'Source':8} {'JobID':10} {'Name':20} {'User':10} {'Account':10} "
                f"{'State':10} {'Start':19} {'End':19} {'Node':12}\n"
            )
            self.textbox.insert("end", header, "default")
            self.textbox.insert("end", "-" * 135 + "\n", "default")
            self.textbox.insert("end", "  (Double-click a COMPLETED/FAILED job to view log)\n\n", "default")

            jobs.sort(key=lambda j: j.get("end") or "", reverse=True)

            for job in jobs:
                # 현재 줄 번호 기록
                line_idx = int(self.textbox.index("end-1c").split(".")[0])
                self._job_line_map[line_idx] = job

                source = job.get("source", "slurm")
                tag = self._get_state_tag(job.get("state", ""), source)
                source_label = "VESSL" if source == "vessl" else "SLURM"
                line = (
                    f"{source_label:8} "
                    f"{job.get('job_id', '-')[:10]:10} "
                    f"{job.get('job_name', '-')[:20]:20} "
                    f"{job.get('user', '-')[:10]:10} "
                    f"{job.get('account', '-')[:10]:10} "
                    f"{job.get('state', '-')[:10]:10} "
                    f"{job.get('start', '-')[:19]:19} "
                    f"{job.get('end', '-')[:19]:19} "
                    f"{job.get('node_list', '-')[:12]:12}\n"
                )
                self.textbox.insert("end", line, tag)

            if not jobs:
                self.textbox.insert("end", "\nNo jobs found for the selected period.\n", "default")

        except Exception as e:
            self.textbox.delete("1.0", "end")
            self.textbox.insert("end", f"Error fetching job history: {e}\n", "failed")

    def _get_state_tag(self, state: str, source: str = "slurm"):
        s = state.upper()
        if source == "vessl":
            if s in ("COMPLETED", "CD"):
                return "vessl_completed"
            elif s in ("FAILED", "F"):
                return "vessl_failed"
            return "vessl_default"
        if s in ("COMPLETED", "CD"):
            return "completed"
        elif s in ("FAILED", "F"):
            return "failed"
        elif s.startswith("CANCELLED") or s == "CA":
            return "cancelled"
        return "default"

    # ✅ 더블클릭 → 로그 조회
    def _on_double_click(self, event):
        index = self.textbox.index(f"@{event.x},{event.y}")
        line_num = int(index.split(".")[0])
        job = self._job_line_map.get(line_num)
        if not job:
            return

        state = (job.get("state", "") or "").upper()
        job_id = job.get("job_id", "")

        # COMPLETED, FAILED만 로그 조회 가능
        if state in ("COMPLETED", "CD", "FAILED", "F"):
            self._show_log_popup(job_id)
        else:
            self._show_message_popup(
                "Log Not Available",
                f"Job {job_id} ({state}) does not have a log.\n\n"
                "Only COMPLETED or FAILED jobs have logs."
            )

    def _show_message_popup(self, title, message):
        popup = ctk.CTkToplevel(self)
        popup.title(title)
        popup.geometry("400x150")
        popup.attributes("-topmost", True)
        popup.after(300, lambda: popup.attributes("-topmost", False))

        label = ctk.CTkLabel(popup, text=message, font=ctk.CTkFont(size=13))
        label.pack(expand=True, padx=20, pady=20)

        btn = ctk.CTkButton(popup, text="OK", width=100, command=popup.destroy)
        btn.pack(pady=(0, 15))

    def _show_log_popup(self, job_id):
        popup = ctk.CTkToplevel(self)
        popup.title(f"Job Log: {job_id}")
        popup.geometry("900x600")
        popup.attributes("-topmost", True)
        popup.after(300, lambda: popup.attributes("-topmost", False))

        textbox = ctk.CTkTextbox(popup, font=ctk.CTkFont(family="Consolas", size=12))
        textbox.pack(fill="both", expand=True, padx=10, pady=10)
        textbox.insert("end", f"Loading log for job {job_id}...")

        def fetch_log():
            try:
                log_content = get_job_log(job_id)
                textbox.after(0, lambda: self._update_log_textbox(textbox, log_content))
            except Exception as e:
                error_msg = f"Error fetching log: {e}"
                textbox.after(0, lambda: self._update_log_textbox(textbox, error_msg))

        threading.Thread(target=fetch_log, daemon=True).start()

    def _update_log_textbox(self, textbox, content):
        textbox.delete("1.0", "end")
        textbox.insert("end", content)

    # ✅ 새로고침 기능 추가
    def refresh(self):
        """대시보드에서 전체 새로고침 시 불리는 함수"""
        self.textbox.delete("1.0", "end")
        self._jobs_cache = []
        self._job_line_map = {}
        self.textbox.insert(
            "end",
            "Job History tab has been reset.\n"
            "Please set a new date range and click [Fetch].\n",
            "default"
        )
