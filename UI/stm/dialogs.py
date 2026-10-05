"""Delete confirmation and error dialogs."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from stm import theme
from stm.schema import TableSpec
from stm.widgets import button, label

MAX_LISTED = 8


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


class _Dialog(QDialog):
    def __init__(self, title: str, parent: QWidget | None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(22, 18, 22, 16)
        self.body.setSpacing(12)
        self.body.addWidget(label(title, "dialogTitle"))

    def showEvent(self, event: QShowEvent) -> None:
        # Top-level windows ignore height-for-width; fit the wrapped text explicitly.
        super().showEvent(event)
        layout = self.layout()
        if layout is not None and layout.hasHeightForWidth():
            self.resize(self.width(), layout.totalHeightForWidth(self.width()))

    def add_text(self, text: str, role: str = "") -> QLabel:
        widget = label(text, role)
        widget.setWordWrap(True)
        widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.addWidget(widget)
        return widget

    def add_buttons(self, *buttons: QWidget) -> None:
        row = QHBoxLayout()
        row.addStretch(1)
        for widget in buttons:
            row.addWidget(widget)
        self.body.addSpacing(4)
        self.body.addLayout(row)


class ConfirmDeleteDialog(_Dialog):
    def __init__(
        self, spec: TableSpec, records: list[str], cascades: list[str], parent: QWidget | None = None
    ) -> None:
        count = len(records)
        title = f"Delete {spec.singular}?" if count == 1 else f"Delete {count} rows from {spec.name}?"
        super().__init__(title, parent)

        intro = "You are about to delete:" if count > 1 else "You are about to delete"
        self.add_text(intro, "muted")
        self.body.addWidget(self._record_list(records))
        if cascades:
            self.add_text(f"This also deletes {_join(cascades)} (ON DELETE CASCADE).", "warning")
        self.add_text(
            f"Runs DELETE on table {spec.name} in one transaction. This cannot be undone.",
            "faint",
        )

        cancel = button("Cancel")
        confirm = button("Delete", "dangerSolid")
        cancel.clicked.connect(self.reject)
        confirm.clicked.connect(self.accept)
        self.add_buttons(cancel, confirm)
        cancel.setDefault(True)
        cancel.setFocus()

    @staticmethod
    def _record_list(records: list[str]) -> QFrame:
        frame = QFrame()
        frame.setObjectName("RecordList")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)
        for record in records[:MAX_LISTED]:
            item = QLabel(record[0].upper() + record[1:])
            item.setWordWrap(True)
            layout.addWidget(item)
        if len(records) > MAX_LISTED:
            layout.addWidget(label(f"…and {len(records) - MAX_LISTED} more", "muted"))
        return frame


class ErrorDialog(_Dialog):
    def __init__(self, title: str, message: str, detail: str = "", parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        self.message = message
        self.add_text(message)
        if detail:
            detail_label = self.add_text(detail, "detail")
            detail_label.setFont(theme.mono_font(8.5))
        close = button("Close", "primary")
        close.clicked.connect(self.accept)
        close.setDefault(True)
        self.add_buttons(close)


def show_error(parent: QWidget | None, title: str, message: str, detail: str = "") -> None:
    ErrorDialog(title, message, detail, parent).exec()
