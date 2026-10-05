"""Record damage: write damaged units off a bin."""
from __future__ import annotations

from PySide6.QtWidgets import QLineEdit

from stm import db, operations, schema
from stm.db import Database, DbError
from stm.grid import DataGrid
from stm.operations import Line, RuleError
from stm.page import mono_span
from stm.record_dialog import parse_int
from stm.workflows.common import (
    FormGrid,
    WorkflowPage,
    date_edit,
    date_value,
    fill_combo,
    fill_stock_combo,
    option_combo,
    selected_id,
    stock_key,
)


class DamagePage(WorkflowPage):
    def __init__(self, database: Database) -> None:
        super().__init__(
            database,
            "Record damage",
            f"Inserts a {mono_span('damaged')} row. Damaged units leave usable stock in {mono_span('v_bin_stock')}; "
            "the quantity cannot exceed what the bin holds.",
        )
        self._warehouse = option_combo("Select warehouse…")
        self._stock = option_combo("Select bin and product…")
        self._stock.setMinimumWidth(420)
        self._quantity = QLineEdit()
        self._quantity.setPlaceholderText("Units")
        self._date = date_edit()
        self._reason = QLineEdit()
        self._reason.setMaxLength(200)
        self._reason.setPlaceholderText("e.g. Cartons crushed during unloading")
        self._form = FormGrid(columns=2)
        self._form.add("warehouse_id", "Warehouse", self._warehouse)
        self._form.add("damage_date", "Date", self._date)
        self._form.add("stock", "Bin and product", self._stock, span=2)
        self._form.add("quantity", "Quantity", self._quantity)
        self._form.add("reason", "Reason", self._reason)
        self.add_section("Damage").addLayout(self._form)

        self._recent = DataGrid(schema.DAMAGED.grid, schema.DAMAGED.key_of, refit=True)
        self._recent.setMinimumHeight(140)
        self.add_section("Damage records").addWidget(self._recent)

        self.add_action("Clear", self._reset)
        self.add_action("Record damage", self._submit, "primary")
        self.finish_layout()

        self._stock_rows: dict[tuple[int, int], dict] = {}
        self._warehouse.currentIndexChanged.connect(self._load_stock)
        self._stock.currentIndexChanged.connect(lambda *_: self._form.set_error("stock", None))
        self._quantity.textChanged.connect(lambda *_: self._form.set_error("quantity", None))
        self._reason.textChanged.connect(lambda *_: self._form.set_error("reason", None))

    def activate(self) -> None:
        fill_combo(self._warehouse, self.options("warehouse"))
        self._load_stock()
        self._load_recent()

    def _load_stock(self) -> None:
        self._form.set_error("warehouse_id", None)
        warehouse_id = selected_id(self._warehouse)
        try:
            rows = db.stock_in_warehouse(self.db, warehouse_id) if warehouse_id else []
        except DbError as err:
            self.show_error(err)
            return
        self._stock_rows = {stock_key(row): row for row in rows}
        fill_stock_combo(self._stock, rows, use_available=False)

    def _load_recent(self, select: list | None = None) -> None:
        try:
            self._recent.set_rows(db.list_rows(self.db, "damaged"), select)
        except DbError as err:
            self.show_error(err)

    def _submit(self) -> None:
        self.banner.clear()
        self._form.clear_errors()
        key = self._stock.currentData() if self._stock.currentIndex() >= 0 else None
        stock = self._stock_rows.get(key) if key else None
        quantity, quantity_error = parse_int(self._quantity.text().strip(), 1)
        errors = {
            "warehouse_id": None if selected_id(self._warehouse) else "Select a warehouse.",
            "stock": None if stock else "Select the bin and product.",
            "quantity": quantity_error or (None if quantity else "Required."),
            "reason": None if self._reason.text().strip() else "Required.",
        }
        for field, message in errors.items():
            self._form.set_error(field, message)
        if any(errors.values()) or stock is None or quantity is None:
            return
        line = Line(stock["bin_id"], stock["product_id"], quantity)
        try:
            record_key = operations.record_damage(self.db, line, date_value(self._date), self._reason.text())
        except RuleError as err:
            if not self._form.set_error(err.field, err.message):
                self.show_error(err)
            return
        except DbError as err:
            if not self._form.set_error("stock" if err.code == 1062 else err.field, err.message):
                self.show_error(err)
            return
        self.message.emit(f"Recorded damage: {quantity:,} × {stock['sku']} written off {stock['bin_code']}.")
        self._quantity.clear()
        self._reason.clear()
        self._load_stock()
        self._load_recent([record_key])
        self.data_changed.emit()

    def _reset(self) -> None:
        self.banner.clear()
        self._form.clear_errors()
        self._quantity.clear()
        self._reason.clear()
