import tkinter

import customtkinter as ctk

VISIBLE_ROWS = 15
WHEEL_DELTA_PER_NOTCH = 120
ROWS_PER_NOTCH = 3


def _wheel_step(event):
    """아래로 굴리면 +1, 위로 굴리면 -1 (Windows 는 delta, Linux 는 Button-4/5)."""
    return 1 if getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0 else -1


class ScrollableOptionMenu(ctk.CTkOptionMenu):
    """항목이 많은 필터용. 기본 드롭다운(Windows 네이티브 메뉴)은 휠로 스크롤되지 않아 Listbox 팝업으로 연다.

    닫힌 상태에서 휠을 굴리면 이전·다음 항목으로 바뀐다(기존 Model·Account 필터 동작).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._popup = None
        self._listbox = None
        self.bind_wheel_cycle(self)

    def bind_wheel_cycle(self, widget):
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(sequence, self._cycle_with_wheel)

    def _cycle_with_wheel(self, event):
        values = self.cget("values")
        if len(values) > 1:
            index = values.index(self.get()) if self.get() in values else 0
            self._dropdown_callback(values[(index + _wheel_step(event)) % len(values)])
        return "break"

    def _clicked(self, event=0):
        if self._popup is not None:
            self._close_popup()
        elif self._state is not tkinter.DISABLED and self.cget("values"):
            self._open_popup()

    def _open_popup(self):
        values = self.cget("values")
        font = ctk.CTkFont(size=13)
        popup = tkinter.Toplevel(self)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)

        fg = self._apply_appearance_mode(ctk.ThemeManager.theme["DropdownMenu"]["fg_color"])
        hover = self._apply_appearance_mode(ctk.ThemeManager.theme["DropdownMenu"]["hover_color"])
        text = self._apply_appearance_mode(ctk.ThemeManager.theme["DropdownMenu"]["text_color"])

        rows = min(len(values), VISIBLE_ROWS)
        listbox = tkinter.Listbox(
            popup, font=font, height=rows, activestyle="none", exportselection=False, borderwidth=0,
            highlightthickness=1, highlightbackground=hover, bg=fg, fg=text,
            selectbackground=hover, selectforeground=text, cursor="hand2",
        )
        listbox.insert("end", *values)
        listbox.pack(side="left", fill="both", expand=True)
        if len(values) > rows:
            scrollbar = tkinter.Scrollbar(popup, command=listbox.yview)
            scrollbar.pack(side="right", fill="y")
            listbox.configure(yscrollcommand=scrollbar.set)
            scrollbar.bind("<MouseWheel>", self._scroll_popup)

        current = values.index(self.get()) if self.get() in values else 0
        listbox.selection_set(current)
        listbox.see(current)

        listbox.bind("<MouseWheel>", self._scroll_popup)
        listbox.bind("<Button-4>", self._scroll_popup)
        listbox.bind("<Button-5>", self._scroll_popup)
        listbox.bind("<Motion>", self._hover_row)
        listbox.bind("<ButtonRelease-1>", lambda event: self._choose(listbox.nearest(event.y)))
        listbox.bind("<Return>", lambda _: self._choose(listbox.curselection()[0]) if listbox.curselection() else None)
        listbox.bind("<Escape>", lambda _: self._close_popup())
        listbox.bind("<FocusOut>", lambda _: self.after(50, self._close_if_app_lost_focus))
        popup.bind("<ButtonPress-1>", self._close_if_outside, add=True)

        self._popup, self._listbox = popup, listbox
        self._place_popup(popup, font, values)
        # 앱 안 다른 곳을 눌러도 팝업이 받도록 잡는다(바깥 클릭이면 닫는다).
        popup.grab_set()
        listbox.focus_force()

    def _place_popup(self, popup, font, values):
        popup.update_idletasks()
        width = max(self.winfo_width(), max(font.measure(value) for value in values) + 40)
        height = popup.winfo_reqheight()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        if y + height > self.winfo_screenheight():
            y = self.winfo_rooty() - height  # 화면 아래로 넘치면 위로 연다
        popup.geometry(f"{width}x{height}+{x}+{y}")

    def _scroll_popup(self, event):
        delta = getattr(event, "delta", 0)
        notches = max(1, abs(delta) // WHEEL_DELTA_PER_NOTCH) if delta else 1
        self._listbox.yview_scroll(_wheel_step(event) * notches * ROWS_PER_NOTCH, "units")
        return "break"

    def _hover_row(self, event):
        self._listbox.selection_clear(0, "end")
        self._listbox.selection_set(self._listbox.nearest(event.y))

    def _close_if_outside(self, event):
        popup = self._popup
        if popup is None:
            return
        inside_x = popup.winfo_rootx() <= event.x_root < popup.winfo_rootx() + popup.winfo_width()
        inside_y = popup.winfo_rooty() <= event.y_root < popup.winfo_rooty() + popup.winfo_height()
        if not (inside_x and inside_y):
            self._close_popup()
            return "break"

    def _close_if_app_lost_focus(self):
        """다른 프로그램으로 넘어가면 닫는다. 스크롤바처럼 앱 안에서 포커스가 옮겨 간 것은 그대로 둔다."""
        if self._popup is not None and self._popup.focus_get() is None:
            self._close_popup()

    def _choose(self, index):
        value = self._listbox.get(index)
        self._close_popup()
        self._dropdown_callback(value)

    def _close_popup(self):
        if self._popup is None:
            return
        popup, self._popup, self._listbox = self._popup, None, None
        popup.grab_release()
        popup.destroy()

    def destroy(self):
        self._close_popup()
        super().destroy()
