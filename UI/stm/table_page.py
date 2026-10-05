"""One page per table: header, filter bar and a sortable, filterable grid with New and Delete."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QVBoxLayout

from stm import db, export
from stm.db import Database, DbError
from stm.dialogs import ConfirmDeleteDialog, show_error
from stm.grid import DataGrid
from stm.page import Page, mono_span, page_header
from stm.record_dialog import RecordDialog
from stm.schema import Row, TableSpec
from stm.widgets import button, label


class TablePage(Page):
    shows_counts = True

    def __init__(self, database: Database, spec: TableSpec) -> None:
        super().__init__()
        self._db = database
        self.spec = spec
        self.title = spec.title

        self.grid = DataGrid(spec.grid, spec.key_of)
        self._filter_column = QComboBox()
        self._filter = QLineEdit()
        self._summary = label("", "muted")
        self._refresh_button = button("Refresh", tooltip="Reload from the database (F5)")
        self._export_button = button("Export CSV", tooltip="Save the rows shown as a CSV file (Ctrl+E)")
        self._new_button = button("New", "primary", tooltip=f"Insert a new {spec.singular} (Ctrl+N)")
        self._new_button.setVisible(spec.can_insert)
        self._delete_button = button("Delete", "danger", tooltip="Delete the selected rows (Del)")
        self._delete_button.setVisible(not spec.is_view)
        self._delete_button.setEnabled(False)

        self._build_layout()
        self._wire()

    # ---- construction -----------------------------------------------------

    def _build_layout(self) -> None:
        kind = "View" if self.spec.is_view else "Table"
        subtitle = (
            f"{kind} {mono_span(self.spec.name)}&nbsp;&nbsp;·&nbsp;&nbsp;"
            f"key ({', '.join(self.spec.primary_key)})"
        )
        actions = QHBoxLayout()
        actions.setSpacing(8)
        for widget in (self._refresh_button, self._export_button, self._delete_button, self._new_button):
            actions.addWidget(widget)

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
        filters.addWidget(self._summary)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(page_header(self.spec.title, subtitle, actions, filters))
        layout.addWidget(self.grid, 1)

    def _wire(self) -> None:
        self._refresh_button.clicked.connect(lambda: self.reload())
        self._export_button.clicked.connect(self.export_csv)
        self._new_button.clicked.connect(self.new_record)
        self._delete_button.clicked.connect(self.delete_selected)
        self.grid.selectionModel().selectionChanged.connect(self._update_actions)
        self.grid.counts_changed.connect(self._on_counts)
        self._filter.textChanged.connect(self._apply_filter)
        self._filter_column.currentIndexChanged.connect(self._apply_filter)
        clear = QAction(self._filter)
        clear.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        clear.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        clear.triggered.connect(self._filter.clear)
        self._filter.addAction(clear)

    # ---- Page hooks -------------------------------------------------------

    def activate(self) -> None:
        self.reload()

    def refresh(self) -> bool:
        return self.reload()

    def focus_filter(self) -> None:
        self._filter.setFocus()
        self._filter.selectAll()

    def focus_main(self) -> None:
        self.grid.setFocus()

    def export_csv(self) -> None:
        path = export.ask_path(self.window(), self.spec.name)
        if path is not None:
            self.export_to(path)

    def export_to(self, path: Path) -> int:
        try:
            count = export.write_csv(path, self.spec.grid, self.grid.visible_rows())
        except OSError as err:
            self.message.emit(f"Could not write {path}: {err.strerror}")
            return 0
        self.message.emit(f"Exported {count:,} rows of {self.spec.name} to {path}.")
        return count

    # ---- data -------------------------------------------------------------

    def reload(self, select_keys: list[tuple[Any, ...]] | None = None) -> bool:
        try:
            rows = db.list_rows(self._db, self.spec.name)
        except DbError as err:
            self.message.emit(f"Could not load {self.spec.title.lower()}: {err.message}")
            return False
        self.grid.set_rows(rows, select_keys)
        self._update_actions()
        return True

    def total_count(self) -> int:
        return self.grid.total_count()

    def visible_count(self) -> int:
        return self.grid.visible_count()

    def selected_rows(self) -> list[Row]:
        return self.grid.selected_rows()

    def selected_keys(self) -> list[tuple[Any, ...]]:
        return self.grid.selected_keys()

    @property
    def view(self) -> DataGrid:
        return self.grid

    # ---- insert -----------------------------------------------------------

    def new_record(self) -> None:
        if not self.spec.can_insert:
            return
        dialog = RecordDialog(self._db, self.spec, self.window())
        if dialog.exec() != RecordDialog.DialogCode.Accepted or dialog.inserted_key is None:
            return
        key = dialog.inserted_key
        self.reload(select_keys=[key])
        if not self.selected_keys():
            self._filter.clear()
            self.grid.select_keys([key])
        row = self.grid.row_for_key(key)
        described = self.spec.describe(row) if row else self.spec.singular
        self.message.emit(f"Inserted {described}.")
        self.data_changed.emit()

    # ---- delete -----------------------------------------------------------

    def delete_selected(self) -> None:
        rows = self.selected_rows()
        if self.spec.is_view or not rows:
            return
        keys = [self.spec.key_of(row) for row in rows]
        names = [self.spec.describe(row) for row in rows]
        try:
            cascades = db.cascade_counts(self._db, self.spec, keys)
        except DbError:
            cascades = []
        confirm = ConfirmDeleteDialog(self.spec, names, cascades, self.window())
        if confirm.exec() != ConfirmDeleteDialog.DialogCode.Accepted:
            return
        anchor = self.grid.first_selected_row()
        try:
            deleted = db.delete_rows(self._db, self.spec, keys)
        except DbError as err:
            self._report_delete_failure(err, names)
            return
        self.reload(select_keys=[])
        self.grid.select_row(anchor)
        if deleted == 0:
            self.message.emit("Nothing was deleted; the rows may already have been removed.")
        elif len(names) == 1:
            self.message.emit(f"Deleted {names[0]}.")
        else:
            self.message.emit(f"Deleted {deleted:,} rows from {self.spec.name}.")
        self.data_changed.emit()

    def _report_delete_failure(self, err: DbError, names: list[str]) -> None:
        name = names[err.row_index] if err.row_index is not None else names[0]
        detail = err.detail
        if len(names) > 1:
            detail += "\nThe transaction was rolled back; no rows were deleted."
        show_error(self.window(), "Could not delete", f"Could not delete {name}. {err.message}", detail)
        self.message.emit(f"Delete refused for {name}. {err.message}")

    # ---- helpers ----------------------------------------------------------

    def _apply_filter(self) -> None:
        self.grid.set_filter(self._filter.text(), int(self._filter_column.currentData()))

    def _update_actions(self) -> None:
        self._delete_button.setEnabled(bool(self.grid.selectionModel().selectedRows()))

    def _on_counts(self, visible: int, total: int) -> None:
        totals = self.grid.column_totals()
        if totals:
            parts = [f"{spec.label} total  <b>{value:,}</b>" for spec, value in totals]
            self._summary.setText("&nbsp;&nbsp;·&nbsp;&nbsp;".join(parts))
        self.counts_changed.emit(visible, total)
