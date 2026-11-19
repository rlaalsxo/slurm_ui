import tkinter

import pytest


@pytest.fixture(scope="session")
def tk_root():
    """Tk 창은 테스트 전체에서 하나만 — Windows 에서 한 프로세스가 Tk 를 여러 번 만들면 가끔 tk.tcl 을 못 찾는다."""
    ctk = pytest.importorskip("customtkinter")
    try:
        window = ctk.CTk()
    except tkinter.TclError as exc:
        pytest.skip(f"no display: {exc}")
    window.withdraw()
    yield window
    window.destroy()
