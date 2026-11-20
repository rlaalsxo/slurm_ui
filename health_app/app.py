"""Node Health 창 실행(Qt). SlurmUI.exe --health 또는 slurm_ui 의 [Health 창 열기] 버튼으로 뜬다."""
import sys

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from health_app.theme import STYLE_SHEET, UI_FONT
from health_app.window import HealthWindow
from runtime import resource_path


def run():
    app = QApplication(sys.argv)
    app.setApplicationName("Node Health")
    app.setStyle("Fusion")
    app.setFont(QFont(UI_FONT, 10))
    app.setStyleSheet(STYLE_SHEET)
    app.setWindowIcon(QIcon(resource_path("curie.ico")))
    window = HealthWindow()
    window.show()
    return app.exec()
