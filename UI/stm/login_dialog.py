"""Startup dialog that opens the database connection."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from stm import APP_NAME, credentials
from stm.db import ConnectionInfo, Database, DbError
from stm.widgets import Banner, button, hairline, label


class LoginDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database: Database | None = None
        self.setWindowTitle(APP_NAME)
        self.setObjectName("LoginDialog")
        self.setMinimumWidth(440)

        saved = credentials.load()
        self._host = QLineEdit(saved.info.host)
        self._port = QLineEdit(str(saved.info.port))
        self._port.setValidator(QIntValidator(1, 65535, self))
        self._port.setFixedWidth(72)
        self._user = QLineEdit(saved.info.user)
        self._database_name = QLineEdit(saved.info.database)
        self._password = QLineEdit(saved.password)
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._remember = QCheckBox("Remember password on this computer")
        self._remember.setChecked(saved.remember)
        self._banner = Banner()
        self._connect = button("Connect", "primary")
        self._connect.setDefault(True)
        self._cancel = button("Cancel")

        self._build_layout()
        self._connect.clicked.connect(self._attempt_connect)
        self._cancel.clicked.connect(self.reject)
        (self._password if not saved.password else self._connect).setFocus()

    def _build_layout(self) -> None:
        header = QVBoxLayout()
        header.setSpacing(2)
        header.addWidget(label(APP_NAME, "dialogTitle"))
        header.addWidget(label("Connect to the MySQL server", "muted"))

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        host_row = QHBoxLayout()
        host_row.setSpacing(8)
        host_row.addWidget(self._host, 1)
        host_row.addWidget(label("Port", "fieldLabel"))
        host_row.addWidget(self._port)
        rows: list[tuple[str, QWidget | QHBoxLayout]] = [
            ("Host", host_row),
            ("User", self._user),
            ("Database", self._database_name),
            ("Password", self._password),
        ]
        for index, (caption, widget) in enumerate(rows):
            form.addWidget(label(caption, "fieldLabel"), index, 0)
            if isinstance(widget, QHBoxLayout):
                form.addLayout(widget, index, 1)
            else:
                form.addWidget(widget, index, 1)
        form.addWidget(self._remember, len(rows), 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._cancel)
        buttons.addWidget(self._connect)

        body = QVBoxLayout()
        body.setContentsMargins(20, 18, 20, 16)
        body.setSpacing(14)
        body.addLayout(header)
        body.addWidget(hairline())
        body.addLayout(form)
        body.addWidget(self._banner)
        body.addLayout(buttons)
        self.setLayout(body)

    def _collect(self) -> ConnectionInfo | None:
        host = self._host.text().strip()
        user = self._user.text().strip()
        database = self._database_name.text().strip()
        port_text = self._port.text().strip()
        if not (host and user and database and port_text):
            self._banner.show_message("Host, port, user and database are required.")
            return None
        port = int(port_text)
        if not 1 <= port <= 65535:
            self._banner.show_message("Port must be between 1 and 65535.")
            return None
        return ConnectionInfo(host=host, port=port, user=user, database=database)

    def _attempt_connect(self) -> None:
        self._banner.clear()
        info = self._collect()
        if info is None:
            return
        password = self._password.text()
        self._set_busy(True)
        try:
            self.database = Database(info, password)
        except DbError as err:
            self._set_busy(False)
            self._banner.show_message(err.message)
            self._password.setFocus()
            self._password.selectAll()
            return
        self._set_busy(False)
        credentials.save(info, password, self._remember.isChecked())
        self.accept()

    def _set_busy(self, busy: bool) -> None:
        self._connect.setEnabled(not busy)
        self._connect.setText("Connecting…" if busy else "Connect")
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            QApplication.processEvents()
        else:
            QApplication.restoreOverrideCursor()
