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
            command=self.on_manual_refresh  # 수동 새로고침 전용
        )
        self.refresh_button.pack(side="right", padx=5)

        # 메인 텍스트 박스 (고정폭 폰트)
        self.textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=13)
        )
        self.textbox.pack(fill="both", expand=True, padx=10, pady=10)

        # 색상 태그 정의
        self.textbox.tag_config("running", foreground="#00ff66")  # 초록
        self.textbox.tag_config("pending", foreground="#ffcc00")  # 노랑
        self.textbox.tag_config("error", foreground="#ff3333")    # 빨강
        self.textbox.tag_config("default", foreground="#cccccc")  # 기본 회색
        self.textbox.tag_config("vessl_running", foreground="#bb86fc")  # 보라 (VESSL 실행중)
        self.textbox.tag_config("vessl_pending", foreground="#9966cc")  # 연보라 (VESSL 대기)

        # 상태 플래그 및 타이머
        self._refreshing = False
        self._auto_after_id = None
        self._auto_interval = 60000  # 60초

        # 초기 1회 렌더 + 자동 새로고침 시작
        self.fetch_and_render()
        self.start_auto_refresh()

    # -------- 수동 새로고침: 타이머를 건드리지 않음 --------
    def on_manual_refresh(self):
        if self._refreshing:
            return
        self.fetch_and_render()

    # -------- 자동 새로고침 루프 --------
    def start_auto_refresh(self):
        if self._auto_after_id is None:
            self._auto_after_id = self.after(self._auto_interval, self._auto_tick)

    def stop_auto_refresh(self):
        if self._auto_after_id is not None:
            try:
                self.after_cancel(self._auto_after_id)
            except Exception:
                pass
            finally:
                self._auto_after_id = None

    def _auto_tick(self):
        # 실행 중이면 이번 주기는 건너뛰고 다음 주기만 예약
        if not self._refreshing:
            self.fetch_and_render()
        self._auto_after_id = self.after(self._auto_interval, self._auto_tick)

    # -------- 실제 데이터 갱신 로직 --------
    def fetch_and_render(self):
        self._refreshing = True
        try:
            self.refresh_button.configure(state="disabled")

            jobs = get_queue()  # 외부 API 호출

            # 상태 순서 정렬: RUNNING → PENDING → 기타
            state_priority = {"R": 1, "RUNNING": 1, "PD": 2, "PENDING": 2}
            def pri(j):
                st = str(j.get("state", "")).upper()
                return state_priority.get(st, 99)
            jobs.sort(key=pri)

            self.textbox.delete("1.0", "end")

            # 헤더
            header = (
                f"{'SOURCE':8} {'JOBID':8} {'PARTITION':14} {'NAME':20} {'USER':12} {'ACCOUNT':12} "
                f"{'ST':4} {'TIME':8} {'NODES':6} NODELIST(REASON)\n"
            )
            self.textbox.insert("end", header, "default")
            self.textbox.insert("end", "-" * 130 + "\n", "default")

            # 데이터 표시
            for job in jobs:
                st = str(job.get("state", "-"))
                source = str(job.get("source", "slurm"))
                tag = self._get_state_tag(st, source)
                source_label = "VESSL" if source == "vessl" else "SLURM"
                line = (
                    f"{source_label:8} "
                    f"{str(job.get('job_id', '-'))[:8]:8} "
                    f"{str(job.get('partition', '-'))[:14]:14} "
                    f"{str(job.get('name', '-'))[:20]:20} "
                    f"{str(job.get('user', '-'))[:12]:12} "
                    f"{str(job.get('account', '-'))[:12]:12} "
                    f"{st[:4]:4} "
                    f"{str(job.get('time', '-'))[:8]:8} "
                    f"{str(job.get('nodes', '-'))[:6]:6} "
                    f"{str(job.get('nodelist', '-'))}\n"
                )
                self.textbox.insert("end", line, tag)

        except Exception as e:
            self.textbox.delete("1.0", "end")
            self.textbox.insert("end", f"\n Error fetching queue: {e}\n", "error")

        finally:
            self.refresh_button.configure(state="normal")
            self._refreshing = False

    def _get_state_tag(self, state: str, source: str = "slurm") -> str:
        s = str(state).upper().strip()
        if source == "vessl":
            if s in ("R", "RUNNING"):
                return "vessl_running"
            elif s in ("PD", "PENDING"):
                return "vessl_pending"
        if s in ("R", "RUNNING"):
            return "running"
        elif s in ("PD", "PENDING"):
            return "pending"
        elif s in ("CA", "CD", "F", "FAILED", "CANCELLED", "TIMEOUT"):
            return "error"
        return "default"
    
    def refresh(self):
        self.on_manual_refresh()

    # 종료 시 타이머 정리
    def destroy(self):
        self.stop_auto_refresh()
        super().destroy()
