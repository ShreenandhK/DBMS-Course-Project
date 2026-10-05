"""One page per table: header, filter bar and a sortable, filterable grid."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QItemSelection, QItemSelectionModel, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from stm import db
from stm.db import Database, DbError
from stm.schema import Row, Style, TableSpec
from stm.table_model import RecordFilterProxy, RecordModel, StatusChipDelegate
from stm.widgets import button, label

MIN_COLUMN_WIDTH = 72
MAX_COLUMN_WIDTH = 380
ROW_HEIGHT = 28


class TablePage(QWidget):
    counts_changed = Signal(int, int)  # visible rows, total rows
    message = Signal(str)

    def __init__(self, database: Database, spec: TableSpec, parent: Any = None) -> None:
        super().__init__(parent)
        self._db = database
        self.spec = spec
        self._columns_fitted = False

        self._model = RecordModel(spec.grid, self)
        self._proxy = RecordFilterProxy(self)
        self._proxy.setSourceModel(self._model)
        self._view = self._build_view()
        self._filter_column = QComboBox()
        self._filter = QLineEdit()
        self._refresh_button = button("Refresh", tooltip="Reload from the database (F5)")
        self._action_bar = QHBoxLayout()

        self._build_layout()
        self._wire()

    # ---- construction -----------------------------------------------------

    def _build_view(self) -> QTableView:
        view = QTableView()
        view.setModel(self._proxy)
        view.setAlternatingRowColors(True)
        view.setShowGrid(False)
        view.setWordWrap(False)
        view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        view.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        view.verticalHeader().hide()
        view.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        view.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header = view.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(False)
        header.setSortIndicatorClearable(True)
        header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        view.setSortingEnabled(True)
        for column, spec in enumerate(self.spec.grid):
            if spec.style is Style.STATUS:
                view.setItemDelegateForColumn(column, StatusChipDelegate(view))
        return view

    def _build_layout(self) -> None:
        kind = "View" if self.spec.is_view else "Table"
        key = ", ".join(self.spec.primary_key)
        subtitle = label(
            f"{kind} <span style=\"font-family:'Cascadia Mono','Consolas'\">{self.spec.name}</span>"
            f"&nbsp;&nbsp;·&nbsp;&nbsp;key ({key})",
            "muted",
        )
        subtitle.setTextFormat(Qt.TextFormat.RichText)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label(self.spec.title, "pageTitle"))
        titles.addWidget(subtitle)

        self._action_bar.setSpacing(8)
        self._action_bar.addWidget(self._refresh_button)

        top = QHBoxLayout()
        top.addLayout(titles)
        top.addStretch(1)
        top.addLayout(self._action_bar)

        self._filter_column.addItem("All columns", -1)
        for column, spec in enumerate(self.spec.grid):
            self._filter_column.addItem(spec.label, column)
        self._filter_column.setFixedWidth(170)
        self._filter.setPlaceholderText("Filter rows   (Ctrl+F)")
        self._filter.setClearButtonEnabled(True)
        self._filter.setFixedWidth(300)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        filters.addWidget(self._filter_column)
        filters.addWidget(self._filter)
        filters.addStretch(1)

        header = QWidget()
        header.setObjectName("PageHeader")
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 14, 20, 12)
        header_layout.setSpacing(12)
        header_layout.addLayout(top)
        header_layout.addLayout(filters)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self._view, 1)

    def _wire(self) -> None:
        self._refresh_button.clicked.connect(lambda: self.reload())
        self._filter.textChanged.connect(self._apply_filter)
        self._filter_column.currentIndexChanged.connect(self._apply_filter)
        clear = QAction(self._filter)
        clear.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        clear.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        clear.triggered.connect(self._filter.clear)
        self._filter.addAction(clear)
        for signal in (self._proxy.modelReset, self._proxy.rowsInserted, self._proxy.rowsRemoved, self._proxy.layoutChanged):
            signal.connect(self._emit_counts)

    def add_action_button(self, widget: QWidget) -> None:
        self._action_bar.addWidget(widget)

    # ---- behaviour --------------------------------------------------------

    def reload(self, select_keys: list[tuple[Any, ...]] | None = None) -> bool:
        keys = select_keys if select_keys is not None else self.selected_keys()
        try:
            rows = db.list_rows(self._db, self.spec.name)
        except DbError as err:
            self.message.emit(f"Could not load {self.spec.title.lower()}: {err.message}")
            return False
        self._model.set_rows(rows)
        if not self._columns_fitted:
            self._fit_columns()
        self._select_keys(keys)
        self._emit_counts()
        return True

    def focus_filter(self) -> None:
        self._filter.setFocus()
        self._filter.selectAll()

    def focus_grid(self) -> None:
        self._view.setFocus()

    def selected_rows(self) -> list[Row]:
        rows = self._view.selectionModel().selectedRows()
        source_rows = sorted(self._proxy.mapToSource(index).row() for index in rows)
        return [self._model.row_data(row) for row in source_rows]

    def selected_keys(self) -> list[tuple[Any, ...]]:
        return [self.spec.key_of(row) for row in self.selected_rows()]

    def visible_count(self) -> int:
        return self._proxy.rowCount()

    def total_count(self) -> int:
        return self._model.rowCount()

    @property
    def view(self) -> QTableView:
        return self._view

    def _apply_filter(self) -> None:
        self._proxy.set_filter(self._filter.text(), int(self._filter_column.currentData()))

    def _fit_columns(self) -> None:
        self._view.resizeColumnsToContents()
        header = self._view.horizontalHeader()
        for column in range(self._model.columnCount()):
            width = header.sectionSize(column) + 16
            header.resizeSection(column, max(MIN_COLUMN_WIDTH, min(MAX_COLUMN_WIDTH, width)))
        self._columns_fitted = self._model.rowCount() > 0

    def _select_keys(self, keys: list[tuple[Any, ...]]) -> None:
        wanted = set(keys)
        selection = QItemSelection()
        first_visible = None
        for row, record in enumerate(self._model.rows()):
            if self.spec.key_of(record) not in wanted:
                continue
            proxy_index = self._proxy.mapFromSource(self._model.index(row, 0))
            if not proxy_index.isValid():
                continue
            selection.select(proxy_index, proxy_index)
            if first_visible is None:
                first_visible = proxy_index
        flags = QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows
        self._view.selectionModel().select(selection, flags)
        if first_visible is not None:
            self._view.selectionModel().setCurrentIndex(first_visible, QItemSelectionModel.SelectionFlag.NoUpdate)
            self._view.scrollTo(first_visible, QAbstractItemView.ScrollHint.PositionAtCenter)

    def _emit_counts(self) -> None:
        self.counts_changed.emit(self.visible_count(), self.total_count())
