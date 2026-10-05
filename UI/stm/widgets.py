"""Small widget helpers shared by dialogs and pages."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget


def set_style_property(widget: QWidget, name: str, value: object) -> None:
    """Set a dynamic property used by QSS selectors and re-apply the style."""
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def label(text: str, role: str = "", parent: QWidget | None = None) -> QLabel:
    widget = QLabel(text, parent)
    if role:
        widget.setProperty("role", role)
    return widget


def field_error_label() -> QLabel:
    widget = label("", "fieldError")
    widget.setWordWrap(True)
    widget.hide()
    return widget


def show_field_error(error_label: QLabel, message: str | None) -> None:
    error_label.setText(message or "")
    error_label.setVisible(bool(message))


def button(text: str, variant: str = "", tooltip: str = "") -> QPushButton:
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if variant:
        widget.setProperty("variant", variant)
    if tooltip:
        widget.setToolTip(tooltip)
    return widget


def hairline(orientation: Qt.Orientation = Qt.Orientation.Horizontal) -> QFrame:
    line = QFrame()
    line.setObjectName("Hairline")
    if orientation == Qt.Orientation.Horizontal:
        line.setFixedHeight(1)
    else:
        line.setFixedWidth(1)
    return line


class Banner(QFrame):
    """Inline message strip used for form-level errors."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Banner")
        self._text = QLabel(self)
        self._text.setWordWrap(True)
        self._text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._detail = label("", "bannerDetail", self)
        self._detail.setWordWrap(True)
        self._detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        layout.addWidget(self._text)
        layout.addWidget(self._detail)
        self.hide()

    def show_message(self, message: str, detail: str = "") -> None:
        self._text.setText(message)
        self._detail.setText(detail)
        self._detail.setVisible(bool(detail))
        self.show()

    def clear(self) -> None:
        self.hide()
