"""필터 드롭다운 휠 스크롤(11-17). Windows 기본 드롭다운은 휠이 안 먹어서 Listbox 팝업으로 바꿨다."""
import tkinter
from types import SimpleNamespace

import pytest

ctk = pytest.importorskip("customtkinter")

from ui.scroll_option_menu import VISIBLE_ROWS, ScrollableOptionMenu  # noqa: E402

VALUES = ["All"] + [f"user{i}@x.com" for i in range(40)]


@pytest.fixture
def menu():
    try:
        root = ctk.CTk()
    except tkinter.TclError as exc:
        pytest.skip(f"no display: {exc}")
    root.withdraw()
    chosen = []
    widget = ScrollableOptionMenu(root, values=VALUES, command=chosen.append)
    widget.pack()
    root.update()
    widget.chosen = chosen
    yield widget
    widget.destroy()
    root.destroy()


def wheel(delta):
    return SimpleNamespace(delta=delta, num="??")


def test_wheel_on_closed_menu_moves_to_next_and_previous_value(menu):
    menu._cycle_with_wheel(wheel(-120))
    menu._cycle_with_wheel(wheel(-120))
    menu._cycle_with_wheel(wheel(120))
    assert menu.get() == VALUES[1]
    assert menu.chosen == [VALUES[1], VALUES[2], VALUES[1]]


def test_open_list_scrolls_with_wheel_and_selects_clicked_value(menu):
    menu._clicked()
    menu.update()
    listbox = menu._listbox
    assert int(listbox.cget("height")) == VISIBLE_ROWS
    assert listbox.nearest(0) == 0

    menu._scroll_popup(wheel(-120))
    menu.update()
    top = listbox.nearest(0)
    assert top > 0

    menu._choose(top)
    assert menu._popup is None
    assert menu.get() == VALUES[top]
    assert menu.chosen == [VALUES[top]]


def test_clicking_menu_again_closes_the_list(menu):
    menu._clicked()
    menu._clicked()
    assert menu._popup is None and menu.chosen == []
