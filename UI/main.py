"""Stock Transfer Manager entry point."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QDialog

from stm import APP_NAME, ORG_NAME, theme
from stm.login_dialog import LoginDialog
from stm.main_window import MainWindow

BASE_DIR = Path(__file__).resolve().parent


def load_stylesheet() -> str:
    stylesheet = (BASE_DIR / "style.qss").read_text(encoding="utf-8")
    return stylesheet.replace("@ASSETS@", (BASE_DIR / "assets").as_posix())


def light_palette() -> QPalette:
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: "#F4F5F7",
        QPalette.ColorRole.WindowText: "#1C2127",
        QPalette.ColorRole.Base: "#FFFFFF",
        QPalette.ColorRole.AlternateBase: "#F9FAFB",
        QPalette.ColorRole.Text: "#1C2127",
        QPalette.ColorRole.Button: "#FFFFFF",
        QPalette.ColorRole.ButtonText: "#1C2127",
        QPalette.ColorRole.Highlight: "#DCEAF1",
        QPalette.ColorRole.HighlightedText: "#0E3D52",
        QPalette.ColorRole.PlaceholderText: "#98A1AA",
        QPalette.ColorRole.ToolTipBase: "#1C2127",
        QPalette.ColorRole.ToolTipText: "#FFFFFF",
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    return palette


def create_application() -> QApplication:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setStyle("Fusion")
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    app.setPalette(light_palette())
    app.setFont(theme.ui_font())
    app.setStyleSheet(load_stylesheet())
    return app


def main() -> int:
    app = create_application()
    login = LoginDialog()
    if login.exec() != QDialog.DialogCode.Accepted or login.database is None:
        return 0
    window = MainWindow(login.database)
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
