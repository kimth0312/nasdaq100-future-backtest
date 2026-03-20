"""
NQ Backtester 앱 진입점
"""
import logging
import sys
from pathlib import Path

# src 디렉토리를 PYTHONPATH에 추가 (PyInstaller 실행 시 대비)
src_dir = Path(__file__).parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from ui.main_window import MainWindow

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("NQ Backtester")
    app.setOrganizationName("NQBacktester")

    # 다크 스타일
    app.setStyle("Fusion")

    from PySide6.QtGui import QPalette, QColor
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#1E1E1E"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#CCCCCC"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#2A2A2A"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#333333"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#333333"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#CCCCCC"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#333333"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#CCCCCC"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#3498DB"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#3498DB"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)

    window = MainWindow()
    window.setMinimumSize(1200, 800)
    window.show()

    sys.exit(app.exec())
