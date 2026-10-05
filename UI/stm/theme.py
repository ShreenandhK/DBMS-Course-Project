"""Fonts and the few colours that are painted in code rather than styled by QSS."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont

UI_FAMILIES = ["Segoe UI Variable Text", "Segoe UI"]
MONO_FAMILIES = ["Cascadia Mono", "Consolas", "Courier New"]

ACCENT = QColor("#18607F")
TEXT = QColor("#1C2127")
TEXT_MUTED = QColor("#5E6A75")
TEXT_FAINT = QColor("#98A1AA")
SIDEBAR_HOVER = QColor("#E4E7EB")
SIDEBAR_SELECTED = QColor("#DCE6EC")
SELECTED_TEXT = QColor("#0E3D52")
NEGATIVE = QColor("#A33A3A")

# Transfer status chips: (background, foreground).
STATUS_COLORS: dict[str, tuple[QColor, QColor]] = {
    "PENDING": (QColor("#ECEEF1"), QColor("#4A5560")),
    "IN_TRANSIT": (QColor("#FBF0D9"), QColor("#8A5A00")),
    "CONFIRMED": (QColor("#E2F1E6"), QColor("#1E6B3A")),
    "CANCELLED": (QColor("#F7E7E7"), QColor("#9A3B3B")),
}


def ui_font(point_size: float = 10, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setFamilies(UI_FAMILIES)
    font.setPointSizeF(point_size)
    font.setWeight(weight)
    return font


def mono_font(point_size: float = 9.5) -> QFont:
    font = QFont()
    font.setFamilies(MONO_FAMILIES)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSizeF(point_size)
    return font
