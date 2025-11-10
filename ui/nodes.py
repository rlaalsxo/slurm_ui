import customtkinter as ctk
from services.api_client import get_nodes
import threading
import requests

class NodesFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)

        self.current_filter = None
        self.nodes_cache = []

        # 상단 타이틀
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", padx=10, pady=(10, 5))

        self.title_label = ctk.CTkLabel(
            top_frame,
            text="🖥️ Slurm Nodes (노드 상태 모니터)",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.title_label.pack(side="left", padx=5)

        self.refresh_button = ctk.CTkButton(top_frame, text="🔄 새로고침", width=120, command=self.refresh)
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

        # 텍스트 영역 (📌 고정폭 폰트로 변경)
        self.table = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=13)  # 👈 고정폭 폰트
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

        # 초기화
        self.refresh()

    def refresh(self):
        try:
            nodes = get_nodes()
            self.nodes_cache = nodes

            # 상태별 카운트
            counts = {"IDLE": 0, "ALLOC": 0, "DRAIN": 0, "DOWN": 0}
            for n in nodes:
                s = n["state"].upper()
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
            self.display_nodes(
                [n for n in nodes if self._match_filter(n)] if self.current_filter else nodes
            )

        except Exception as e:
            self.table.delete("1.0", "end")
            self.table.insert("end", f"❌ Error fetching nodes: {e}\n", "down")
        finally:
            self.after(60000, self.refresh)

    def display_nodes(self, nodes):
        """📊 표시 정렬 및 폭 조정"""
        self.table.delete("1.0", "end")
        # 폭을 살짝 넉넉하게 조정
        self.table.insert("end", f"{'Node':22} {'State':15} {'CPU':14} {'Mem':12} {'GPU':18}\n", "default")
        self.table.insert("end", "-" * 90 + "\n", "default")

        for n in sorted(nodes, key=lambda x: x["name"]):
            tag = self._get_state_tag(n["state"])
            line = (
                f"{n.get('name', '-')[:22]:22} "
                f"{n.get('state', '-')[:15]:15} "
                f"{n.get('cpu', n.get('cpus', '-'))[:14]:14} "
                f"{n.get('mem', n.get('memory', '-'))[:12]:12} "
                f"{n.get('gpu', n.get('gpus', '-'))[:18]:18}\n"
            )
            self.table.insert("end", line, tag)

    def filter_by_state(self, state):
        if self.current_filter == state:
            self.current_filter = None
        else:
            self.current_filter = state
        self.display_nodes(
            [n for n in self.nodes_cache if self._match_filter(n)] if self.current_filter else self.nodes_cache
        )

    def _match_filter(self, node):
        return self.current_filter and self.current_filter in node["state"].upper()

    def _get_state_tag(self, state):
        s = state.upper()
        if "IDLE" in s:
            return "idle"
        elif "ALLOC" in s:
            return "alloc"
        elif "DOWN" in s:
            return "down"
        elif "DRAIN" in s:
            return "drain"
        return "default"

    def on_click(self, event):
        """노드 클릭 시 상세정보 팝업"""
        index = self.table.index(f"@{event.x},{event.y}")
        line = self.table.get(f"{index} linestart", f"{index} lineend").strip()
        if not line or line.startswith("Node") or line.startswith("-"):
            return
        node_name = line.split()[0]
        threading.Thread(target=self.open_node_detail_popup, args=(node_name,), daemon=True).start()

    def open_node_detail_popup(self, node_name):
        """새 팝업창에서 상세정보 표시"""
        popup = ctk.CTkToplevel(self)
        popup.title(f"🔍 Node Detail: {node_name}")
        popup.geometry("800x600")
        popup.lift()
        popup.focus_force()

        label = ctk.CTkLabel(popup, text=f"Loading node info for {node_name}...", font=ctk.CTkFont(size=14))
        label.pack(pady=10)

        textbox = ctk.CTkTextbox(popup, width=780, height=500, font=ctk.CTkFont(family="Consolas", size=12))
        textbox.pack(padx=10, pady=10, fill="both", expand=True)

        close_btn = ctk.CTkButton(popup, text="닫기", command=popup.destroy)
        close_btn.pack(pady=10)

        try:
            from services import api_client
            res = requests.get(f"{api_client.get_base_url()}/slurm/node/{node_name}", timeout=5)
            res.raise_for_status()
            data = res.json()

            textbox.delete("1.0", "end")
            if isinstance(data, dict):
                for k, v in data.items():
                    textbox.insert("end", f"{k}: {v}\n")
            else:
                textbox.insert("end", str(data))

            label.configure(text=f"Node Detail: {node_name}")

        except Exception as e:
            textbox.delete("1.0", "end")
            textbox.insert("end", f"❌ Error fetching node detail: {e}")
