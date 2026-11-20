"""exe 한 개 두 모드 — Health 창 실행 명령."""
import sys

import runtime


def test_source_run_launches_main_with_health_flag(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    command = runtime.health_command()
    assert command[0] == sys.executable and command[1].endswith("main.py") and command[-1] == runtime.HEALTH_FLAG


def test_exe_relaunches_itself_as_an_independent_instance(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert runtime.health_command() == [sys.executable, runtime.HEALTH_FLAG]
    assert runtime.health_environment()["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
