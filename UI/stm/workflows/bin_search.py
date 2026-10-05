"""Bin search: find bins and their contents by bin code, zone, SKU or product name."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QVBoxLayout

from stm import db
from stm.db import Database, DbError
from stm.grid import DataGrid
from stm.page import Page, mono_span, page_header
from stm.schema import CODE, NUMBER, GridColumn
from stm.widgets import label

_COLUMNS = (
    GridColumn("warehouse_name", "Warehouse"),
    GridColumn("zone_name", "Zone"),
    GridColumn("bin_code", "Bin", CODE),
    GridColumn("sku", "SKU", CODE),
    GridColumn("product_name", "Product"),
    GridColumn("on_hand", "On hand", NUMBER, strong=True, summed=True),
    GridColumn("reserved", "Reserved", NUMBER),
    GridColumn("available", "Available", NUMBER),
)


class BinSearchPage(Page):
    shows_counts = True

    def __init__(self, database: Database) -> None:
        super().__init__()
        self._db = database
        self.title = "Bin search"
        self._warehouse = QComboBox()
        self._warehouse.setFixedWidth(220)
        self._text = QLineEdit()
        self._text.setPlaceholderText("Bin code, zone, SKU or product   (Ctrl+F)")
        self._text.setClearButtonEnabled(True)
        self._text.setFixedWidth(320)
        self._include_empty = QCheckBox("Include empty bins")
        self._summary = label("", "muted")
        self.grid = DataGrid(
            _COLUMNS,
            lambda row: (row["bin_id"], row["product_id"]),
            refit=True,
            empty_text="No bins match. Try part of a bin code (HYD-BS), a SKU or a product name, "
            "or tick Include empty bins.",
        )
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        filters.addWidget(self._warehouse)
        filters.addWidget(self._text)
        filters.addWidget(self._include_empty)
        filters.addStretch(1)
        filters.addWidget(self._summary)
        detail = (
            "Reserved = promised to pending transfers.&nbsp;&nbsp;Available = on hand − reserved."
            f"&nbsp;&nbsp;&nbsp;·&nbsp;&nbsp;&nbsp;Reads {mono_span('bin')} joined to {mono_span('v_bin_stock')}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(
            page_header(
                "Bin search",
                "Find bins and what they hold by bin code, zone, SKU or product name.",
                None,
                filters,
                detail,
            )
        )
        layout.addWidget(self.grid, 1)

        self._debounce.timeout.connect(self.search)
        self._text.textChanged.connect(lambda *_: self._debounce.start())
        self._warehouse.currentIndexChanged.connect(lambda *_: self.search())
        self._include_empty.toggled.connect(lambda *_: self.search())
        self.grid.counts_changed.connect(self._on_counts)

    def activate(self) -> None:
        current = self._warehouse.currentData()
        self._warehouse.blockSignals(True)
        self._warehouse.clear()
        self._warehouse.addItem("All warehouses", None)
        try:
            for option in db.lookup(self._db, "warehouse"):
                self._warehouse.addItem(option.label, option.id)
        except DbError as err:
            self.message.emit(f"Could not load warehouses: {err.message}")
        self._warehouse.setCurrentIndex(max(0, self._warehouse.findData(current)))
        self._warehouse.blockSignals(False)
        self.search()

    def search(self) -> None:
        try:
            rows = db.search_bins(
                self._db, self._text.text(), self._warehouse.currentData(), self._include_empty.isChecked()
            )
        except DbError as err:
            self.message.emit(f"Search failed: {err.message}")
            return
        for row in rows:
            row["product_id"] = row["product_id"] or 0  # empty bins still need a unique key
        self.grid.set_rows(rows)

    def focus_filter(self) -> None:
        self._text.setFocus()
        self._text.selectAll()

    def focus_main(self) -> None:
        self._text.setFocus()

    def _on_counts(self, visible: int, total: int) -> None:
        bins = len({row["bin_id"] for row in self.grid.rows()})
        on_hand = sum(row["on_hand"] or 0 for row in self.grid.rows())
        self._summary.setText(f"{bins} bin{'s' if bins != 1 else ''}  ·  On hand total  <b>{on_hand:,}</b>")
        self.counts_changed.emit(visible, total)
