"""Dispatch stock: a dispatch header and its pick lines in one transaction."""
from __future__ import annotations

from PySide6.QtWidgets import QLineEdit

from stm import db, operations
from stm.db import Database, DbError
from stm.operations import RuleError
from stm.page import mono_span, steps
from stm.workflows.common import (
    PICK,
    FormGrid,
    LineEditor,
    WorkflowPage,
    date_edit,
    date_value,
    fill_combo,
    option_combo,
    selected_id,
)


class DispatchPage(WorkflowPage):
    def __init__(self, database: Database) -> None:
        super().__init__(
            database,
            "Dispatch stock",
            "Send stock out of a warehouse to a customer. Stock reserved for pending transfers cannot be picked.",
            steps("Choose the warehouse and destination", "Pick stock and quantities", "Post dispatch")
            + f"&nbsp;&nbsp;&nbsp;·&nbsp;&nbsp;&nbsp;Writes {mono_span('dispatch')} + {mono_span('dispatch_line')}"
            " in one transaction",
        )
        self._warehouse = option_combo("Select warehouse…")
        self._destination = QLineEdit()
        self._destination.setPlaceholderText("Customer and delivery address")
        self._destination.setMaxLength(150)
        self._date = date_edit()
        self._form = FormGrid()
        self._form.add("warehouse_id", "Warehouse", self._warehouse)
        self._form.add("dispatch_date", "Date", self._date)
        self._form.add("destination", "Destination", self._destination, span=2)
        self.add_section("Dispatch").addLayout(self._form)

        self._lines = LineEditor(PICK)
        self.add_section("Pick lines").addWidget(self._lines)

        self.add_action("Clear", self._reset)
        self.add_action("Post dispatch", self._submit, "primary")
        self.finish_layout()

        self._warehouse.currentIndexChanged.connect(self._on_warehouse_changed)
        self._destination.textChanged.connect(lambda *_: self._form.set_error("destination", None))

    def activate(self) -> None:
        fill_combo(self._warehouse, self.options("warehouse"))
        self._load_stock()

    def _on_warehouse_changed(self) -> None:
        self._form.set_error("warehouse_id", None)
        self._lines.clear()
        self._load_stock()

    def _load_stock(self) -> None:
        warehouse_id = selected_id(self._warehouse)
        try:
            self._lines.set_stock(db.stock_in_warehouse(self.db, warehouse_id) if warehouse_id else [])
        except DbError as err:
            self.show_error(err)

    def _submit(self) -> None:
        self.banner.clear()
        self._form.clear_errors()
        warehouse_id = selected_id(self._warehouse)
        if warehouse_id is None:
            self._form.set_error("warehouse_id", "Select a warehouse.")
            return
        lines = self._lines.lines()
        try:
            dispatch_id = operations.dispatch(
                self.db, warehouse_id, self._destination.text(), date_value(self._date), lines
            )
        except RuleError as err:
            if err.line is not None:
                self._lines.show_line_error(err.line, err.message)
            elif not self._form.set_error(err.field, err.message):
                self.show_error(err)
            return
        except DbError as err:
            self.show_error(err)
            return
        units = sum(line.quantity for line in lines)
        self.message.emit(
            f"Posted dispatch #{dispatch_id}: {units:,} units from {self._warehouse.currentText()} "
            f"to {self._destination.text().strip()}."
        )
        self._lines.clear()
        self._destination.clear()
        self._load_stock()
        self.data_changed.emit()

    def _reset(self) -> None:
        self.banner.clear()
        self._form.clear_errors()
        self._lines.clear()
        self._destination.clear()
