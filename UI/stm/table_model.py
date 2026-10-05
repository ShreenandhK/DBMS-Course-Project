"""Grid model, sort/filter proxy and the status chip delegate."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QRectF,
    QRegularExpression,
    QSize,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from stm import theme
from stm.schema import GridColumn, Row, Style

SORT_ROLE = Qt.ItemDataRole.UserRole + 1
EMPTY = "—"

_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
_LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
_NUMERIC = {Style.NUMBER, Style.ID, Style.PERCENT}
_MONO = {Style.CODE, Style.ID}

AnyIndex = QModelIndex | QPersistentModelIndex


def format_value(value: Any, style: Style) -> str:
    if value is None:
        return EMPTY
    if style is Style.NUMBER and isinstance(value, (int, float)):
        return f"{value:,}"
    if style is Style.PERCENT and isinstance(value, (int, float)):
        return f"{value:.1f}%"
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _sort_key(value: Any, style: Style) -> Any:
    if style in _NUMERIC:
        return value if value is not None else float("-inf")
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    return str(value).casefold()


class RecordModel(QAbstractTableModel):
    def __init__(self, columns: Sequence[GridColumn], parent: Any = None) -> None:
        super().__init__(parent)
        self._columns = tuple(columns)
        self._rows: list[Row] = []
        self._mono = theme.mono_font()
        self._strong = theme.ui_font(10, QFont.Weight.DemiBold)

    def set_rows(self, rows: list[Row]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def row_data(self, row: int) -> Row:
        return self._rows[row]

    def rows(self) -> list[Row]:
        return self._rows

    def column_spec(self, column: int) -> GridColumn:
        return self._columns[column]

    def rowCount(self, parent: AnyIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: AnyIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._columns)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation != Qt.Orientation.Horizontal:
            return None
        column = self._columns[section]
        if role == Qt.ItemDataRole.DisplayRole:
            return column.label
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return _RIGHT if column.style in _NUMERIC else _LEFT
        return None

    def data(self, index: AnyIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        column = self._columns[index.column()]
        value = self._rows[index.row()].get(column.key)
        if role == Qt.ItemDataRole.DisplayRole:
            return format_value(value, column.style)
        if role == SORT_ROLE:
            return _sort_key(value, column.style)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return _RIGHT if column.style in _NUMERIC else _LEFT
        if role == Qt.ItemDataRole.FontRole:
            if column.style in _MONO:
                return self._mono
            return self._strong if column.strong else None
        if role == Qt.ItemDataRole.ForegroundRole:
            if value is None:
                return theme.TEXT_FAINT
            if isinstance(value, (int, float)) and value < 0:
                return theme.NEGATIVE
        return None


class RecordFilterProxy(QSortFilterProxyModel):
    """Case-insensitive substring filter over one column or all of them."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setSortRole(SORT_ROLE)
        self.setFilterKeyColumn(-1)
        self.setDynamicSortFilter(True)

    def set_filter(self, text: str, column: int = -1) -> None:
        self.setFilterKeyColumn(column)
        pattern = QRegularExpression.escape(text.strip())
        self.setFilterRegularExpression(
            QRegularExpression(pattern, QRegularExpression.PatternOption.CaseInsensitiveOption)
        )


class StatusChipDelegate(QStyledItemDelegate):
    """Paints a transfer status as a small flat chip."""

    PADDING_X = 7
    INSET_X = 8

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._font = theme.ui_font(8, QFont.Weight.DemiBold)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: AnyIndex) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        if not text or text == EMPTY:
            return
        background, foreground = theme.STATUS_COLORS.get(text, theme.STATUS_COLORS["PENDING"])
        metrics = QFontMetrics(self._font)
        width = metrics.horizontalAdvance(text) + 2 * self.PADDING_X
        height = metrics.height() + 4
        rect = QRectF(
            option.rect.left() + self.INSET_X,
            option.rect.top() + (option.rect.height() - height) / 2,
            width,
            height,
        )
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 3, 3)
        painter.setFont(self._font)
        painter.setPen(foreground)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: AnyIndex) -> QSize:
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        width = QFontMetrics(self._font).horizontalAdvance(text) + 2 * (self.PADDING_X + self.INSET_X)
        return QSize(width, super().sizeHint(option, index).height())
