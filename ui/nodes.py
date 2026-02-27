import customtkinter as ctk
from services.api_client import get_nodes, drain_node, resume_node
from tkinter import messagebox
import threading
import requests


class NodesFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)

        self.current_filter = None
        self.nodes_cache = []

        # 상태 플래그 및 타이머
        self._refreshing = False
        self._auto_after_id = None
        self._auto_interval = 600000  # 10분

        # 상단 타이틀
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", padx=10, pady=(10, 5))

        self.title_label = ctk.CTkLabel(
            top_frame,
            text="Slurm Nodes (Node Status Monitor)",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.title_label.pack(side="left", padx=5)

        # 수동 새로고침: 타이머 건드리지 않음
        self.refresh_button = ctk.CTkButton(
            top_frame, text="Refresh", width=120, command=self.on_manual_refresh
        )
        self.refresh_button.pack(side="right", padx=5)

        # 상태 요약
        self.stats_frame = ctk.CTkFrame(self)
        self.stats_frame.pack(fill="x", padx=10, pady=(0, 5))

        self.stats_labels = {}
        for state in ["IDLE", "ALLOC", "DRAIN", "DOWN"]:
            btn = ctk.CTkButton(
                self.stats_frame,
                text=f"{state}: 0",
                width=120,
                command=lambda s=state: self.filter_by_state(s),
            )
            btn.pack(side="left", padx=8, pady=5)
            self.stats_labels[state] = btn

        # 텍스트 영역 (고정폭 폰트)
        self.table = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=13)
        )
        self.table.pack(fill="both", expand=True, padx=10, pady=10)

        # 색상 태그 정의
        self.table.tag_config("idle", foreground="#00ff66")
        self.table.tag_config("alloc", foreground="#66aaff")
        self.table.tag_config("down", foreground="#ff3333")
        self.table.tag_config("drain", foreground="#ffcc00")
        self.table.tag_config("default", foreground="#cccccc")

        # 마우스 클릭 이벤트 바인딩
        self.table.bind("<Button-1>", self.on_click)

        # 초기 1회 렌더 + 자동 새로고침 시작
        self.fetch_and_render()
        self.start_auto_refresh()

    # ---------------- 수동 새로고침 ----------------
    def on_manual_refresh(self):
        if self._refreshing:
            return
        self.fetch_and_render()

    # ---------------- 자동 새로고침 루프 ----------------
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
        # 실행 중이면 이번 주기는 건너뛰되 다음 주기는 유지
        if not self._refreshing:
            self.fetch_and_render()
        self._auto_after_id = self.after(self._auto_interval, self._auto_tick)

    # ---------------- 데이터 갱신 및 렌더 ----------------
    def fetch_and_render(self):
        self._refreshing = True
        self.refresh_button.configure(state="disabled")
        try:
            nodes = get_nodes()
            self.nodes_cache = nodes

            # 상태별 카운트
            counts = {"IDLE": 0, "ALLOC": 0, "DRAIN": 0, "DOWN": 0}
            for n in nodes:
                s = str(n.get("state", "")).upper()
                if "IDLE" in s:
                    counts["IDLE"] += 1
                elif "ALLOC" in s:
                    counts["ALLOC"] += 1
                elif "DRAIN" in s:
                    counts["DRAIN"] += 1
                elif "DOWN" in s:
                    counts["DOWN"] += 1

            colors = {
                "IDLE": "#00ff66",
                "ALLOC": "#66aaff",
                "DRAIN": "#ffcc00",
                "DOWN": "#ff3333",
            }
            for state, btn in self.stats_labels.items():
                btn.configure(
                    text=f"{state}: {counts[state]}",
                    fg_color=("gray20", "gray25"),
                    hover_color=colors[state],
                )

            # 표시
            data = [n for n in nodes if self._match_filter(n)] if self.current_filter else nodes
            self.display_nodes(data)

        except Exception as e:
            self.table.delete("1.0", "end")
            self.table.insert("end", f"❌ Error fetching nodes: {e}\n", "down")
        finally:
            self.refresh_button.configure(state="normal")
            self._refreshing = False

    def display_nodes(self, nodes):
        """노드 목록 표시"""
        self.table.delete("1.0", "end")
        self.table.insert("end", f"{'Node':22} {'State':15} {'CPU':14} {'Mem':12} {'GPU':18}\n", "default")
        self.table.insert("end", "-" * 90 + "\n", "default")

        for n in sorted(nodes, key=lambda x: str(x.get("name", ""))):
            tag = self._get_state_tag(str(n.get("state", "")))
            line = (
                f"{str(n.get('name', '-'))[:22]:22} "
                f"{str(n.get('state', '-'))[:15]:15} "
                f"{str(n.get('cpu', n.get('cpus', '-')))[:14]:14} "
                f"{str(n.get('mem', n.get('memory', '-')))[:12]:12} "
                f"{str(n.get('gpu', n.get('gpus', '-')))[:18]:18}\n\n"
            )
            self.table.insert("end", line, tag)

    def filter_by_state(self, state):
        self.current_filter = None if self.current_filter == state else state
        data = [n for n in self.nodes_cache if self._match_filter(n)] if self.current_filter else self.nodes_cache
        self.display_nodes(data)

    def _match_filter(self, node):
        return bool(self.current_filter and self.current_filter in str(node.get("state", "")).upper())

    def _get_state_tag(self, state):
        s = str(state).upper()
        if "IDLE" in s:
            return "idle"
        if "ALLOC" in s:
            return "alloc"
        if "DOWN" in s:
            return "down"
        if "DRAIN" in s:
            return "drain"
        return "default"

    # ---------------- 노드 상세 팝업 ----------------
    def on_click(self, event):
        """노드 클릭 시 하이라이트 + 팝업"""
        index = self.table.index(f"@{event.x},{event.y}")
        line = self.table.get(f"{index} linestart", f"{index} lineend").strip()
        if not line or line.startswith("Node") or line.startswith("-"):
            return

        # 클릭 시 줄 하이라이트 효과
        self.table.tag_add("highlight", f"{index} linestart", f"{index} lineend")
        self.table.tag_config("highlight", background="#333333")
        self.after(250, lambda: self.table.tag_remove("highlight", "1.0", "end"))

        node_name = line.split()[0]
        # 팝업 생성은 메인 스레드에서
        self.open_node_detail_popup(node_name)

    def open_node_detail_popup(self, node_name):
        """팝업 생성 후, 데이터 로드는 백그라운드에서 수행하고 UI 갱신은 after로 메인 스레드에서 처리"""
        popup = ctk.CTkToplevel(self)
        popup.title(f"Node Detail: {node_name}")
        popup.geometry("900x700")

        popup.transient(self.winfo_toplevel())
        popup.attributes("-topmost", True)
        popup.lift()
        popup.focus_force()

        label = ctk.CTkLabel(
            popup,
            text=f"Loading node info for {node_name}...",
            font=ctk.CTkFont(size=15, weight="bold")
        )
        label.pack(pady=10)

        textbox = ctk.CTkTextbox(
            popup,
            width=850,
            height=520,
            font=ctk.CTkFont(family="Consolas", size=13)
        )
        textbox.pack(padx=15, pady=10, fill="both", expand=True)

        textbox.tag_config("key", foreground="#00ccff")
        textbox.tag_config("ok", foreground="#00ff66")
        textbox.tag_config("warn", foreground="#ffcc00")
        textbox.tag_config("error", foreground="#ff5555")
        textbox.tag_config("default", foreground="#cccccc")

        btn_frame = ctk.CTkFrame(popup)
        btn_frame.pack(pady=(0, 15))

        def on_drain():
            if not messagebox.askyesno("Drain Node", f"{node_name} 노드를 Drain 하시겠습니까?"):
                return
            try:
                drain_node(node_name)
                messagebox.showinfo("Success", f"{node_name} drained")
                self.fetch_and_render()
                popup.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Drain 실패: {e}")

        def on_resume():
            if not messagebox.askyesno("Resume Node", f"{node_name} 노드를 Resume 하시겠습니까?"):
                return
            try:
                resume_node(node_name)
                messagebox.showinfo("Success", f"{node_name} resumed")
                self.fetch_and_render()
                popup.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Resume 실패: {e}")

        ctk.CTkButton(btn_frame, text="Drain", width=100, fg_color="#cc7700", hover_color="#ff9900", command=on_drain).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Resume", width=100, fg_color="#007744", hover_color="#00aa66", command=on_resume).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Close", width=100, command=popup.destroy).pack(side="left", padx=5)

        def load_and_update():
            try:
                from services import api_client
                res = requests.get(f"{api_client.get_base_url()}/slurm/node/{node_name}", timeout=5)
                res.raise_for_status()
                data = res.json()

                def render():
                    textbox.delete("1.0", "end")
                    if isinstance(data, dict):
                        max_key_len = max(len(k) for k in data.keys()) if data else 0
                        for k, v in data.items():
                            key_tag = "key"
                            value_tag = "default"
                            sv = str(v)
                            kl = k.lower()

                            if kl in ("state", "reason"):
                                s = sv.upper()
                                if "DOWN" in s or "FAIL" in s:
                                    value_tag = "error"
                                elif "DRAIN" in s or "RESERVED" in s:
                                    value_tag = "warn"
                                elif "IDLE" in s or "ALLOC" in s:
                                    value_tag = "ok"
                            elif any(x in kl for x in ("cpu", "mem", "gpu", "gres")):
                                if sv.isdigit() or "G" in sv.upper():
                                    value_tag = "ok"
                            elif "error" in sv.lower():
                                value_tag = "error"

                            textbox.insert("end", f"{k:<{max_key_len}} : ", key_tag)
                            textbox.insert("end", f"{sv}\n", value_tag)
                    else:
                        textbox.insert("end", str(data), "default")

                    label.configure(text=f"Node Detail: {node_name}")

                # 메인 스레드에서 렌더
                self.after(0, render)

            except Exception as e:
                def render_err():
                    textbox.delete("1.0", "end")
                    textbox.insert("end", f"❌ Error fetching node detail: {e}", "error")
                self.after(0, render_err)

        # 데이터 로드는 백그라운드에서
        threading.Thread(target=load_and_update, daemon=True).start()
        
    def refresh(self):
        self.on_manual_refresh()
    # 종료 시 타이머 정리
    def destroy(self):
        self.stop_auto_refresh()
        super().destroy()
