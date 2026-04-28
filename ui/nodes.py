import customtkinter as ctk
from tkinter import messagebox

from services.api_client import drain_node, get_node_detail, get_nodes, resume_node
from ui.background import BackgroundTaskMixin, run_detached
from ui.job_utils import cell, safe_text


class NodesFrame(BackgroundTaskMixin, ctk.CTkFrame):
    STATES = ("IDLE", "ALLOC", "DRAIN", "DOWN")
    STATE_COLORS = {
        "IDLE": "#00ff66",
        "ALLOC": "#66aaff",
        "DRAIN": "#ffcc00",
        "DOWN": "#ff3333",
    }

    def __init__(self, master):
        super().__init__(master)
        self._init_background_tasks()
        self.current_filter = None
        self.nodes_cache = []
        self._refreshing = False
        self._auto_after_id = None
        self._auto_interval = 600000

        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", padx=10, pady=(10, 5))

        self.title_label = ctk.CTkLabel(
            top_frame,
            text="Slurm Nodes (Node Status Monitor)",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.title_label.pack(side="left", padx=5)

        self.refresh_button = ctk.CTkButton(
            top_frame,
            text="Refresh",
            width=120,
            command=self.on_manual_refresh,
        )
        self.refresh_button.pack(side="right", padx=5)

        self.stats_frame = ctk.CTkFrame(self)
        self.stats_frame.pack(fill="x", padx=10, pady=(0, 5))

        self.stats_labels = {}
        for state in self.STATES:
            btn = ctk.CTkButton(
                self.stats_frame,
                text=f"{state}: 0",
                width=120,
                command=lambda s=state: self.filter_by_state(s),
            )
            btn.pack(side="left", padx=8, pady=5)
            self.stats_labels[state] = btn

        self.table = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=13),
        )
        self.table.pack(fill="both", expand=True, padx=10, pady=10)

        self.table.tag_config("idle", foreground="#00ff66")
        self.table.tag_config("alloc", foreground="#66aaff")
        self.table.tag_config("down", foreground="#ff3333")
        self.table.tag_config("drain", foreground="#ffcc00")
        self.table.tag_config("default", foreground="#cccccc")

        self.table.bind("<Button-1>", self.on_click)

        self.fetch_and_render()
        self.start_auto_refresh()

    def on_manual_refresh(self):
        if not self._refreshing:
            self.fetch_and_render()

    def start_auto_refresh(self):
        if self._auto_after_id is None:
            self._auto_after_id = self.after(self._auto_interval, self._auto_tick)

    def stop_auto_refresh(self):
        if self._auto_after_id is None:
            return
        try:
            self.after_cancel(self._auto_after_id)
        except Exception:
            pass
        finally:
            self._auto_after_id = None

    def _auto_tick(self):
        if not self._refreshing:
            self.fetch_and_render()
        self._auto_after_id = self.after(self._auto_interval, self._auto_tick)

    def fetch_and_render(self):
        self.run_background(
            task=get_nodes,
            on_start=self._begin_refresh,
            on_success=self._set_nodes,
            on_error=lambda exc: self._show_error(f"Error fetching nodes: {exc}"),
            on_done=self._finish_refresh,
        )

    def _set_nodes(self, nodes):
        self.nodes_cache = nodes
        self._update_state_counts(nodes)
        self.display_nodes(self._filtered_nodes())

    def _update_state_counts(self, nodes):
        counts = {state: 0 for state in self.STATES}
        for node in nodes:
            state = safe_text(node.get("state"), "").upper()
            for known_state in self.STATES:
                if known_state in state:
                    counts[known_state] += 1
                    break

        for state, btn in self.stats_labels.items():
            btn.configure(
                text=f"{state}: {counts[state]}",
                fg_color=("gray20", "gray25"),
                hover_color=self.STATE_COLORS[state],
            )

    def display_nodes(self, nodes):
        self.table.delete("1.0", "end")
        self.table.insert("end", f"{'Node':22} {'State':15} {'CPU':14} {'Mem':12} {'GPU':18}\n", "default")
        self.table.insert("end", "-" * 90 + "\n", "default")

        for node in sorted(nodes, key=lambda item: safe_text(item.get("name"), "")):
            self.table.insert("end", self._format_node_line(node), self._get_state_tag(node.get("state")))

    def _format_node_line(self, node):
        return (
            f"{cell(node.get('name'), 22)} "
            f"{cell(node.get('state'), 15)} "
            f"{cell(node.get('cpu', node.get('cpus')), 14)} "
            f"{cell(node.get('mem', node.get('memory')), 12)} "
            f"{cell(node.get('gpu', node.get('gpus')), 18)}\n\n"
        )

    def filter_by_state(self, state):
        self.current_filter = None if self.current_filter == state else state
        self.display_nodes(self._filtered_nodes())

    def _filtered_nodes(self):
        if not self.current_filter:
            return self.nodes_cache
        return [node for node in self.nodes_cache if self._match_filter(node)]

    def _match_filter(self, node):
        return self.current_filter in safe_text(node.get("state"), "").upper()

    def _get_state_tag(self, state):
        state = safe_text(state, "").upper()
        if "IDLE" in state:
            return "idle"
        if "ALLOC" in state:
            return "alloc"
        if "DOWN" in state:
            return "down"
        if "DRAIN" in state:
            return "drain"
        return "default"

    def on_click(self, event):
        index = self.table.index(f"@{event.x},{event.y}")
        line = self.table.get(f"{index} linestart", f"{index} lineend").strip()
        if not line or line.startswith("Node") or line.startswith("-"):
            return

        self.table.tag_add("highlight", f"{index} linestart", f"{index} lineend")
        self.table.tag_config("highlight", background="#333333")
        self.after(250, lambda: self.table.tag_remove("highlight", "1.0", "end"))

        self.open_node_detail_popup(line.split()[0])

    def open_node_detail_popup(self, node_name):
        popup = ctk.CTkToplevel(self)
        popup.title(f"Node Detail: {node_name}")
        popup.geometry("900x700")
        popup.transient(self.winfo_toplevel())
        popup.attributes("-topmost", True)
        popup.after(300, lambda: popup.attributes("-topmost", False))
        popup.lift()
        popup.focus_force()

        label = ctk.CTkLabel(
            popup,
            text=f"Loading node info for {node_name}...",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        label.pack(pady=10)

        textbox = ctk.CTkTextbox(
            popup,
            width=850,
            height=520,
            font=ctk.CTkFont(family="Consolas", size=13),
        )
        textbox.pack(padx=15, pady=10, fill="both", expand=True)

        self._configure_detail_tags(textbox)

        btn_frame = ctk.CTkFrame(popup)
        btn_frame.pack(pady=(0, 15))

        drain_btn = ctk.CTkButton(
            btn_frame,
            text="Drain",
            width=100,
            fg_color="#cc7700",
            hover_color="#ff9900",
            command=lambda: self._confirm_node_action(popup, node_name, "Drain", drain_node),
        )
        drain_btn.pack(side="left", padx=5)

        resume_btn = ctk.CTkButton(
            btn_frame,
            text="Resume",
            width=100,
            fg_color="#007744",
            hover_color="#00aa66",
            command=lambda: self._confirm_node_action(popup, node_name, "Resume", resume_node),
        )
        resume_btn.pack(side="left", padx=5)

        ctk.CTkButton(btn_frame, text="Close", width=100, command=popup.destroy).pack(side="left", padx=5)

        run_detached(
            popup,
            task=lambda: get_node_detail(node_name),
            on_success=lambda data: self._render_node_detail(textbox, label, node_name, data),
            on_error=lambda exc: self._render_detail_error(textbox, exc),
        )

    def _confirm_node_action(self, popup, node_name, action_name, action):
        if not messagebox.askyesno(action_name + " Node", f"{action_name} node {node_name}?"):
            return

        run_detached(
            popup,
            task=lambda: action(node_name),
            on_success=lambda _: self._finish_node_action(popup, node_name, action_name),
            on_error=lambda exc: messagebox.showerror("Error", f"{action_name} failed: {exc}"),
        )

    def _finish_node_action(self, popup, node_name, action_name):
        past_tense = "resumed" if action_name.lower() == "resume" else "drained"
        messagebox.showinfo("Success", f"{node_name} {past_tense}")
        self.fetch_and_render()
        popup.destroy()

    def _configure_detail_tags(self, textbox):
        textbox.tag_config("key", foreground="#00ccff")
        textbox.tag_config("ok", foreground="#00ff66")
        textbox.tag_config("warn", foreground="#ffcc00")
        textbox.tag_config("error", foreground="#ff5555")
        textbox.tag_config("default", foreground="#cccccc")

    def _render_node_detail(self, textbox, label, node_name, data):
        textbox.delete("1.0", "end")
        if isinstance(data, dict):
            self._render_node_detail_dict(textbox, data)
        else:
            textbox.insert("end", safe_text(data), "default")
        label.configure(text=f"Node Detail: {node_name}")

    def _render_node_detail_dict(self, textbox, data):
        max_key_len = max(len(key) for key in data.keys()) if data else 0
        for key, value in data.items():
            value_text = safe_text(value)
            textbox.insert("end", f"{key:<{max_key_len}} : ", "key")
            textbox.insert("end", f"{value_text}\n", self._detail_value_tag(key, value_text))

    def _detail_value_tag(self, key, value):
        key = key.lower()
        state = value.upper()
        if key in ("state", "reason"):
            if "DOWN" in state or "FAIL" in state:
                return "error"
            if "DRAIN" in state or "RESERVED" in state:
                return "warn"
            if "IDLE" in state or "ALLOC" in state:
                return "ok"
        if any(part in key for part in ("cpu", "mem", "gpu", "gres")) and (value.isdigit() or "G" in state):
            return "ok"
        if "error" in value.lower():
            return "error"
        return "default"

    def _render_detail_error(self, textbox, exc):
        textbox.delete("1.0", "end")
        textbox.insert("end", f"Error fetching node detail: {exc}", "error")

    def _begin_refresh(self):
        self._refreshing = True
        self.refresh_button.configure(state="disabled")

    def _finish_refresh(self):
        self.refresh_button.configure(state="normal")
        self._refreshing = False

    def _show_error(self, message):
        self.table.delete("1.0", "end")
        self.table.insert("end", f"{message}\n", "down")

    def refresh(self):
        self.cancel_background_tasks()
        self._refreshing = False
        self.fetch_and_render()

    def destroy(self):
        self.cancel_background_tasks()
        self.stop_auto_refresh()
        super().destroy()
