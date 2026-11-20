"""node_manager 호출을 화면이 멈추지 않게 뒤에서 돌리고, 결과는 Qt 메인 스레드에서 받는다."""
import threading

from PySide6.QtCore import QObject, Signal, Slot


class TaskRunner(QObject):
    """task 는 작업 스레드에서, on_success/on_error 는 메인 스레드에서 부른다.

    스레드는 daemon — 창을 닫을 때 응답을 기다리느라(최대 120초) 프로그램이 안 꺼지는 일이 없게 한다.
    주인 위젯이 먼저 닫히면 이 객체도 지워지고, 늦게 온 결과는 버린다.
    """

    _finished = Signal(object, object)

    def __init__(self, parent):
        super().__init__(parent)
        self._finished.connect(self._deliver)

    def run(self, task, on_success, on_error=None):
        def work():
            try:
                callback, value = on_success, task()
            except Exception as exc:  # 네트워크·HTTP 오류는 화면에 보여 주려고 그대로 넘긴다
                callback, value = on_error, exc
            if callback is None:
                return
            try:
                self._finished.emit(callback, value)
            except RuntimeError:  # 기다리는 사이 창이 닫혀 이 객체가 지워졌다 — 받을 곳이 없다
                return

        threading.Thread(target=work, daemon=True).start()

    @Slot(object, object)
    def _deliver(self, callback, value):
        callback(value)
