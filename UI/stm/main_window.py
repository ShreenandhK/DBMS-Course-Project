"""Application main window."""
from __future__ import annotations

from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QWidget

from stm import APP_NAME
from stm.db import Database


class MainWindow(QMainWindow):
    def __init__(self, database: Database) -> None:
        super().__init__()
        self._db = database
        self.setWindowTitle(APP_NAME)
        self.resize(1360, 820)

        self._connection_label = QLabel(f"{database.info.label}   ·   MySQL {database.server_version}")
        self._message_label = QLabel()
        self._count_label = QLabel()

        self._build_central()
        self._build_status_bar()
        self._build_menu()

    def _build_central(self) -> None:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setCentralWidget(central)

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)
        bar.addWidget(self._connection_label)
        bar.addWidget(self._message_label, 1)
        bar.addPermanentWidget(self._count_label)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        quit_action = QAction("E&xit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def show_message(self, text: str) -> None:
        self._message_label.setText(text)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._db.close()
        super().closeEvent(event)
