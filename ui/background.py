import threading


def run_detached(widget, task, on_success, on_error=None):
    def call_on_main(callback, *args):
        if not callback:
            return

        def wrapped():
            if widget.winfo_exists():
                callback(*args)

        try:
            widget.after(0, wrapped)
        except Exception:
            pass

    def worker():
        try:
            result = task()
        except Exception as exc:
            call_on_main(on_error, exc)
        else:
            call_on_main(on_success, result)

    threading.Thread(target=worker, daemon=True).start()


class BackgroundTaskMixin:
    def _init_background_tasks(self):
        self._background_request_id = 0

    def cancel_background_tasks(self):
        self._background_request_id = getattr(self, "_background_request_id", 0) + 1

    def run_background(self, task, on_success, on_error=None, on_start=None, on_done=None):
        self._background_request_id = getattr(self, "_background_request_id", 0) + 1
        request_id = self._background_request_id

        if on_start:
            on_start()

        def is_current():
            return request_id == getattr(self, "_background_request_id", None) and self.winfo_exists()

        def call_on_main(callback, *args):
            if not callback:
                return

            def wrapped():
                if is_current():
                    callback(*args)

            try:
                self.after(0, wrapped)
            except Exception:
                pass

        def worker():
            try:
                result = task()
            except Exception as exc:
                call_on_main(on_error, exc)
            else:
                call_on_main(on_success, result)
            finally:
                call_on_main(on_done)

        threading.Thread(target=worker, daemon=True).start()
        return request_id
