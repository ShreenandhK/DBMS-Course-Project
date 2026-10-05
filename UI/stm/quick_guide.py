"""F1 quick guide: how the app is organised, built from the same descriptions as the sidebar."""
from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QWidget

from stm import navigation
from stm.dialogs import BaseDialog
from stm.widgets import button

_SHORTCUTS = (
    ("Ctrl+N", "New record on the current table"),
    ("Del", "Delete the selected rows (asks first)"),
    ("Ctrl+F", "Filter the current list (Esc clears)"),
    ("F5", "Reload the current page from the database"),
    ("Ctrl+E", "Save the rows shown as a CSV file"),
    ("Ctrl+L", "Show or hide the SQL activity panel"),
    ("F1", "This guide"),
)


def _guide_html() -> str:
    parts = [
        "<h3>How stock works</h3>",
        "<p>The database never stores a stock balance. It records <b>movements</b>: receipts, transfers, "
        "dispatches and damage. <b>Bin stock</b> is calculated from them:</p>",
        "<p style='margin-left:12px'>on hand = received + transferred in − transferred out "
        "− dispatched − damaged</p>",
        "<p>To change stock, record a movement with one of the <b>Tasks</b>; Bin stock updates by itself.</p>",
        "<h3>The sidebar</h3>",
    ]
    for group in navigation.GROUPS:
        titles = ", ".join(html.escape(navigation.PAGES[key].title) for key in group.keys)
        parts.append(f"<p><b>{html.escape(group.title)}</b> — {html.escape(group.description)}<br>"
                     f"<span style='color:#6B7680'>{titles}</span></p>")
    parts += [
        "<p>Hover over any sidebar entry for a one-line description.</p>",
        "<h3>Transfers</h3>",
        "<p><b>PENDING</b>: stock still in its bin, reserved &nbsp;→&nbsp; <b>IN_TRANSIT</b>: on the way, "
        "in no bin &nbsp;→&nbsp; <b>CONFIRMED</b>: in the destination bin. <b>CANCELLED</b> has no effect. "
        "Use <b>Process transfers</b> to move a transfer along.</p>",
        "<h3>Keyboard</h3><table cellspacing='0' cellpadding='3'>",
    ]
    parts += [f"<tr><td><b>{key}</b>&nbsp;&nbsp;&nbsp;</td><td>{text}</td></tr>" for key, text in _SHORTCUTS]
    parts.append("</table>")
    return "".join(parts)


class QuickGuideDialog(BaseDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Quick guide", parent)
        self.setMinimumWidth(620)
        content = QLabel(_guide_html())
        content.setTextFormat(Qt.TextFormat.RichText)
        content.setWordWrap(True)
        content.setObjectName("GuideText")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        scroll.setMinimumHeight(min(520, int(parent.height() * 0.7)) if parent else 520)
        self.body.addWidget(scroll, 1)
        close = button("Close", "primary")
        close.clicked.connect(self.accept)
        close.setDefault(True)
        self.add_buttons(close)

    def showEvent(self, event: QShowEvent) -> None:
        # Keep the scroll area's height instead of BaseDialog's fit-to-text resize.
        QWidget.showEvent(self, event)
