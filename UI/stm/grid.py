"""Read-only data grid: a sortable, filterable table view over a list of row dicts."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import QItemSelection, QItemSelectionModel, Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView, QWidget

from stm import theme
from stm.schema import GridColumn, Row, Style
from stm.table_model import RecordFilterProxy, RecordModel, StatusChipDelegate

MIN_COLUMN_WIDTH = 56
MAX_COLUMN_WIDTH = 380
HEADER_PADDING = 18
COLUMN_SLACK = 4
ROW_HEIGHT = 28

KeyFunction = Callable[[Row], tuple[Any, ...]]


class DataGrid(QTableView):
    counts_changed = Signal(int, int)  # visible rows, total rows

    def __init__(
        self, columns: Sequence[GridColumn], key_of: KeyFunction, parent: QWidget | None = None, refit: bool = False
    ) -> None:
        """``refit`` re-sizes columns on every load (small working grids); otherwise only on the first."""
        super().__init__(parent)
        self.columns = tuple(columns)
        self._key_of = key_of
        self._refit = refit
        self._fitted = False
        self._model = RecordModel(self.columns, self)
        self._proxy = RecordFilterProxy(self)
        self._proxy.setSourceModel(self._model)
        self.setModel(self._proxy)
        self._configure()
        for signal in (self._proxy.modelReset, self._proxy.rowsInserted, self._proxy.rowsRemoved, self._proxy.layoutChanged):
            signal.connect(self._emit_counts)

    def _configure(self) -> None:
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header = self.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(False)
        header.setSortIndicatorClearable(True)
        header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.setSortingEnabled(True)
        for column, spec in enumerate(self.columns):
            if spec.style is Style.STATUS:
                self.setItemDelegateForColumn(column, StatusChipDelegate(self))

    # ---- data -------------------------------------------------------------

    def set_rows(self, rows: list[Row], select_keys: list[tuple[Any, ...]] | None = None) -> None:
        keys = self.selected_keys() if select_keys is None else select_keys
        self._model.set_rows(rows)
        if self._refit or not self._fitted:
            self.fit_columns()
        self.select_keys(keys)
        self._emit_counts()

    def rows(self) -> list[Row]:
        return self._model.rows()

    def row_for_key(self, key: tuple[Any, ...]) -> Row | None:
        return next((row for row in self._model.rows() if self._key_of(row) == key), None)

    def visible_count(self) -> int:
        return self._proxy.rowCount()

    def total_count(self) -> int:
        return self._model.rowCount()

    def visible_rows(self) -> list[Row]:
        return [
            self._model.row_data(self._proxy.mapToSource(self._proxy.index(row, 0)).row())
            for row in range(self._proxy.rowCount())
        ]

    def column_totals(self) -> list[tuple[GridColumn, int]]:
        visible = self.visible_rows()
        return [(spec, sum(row.get(spec.key) or 0 for row in visible)) for spec in self.columns if spec.summed]

    def set_filter(self, text: str, column: int = -1) -> None:
        self._proxy.set_filter(text, column)

    # ---- selection --------------------------------------------------------

    def selected_rows(self) -> list[Row]:
        indexes = self.selectionModel().selectedRows()
        source_rows = sorted(self._proxy.mapToSource(index).row() for index in indexes)
        return [self._model.row_data(row) for row in source_rows]

    def selected_keys(self) -> list[tuple[Any, ...]]:
        return [self._key_of(row) for row in self.selected_rows()]

    def select_keys(self, keys: list[tuple[Any, ...]]) -> None:
        wanted = set(keys)
        selection = QItemSelection()
        first = None
        for row, record in enumerate(self._model.rows()):
            if self._key_of(record) not in wanted:
                continue
            index = self._proxy.mapFromSource(self._model.index(row, 0))
            if not index.isValid():
                continue
            selection.select(index, index)
            if first is None:
                first = index
        flags = QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows
        self.selectionModel().select(selection, flags)
        if first is not None:
            self.selectionModel().setCurrentIndex(first, QItemSelectionModel.SelectionFlag.NoUpdate)
            self.scrollTo(first, QAbstractItemView.ScrollHint.PositionAtCenter)

    def first_selected_row(self) -> int:
        return min((index.row() for index in self.selectionModel().selectedRows()), default=0)

    def select_row(self, row: int) -> None:
        count = self._proxy.rowCount()
        if count == 0:
            return
        index = self._proxy.index(min(row, count - 1), 0)
        flags = QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows
        self.selectionModel().setCurrentIndex(index, flags)

    # ---- layout -----------------------------------------------------------

    def fit_columns(self) -> None:
        # Sized by hand: resizeColumnsToContents() reserves room for a sort arrow the stylesheet hides.
        header = self.horizontalHeader()
        header_metrics = QFontMetrics(theme.ui_font(9, QFont.Weight.DemiBold))
        for column, spec in enumerate(self.columns):
            content = self.sizeHintForColumn(column)
            title = header_metrics.horizontalAdvance(spec.label) + HEADER_PADDING
            width = max(content, title) + COLUMN_SLACK
            header.resizeSection(column, max(MIN_COLUMN_WIDTH, min(MAX_COLUMN_WIDTH, width)))
        self._fitted = self._model.rowCount() > 0

    def _emit_counts(self) -> None:
        self.counts_changed.emit(self.visible_count(), self.total_count())
