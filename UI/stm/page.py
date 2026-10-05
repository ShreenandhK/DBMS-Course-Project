"""Base class and header for every page shown in the main window."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLayout, QVBoxLayout, QWidget

from stm.widgets import label


class Page(QWidget):
    """A main-window page. Subclasses override the hooks they support."""

    message = Signal(str)
    data_changed = Signal()
    counts_changed = Signal(int, int)  # visible rows, total rows; pages without a grid never emit

    shows_counts = False
    title = ""

    def activate(self) -> None:
        """Called every time the page is shown; reload whatever may be stale."""

    def refresh(self) -> bool:
        self.activate()
        return True

    def new_record(self) -> None:
        """Ctrl+N."""

    def delete_selected(self) -> None:
        """Del."""

    def focus_filter(self) -> None:
        """Ctrl+F."""

    def focus_main(self) -> None:
        self.setFocus()


def mono_span(text: str) -> str:
    return f"<span style=\"font-family:'Cascadia Mono','Consolas'\">{text}</span>"


def page_header(title: str, subtitle: str, actions: QLayout | None = None, extra: QLayout | None = None) -> QWidget:
    """White header strip: title, rich-text subtitle, optional right-aligned actions and a second row."""
    subtitle_label = label(subtitle, "muted")
    subtitle_label.setTextFormat(Qt.TextFormat.RichText)
    titles = QVBoxLayout()
    titles.setSpacing(2)
    titles.addWidget(label(title, "pageTitle"))
    titles.addWidget(subtitle_label)

    top = QHBoxLayout()
    top.addLayout(titles)
    top.addStretch(1)
    if actions is not None:
        top.addLayout(actions)

    header = QWidget()
    header.setObjectName("PageHeader")
    header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    layout = QVBoxLayout(header)
    layout.setContentsMargins(20, 14, 20, 12)
    layout.setSpacing(12)
    layout.addLayout(top)
    if extra is not None:
        layout.addLayout(extra)
    return header
