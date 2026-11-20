"""SlurmUI.exe — 그냥 실행하면 Slurm Monitor(Tk), --health 로 실행하면 Node Health(Qt).

Tk 와 Qt 는 한 프로세스에 섞을 수 없어서 모드마다 필요한 쪽만 불러온다.
"""
import logging
import sys
import traceback

from runtime import HEALTH_FLAG, log_path

logging.basicConfig(
    filename=log_path(),
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _log_uncaught(exc_type, exc_value, exc_tb):
    # 창 모드 exe 는 콘솔이 없어 Qt 콜백 안의 오류가 그냥 사라진다 — 로그 파일에 남긴다
    logger.error("Uncaught exception:\n%s", "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))


def main():
    sys.excepthook = _log_uncaught
    if HEALTH_FLAG in sys.argv[1:]:
        from health_app.app import run
    else:
        from ui.app import run
    return run()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        logger.critical(f"Fatal exception:\n{traceback.format_exc()}")
        sys.exit(1)
