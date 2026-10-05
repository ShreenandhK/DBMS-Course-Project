"""Left navigation: grouped table list with live row counts."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from stm import theme

KIND_ROLE = Qt.ItemDataRole.UserRole + 1
KEY_ROLE = Qt.ItemDataRole.UserRole + 2
COUNT_ROLE = Qt.ItemDataRole.UserRole + 3

HEADER = "header"
ENTRY = "entry"

AnyIndex = QModelIndex | QPersistentModelIndex


class Sidebar(QListWidget):
    page_selected = Signal(str)

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(228)
        self.setItemDelegate(_SidebarDelegate(self))
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.currentItemChanged.connect(self._on_current_changed)

    def add_group(self, title: str, entries: list[tuple[str, str]]) -> None:
        header = QListWidgetItem(title.upper())
        header.setData(KIND_ROLE, HEADER)
        header.setFlags(Qt.ItemFlag.NoItemFlags)
        self.addItem(header)
        for key, label in entries:
            item = QListWidgetItem(label)
            item.setData(KIND_ROLE, ENTRY)
            item.setData(KEY_ROLE, key)
            self.addItem(item)

    def select(self, key: str) -> None:
        for row in range(self.count()):
            item = self.item(row)
            if item.data(KEY_ROLE) == key:
                self.setCurrentItem(item)
                return

    def set_counts(self, counts: dict[str, int]) -> None:
        for row in range(self.count()):
            item = self.item(row)
            key = item.data(KEY_ROLE)
            if key in counts:
                item.setData(COUNT_ROLE, counts[key])

    def _on_current_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is not None and current.data(KIND_ROLE) == ENTRY:
            self.page_selected.emit(current.data(KEY_ROLE))


class _SidebarDelegate(QStyledItemDelegate):
    HEADER_HEIGHT = 34
    ENTRY_HEIGHT = 28
    INDENT = 18

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._header_font = theme.ui_font(8, QFont.Weight.DemiBold)
        self._header_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        self._entry_font = theme.ui_font(10)
        self._selected_font = theme.ui_font(10, QFont.Weight.DemiBold)
        self._count_font = theme.mono_font(8.5)

    def sizeHint(self, option: QStyleOptionViewItem, index: AnyIndex) -> QSize:
        height = self.HEADER_HEIGHT if index.data(KIND_ROLE) == HEADER else self.ENTRY_HEIGHT
        return QSize(option.rect.width(), height)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: AnyIndex) -> None:
        painter.save()
        if index.data(KIND_ROLE) == HEADER:
            self._paint_header(painter, option.rect, str(index.data()))
        else:
            self._paint_entry(painter, option, index)
        painter.restore()

    def _paint_header(self, painter: QPainter, rect: QRect, text: str) -> None:
        painter.setFont(self._header_font)
        painter.setPen(theme.TEXT_FAINT)
        area = rect.adjusted(self.INDENT, 10, -8, 0)
        painter.drawText(area, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)

    def _paint_entry(self, painter: QPainter, option: QStyleOptionViewItem, index: AnyIndex) -> None:
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            painter.fillRect(rect, theme.SIDEBAR_SELECTED)
            painter.fillRect(QRect(rect.left(), rect.top(), 2, rect.height()), theme.ACCENT)
        elif hovered:
            painter.fillRect(rect, theme.SIDEBAR_HOVER)

        painter.setFont(self._selected_font if selected else self._entry_font)
        painter.setPen(theme.SELECTED_TEXT if selected else theme.TEXT)
        text_rect = rect.adjusted(self.INDENT, 0, -52, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(index.data()))

        count = index.data(COUNT_ROLE)
        if count is not None:
            painter.setFont(self._count_font)
            painter.setPen(theme.TEXT_MUTED)
            painter.drawText(
                rect.adjusted(0, 0, -14, 0),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{count:,}",
            )
