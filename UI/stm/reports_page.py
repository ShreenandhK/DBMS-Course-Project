"""Reports page: one tab per report, each a read-only grid with a summary line and CSV export."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QStackedWidget, QTabBar, QVBoxLayout

from stm import db, export
from stm.db import Database, DbError
from stm.grid import DataGrid
from stm.page import Page, page_header
from stm.reports import REPORTS, ReportSpec
from stm.widgets import button, label


class ReportsPage(Page):
    shows_counts = True

    def __init__(self, database: Database) -> None:
        super().__init__()
        self._db = database
        self.title = "Reports"
        self._tabs = QTabBar()
        self._tabs.setObjectName("ReportTabs")
        self._tabs.setDrawBase(False)
        self._tabs.setExpanding(False)
        self._stack = QStackedWidget()
        self._grids: list[DataGrid] = []
        self._description = label("", "muted")
        self._description.setWordWrap(True)
        self._summary = label("", "muted")
        self._summary.setTextFormat(Qt.TextFormat.RichText)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter rows   (Ctrl+F)")
        self._filter.setClearButtonEnabled(True)
        self._filter.setFixedWidth(260)
        self._refresh_button = button("Refresh", tooltip="Run the report again (F5)")
        self._export_button = button("Export CSV", "primary", tooltip="Save the rows shown as a CSV file (Ctrl+E)")

        for report in REPORTS:
            self._tabs.addTab(report.title)
            grid = DataGrid(report.columns, report.key_of, refit=True)
            grid.counts_changed.connect(lambda visible, total, g=grid: self._on_counts(g, visible, total))
            self._grids.append(grid)
            self._stack.addWidget(grid)

        self._build_layout()
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._filter.textChanged.connect(lambda text: self._grid().set_filter(text))
        self._refresh_button.clicked.connect(self.refresh)
        self._export_button.clicked.connect(self.export_csv)
        self._show_description()

    def _build_layout(self) -> None:
        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self._refresh_button)
        actions.addWidget(self._export_button)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        filters.addWidget(self._filter)
        filters.addStretch(1)
        filters.addWidget(self._summary)

        extra = QVBoxLayout()
        extra.setSpacing(10)
        extra.addWidget(self._tabs)
        extra.addWidget(self._description)
        extra.addLayout(filters)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(
            page_header(
                "Reports",
                "Summaries of stock, transfers, bins, ageing, damage and reorder needs. Nothing is changed here.",
                actions,
                extra,
                "Choose a tab.&nbsp;&nbsp;Ctrl+F filters the rows; Ctrl+E saves the rows shown as a CSV file.",
            )
        )
        layout.addWidget(self._stack, 1)

    # ---- Page hooks -------------------------------------------------------

    def activate(self) -> None:
        self.refresh()

    def refresh(self) -> bool:
        report = self.current_report()
        try:
            rows = db.run_report(self._db, report.key)
        except DbError as err:
            self.message.emit(f"Could not run {report.title.lower()}: {err.message}")
            return False
        self._grid().set_rows(rows)
        return True

    def focus_filter(self) -> None:
        self._filter.setFocus()
        self._filter.selectAll()

    def focus_main(self) -> None:
        self._grid().setFocus()

    def export_csv(self) -> None:
        path = export.ask_path(self.window(), self.current_report().key)
        if path is not None:
            self.export_to(path)

    # ---- helpers ----------------------------------------------------------

    def current_report(self) -> ReportSpec:
        return REPORTS[self._tabs.currentIndex()]

    def select_report(self, key: str) -> None:
        index = next(i for i, report in enumerate(REPORTS) if report.key == key)
        self._tabs.setCurrentIndex(index)

    def export_to(self, path: Path) -> int:
        report = self.current_report()
        try:
            count = export.write_csv(path, report.columns, self._grid().visible_rows())
        except OSError as err:
            self.message.emit(f"Could not write {path}: {err.strerror}")
            return 0
        self.message.emit(f"Exported {count:,} rows of {report.title.lower()} to {path}.")
        return count

    def _grid(self) -> DataGrid:
        return self._grids[self._tabs.currentIndex()]

    def _on_tab_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self._filter.blockSignals(True)
        self._filter.clear()
        self._filter.blockSignals(False)
        self._grid().set_filter("")
        self._show_description()
        self.refresh()

    def _show_description(self) -> None:
        self._description.setText(self.current_report().description)

    def _on_counts(self, grid: DataGrid, visible: int, total: int) -> None:
        if grid is not self._grid():
            return
        self._summary.setText(self.current_report().summary(grid.visible_rows()))
        self.counts_changed.emit(visible, total)
