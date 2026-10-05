"""Receive stock: a receipt header and its put-away lines in one transaction."""
from __future__ import annotations

from stm import operations
from stm.db import Database, DbError
from stm.operations import RuleError
from stm.page import mono_span, steps
from stm.workflows.common import (
    PUTAWAY,
    FormGrid,
    LineEditor,
    WorkflowPage,
    date_edit,
    date_value,
    fill_combo,
    option_combo,
    selected_id,
)


class ReceivePage(WorkflowPage):
    def __init__(self, database: Database) -> None:
        super().__init__(
            database,
            "Receive stock",
            "Record goods arriving from a supplier and put them into bins.",
            steps("Choose the supplier and warehouse", "Add a line for each bin and product", "Post receipt")
            + f"&nbsp;&nbsp;&nbsp;·&nbsp;&nbsp;&nbsp;Writes {mono_span('receipt')} + {mono_span('receipt_line')}"
            " in one transaction",
        )
        self._supplier = option_combo("Select supplier…")
        self._warehouse = option_combo("Select warehouse…")
        self._date = date_edit()
        self._form = FormGrid()
        self._form.add("supplier_id", "Supplier", self._supplier)
        self._form.add("warehouse_id", "Warehouse", self._warehouse)
        self._form.add("receipt_date", "Date", self._date)
        self.add_section("Receipt").addLayout(self._form)

        self._lines = LineEditor(PUTAWAY)
        self.add_section("Put-away lines").addWidget(self._lines)

        self.add_action("Clear", self._reset)
        self._post = self.add_action("Post receipt", self._submit, "primary")
        self.finish_layout()

        self._warehouse.currentIndexChanged.connect(self._on_warehouse_changed)
        self._supplier.currentIndexChanged.connect(lambda *_: self._form.set_error("supplier_id", None))

    def activate(self) -> None:
        fill_combo(self._supplier, self.options("supplier"))
        fill_combo(self._warehouse, self.options("warehouse"))
        self._lines.set_products(self.options("product"))
        self._load_bins()

    def _on_warehouse_changed(self) -> None:
        self._form.set_error("warehouse_id", None)
        self._lines.clear()
        self._load_bins()

    def _load_bins(self) -> None:
        warehouse_id = selected_id(self._warehouse)
        bins = [o for o in self.options("bin") if o.data["warehouse_id"] == warehouse_id] if warehouse_id else []
        self._lines.set_bins(bins)

    def _submit(self) -> None:
        self.banner.clear()
        self._form.clear_errors()
        supplier_id, warehouse_id = selected_id(self._supplier), selected_id(self._warehouse)
        if supplier_id is None or warehouse_id is None:
            if supplier_id is None:
                self._form.set_error("supplier_id", "Select a supplier.")
            if warehouse_id is None:
                self._form.set_error("warehouse_id", "Select a warehouse.")
            return
        lines = self._lines.lines()
        try:
            receipt_id = operations.receive(self.db, supplier_id, warehouse_id, date_value(self._date), lines)
        except RuleError as err:
            if err.line is not None:
                self._lines.show_line_error(err.line, err.message)
            else:
                self.show_error(err)
            return
        except DbError as err:
            self.show_error(err)
            return
        units = sum(line.quantity for line in lines)
        self.message.emit(
            f"Posted receipt #{receipt_id}: {len(lines)} line{'s' if len(lines) != 1 else ''}, "
            f"{units:,} units into {self._warehouse.currentText()}."
        )
        self._lines.clear()
        self.data_changed.emit()

    def _reset(self) -> None:
        self.banner.clear()
        self._form.clear_errors()
        self._lines.clear()
