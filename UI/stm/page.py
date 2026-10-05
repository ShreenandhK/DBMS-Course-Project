"""Base class and header for every page shown in the main window."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLayout, QVBoxLayout, QWidget

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

    def export_csv(self) -> None:
        """Ctrl+E."""

    def focus_main(self) -> None:
        self.setFocus()


def mono_span(text: str) -> str:
    return f"<span style=\"font-family:'Cascadia Mono','Consolas'\">{text}</span>"


def steps(*items: str) -> str:
    """Numbered steps on one line, e.g. '1 Choose …   2 Add …'."""
    return "&nbsp;&nbsp;&nbsp;".join(f"<b>{number}</b>&nbsp;{item}" for number, item in enumerate(items, 1))


def _rich_label(text: str, role: str) -> QLabel:
    widget = label(text, role)
    widget.setTextFormat(Qt.TextFormat.RichText)
    widget.setWordWrap(True)
    return widget


def page_header(
    title: str,
    subtitle: str,
    actions: QLayout | None = None,
    extra: QLayout | None = None,
    detail: str = "",
) -> QWidget:
    """White header strip.

    ``subtitle`` says in plain words what the page is for; ``detail`` (smaller, fainter) carries
    steps or the tables involved. ``actions`` sit on the right; ``extra`` is a row underneath.
    """
    titles = QVBoxLayout()
    titles.setSpacing(2)
    titles.addWidget(label(title, "pageTitle"))
    titles.addWidget(_rich_label(subtitle, "muted"))
    if detail:
        titles.addWidget(_rich_label(detail, "pageDetail"))

    # The text column takes the free width (a stretch here would squeeze the wrapped labels).
    top = QHBoxLayout()
    top.setSpacing(24)
    top.addLayout(titles, 1)
    if actions is not None:
        top.addLayout(actions)
        top.setAlignment(actions, Qt.AlignmentFlag.AlignTop)

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
