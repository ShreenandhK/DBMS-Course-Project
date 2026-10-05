"""Panel listing every write statement the app sends, with its outcome."""
from __future__ import annotations

import html
from datetime import date
from typing import Any

from PySide6.QtWidgets import QFrame, QHBoxLayout, QPlainTextEdit, QVBoxLayout, QWidget

from stm import theme
from stm.db import StatementRecord
from stm.widgets import button, label

_MUTED = "#6B7680"
_ERROR = "#A33A3A"
_OK = "#1E6B3A"
_KEYWORDS = {"START TRANSACTION", "COMMIT", "ROLLBACK"}


def _format_param(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, date):
        return f"'{value.isoformat()}'"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return str(value)


class ActivityLog(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ActivityPanel")
        self._text = QPlainTextEdit()
        self._text.setObjectName("ActivityLog")
        self._text.setReadOnly(True)
        self._text.setFont(theme.mono_font(9))
        self._text.setMaximumBlockCount(2000)
        self._text.setPlaceholderText("Statements sent by inserts, deletes and workflows appear here.")
        clear = button("Clear", "flat")
        clear.clicked.connect(self._text.clear)

        bar = QWidget()
        bar.setObjectName("ActivityBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 3, 8, 3)
        bar_layout.addWidget(label("SQL activity", "panelTitle"))
        bar_layout.addStretch(1)
        bar_layout.addWidget(clear)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(bar)
        layout.addWidget(self._text, 1)

    def text(self) -> str:
        return self._text.toPlainText()

    def record(self, entry: StatementRecord) -> None:
        stamp = f'<span style="color:{_MUTED}">{entry.at:%H:%M:%S}</span>&nbsp;&nbsp;'
        if entry.sql in _KEYWORDS:
            color = _ERROR if entry.sql == "ROLLBACK" else _MUTED
            self._append(f'{stamp}<span style="color:{color}">{entry.sql}</span>')
            return
        params = ", ".join(_format_param(p) for p in entry.params)
        line = f"{stamp}{html.escape(entry.sql)}"
        if params:
            line += f'&nbsp;&nbsp;<span style="color:{_MUTED}">[{html.escape(params)}]</span>'
        if entry.error:
            line += f'&nbsp;&nbsp;<span style="color:{_ERROR}">ERROR {html.escape(entry.error)}</span>'
        else:
            rows = entry.rowcount if entry.rowcount is not None else 0
            line += f'&nbsp;&nbsp;<span style="color:{_OK}">{rows} row{"s" if rows != 1 else ""} affected</span>'
        self._append(line)

    def _append(self, line: str) -> None:
        self._text.appendHtml(f'<div style="white-space:pre">{line}</div>')
        bar = self._text.verticalScrollBar()
        bar.setValue(bar.maximum())
