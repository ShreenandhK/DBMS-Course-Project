"""Transfer workflows: initiate a transfer, then ship, put away, confirm or cancel it."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QHeaderView, QTableWidget, QTableWidgetItem

from stm import db, operations, theme
from stm.db import Database, DbError
from stm.dialogs import ask
from stm.grid import DataGrid
from stm.operations import ALLOWED_TRANSITIONS, RuleError
from stm.page import mono_span, steps
from stm.schema import CODE, DATE, ID, NUMBER, STATUS, GridColumn, Row
from stm.widgets import label, set_style_property
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


class NewTransferPage(WorkflowPage):
    def __init__(self, database: Database) -> None:
        super().__init__(
            database,
            "New transfer",
            "Start moving stock to another warehouse. Until it ships, the stock stays in its bin, reserved.",
            steps("Choose From and To warehouse", "Pick stock and quantities", "Create transfer")
            + "&nbsp;&nbsp;&nbsp;·&nbsp;&nbsp;&nbsp;Then ship and confirm it in Process transfers"
            + f"&nbsp;&nbsp;&nbsp;·&nbsp;&nbsp;&nbsp;Writes {mono_span('transfer')} + {mono_span('transfer_line')}",
        )
        self._source = option_combo("Select source…")
        self._dest = option_combo("Select destination…")
        self._date = date_edit()
        self._form = FormGrid()
        self._form.add("source_warehouse_id", "From warehouse", self._source)
        self._form.add("dest_warehouse_id", "To warehouse", self._dest)
        self._form.add("transfer_date", "Date", self._date)
        self.add_section("Transfer").addLayout(self._form)

        self._lines = LineEditor(PICK)
        self.add_section("Lines (picked from the source warehouse)").addWidget(self._lines)

        self.add_action("Clear", self._reset)
        self.add_action("Create transfer", self._submit, "primary")
        self.finish_layout()

        self._source.currentIndexChanged.connect(self._on_source_changed)
        self._dest.currentIndexChanged.connect(lambda *_: self._form.set_error("dest_warehouse_id", None))

    def activate(self) -> None:
        warehouses = self.options("warehouse")
        fill_combo(self._source, warehouses)
        fill_combo(self._dest, warehouses)
        self._load_stock()

    def _on_source_changed(self) -> None:
        self._form.set_error("source_warehouse_id", None)
        self._lines.clear()
        self._load_stock()

    def _load_stock(self) -> None:
        source = selected_id(self._source)
        try:
            self._lines.set_stock(db.stock_in_warehouse(self.db, source) if source else [])
        except DbError as err:
            self.show_error(err)

    def _submit(self) -> None:
        self.banner.clear()
        self._form.clear_errors()
        source, dest = selected_id(self._source), selected_id(self._dest)
        if source is None or dest is None:
            if source is None:
                self._form.set_error("source_warehouse_id", "Select the source warehouse.")
            if dest is None:
                self._form.set_error("dest_warehouse_id", "Select the destination warehouse.")
            return
        lines = self._lines.lines()
        try:
            transfer_id = operations.create_transfer(self.db, source, dest, date_value(self._date), lines)
        except RuleError as err:
            if err.line is not None:
                self._lines.show_line_error(err.line, err.message)
            elif not self._form.set_error(err.field, err.message):
                self.show_error(err)
            return
        except DbError as err:
            if not self._form.set_error(err.field, err.message):
                self.show_error(err)
            return
        units = sum(line.quantity for line in lines)
        self.message.emit(
            f"Created transfer #{transfer_id} (PENDING): {units:,} units, "
            f"{self._source.currentText()} → {self._dest.currentText()}. Ship and confirm it in Process transfers."
        )
        self._lines.clear()
        self._load_stock()
        self.data_changed.emit()

    def _reset(self) -> None:
        self.banner.clear()
        self._form.clear_errors()
        self._lines.clear()


_OPEN_COLUMNS = (
    GridColumn("transfer_id", "Transfer", ID),
    GridColumn("status", "Status", STATUS),
    GridColumn("transfer_date", "Date", DATE),
    GridColumn("source_warehouse", "From"),
    GridColumn("dest_warehouse", "To"),
    GridColumn("line_count", "Lines", NUMBER),
    GridColumn("units", "Units", NUMBER),
    GridColumn("unassigned", "Lines without dest bin", NUMBER),
)

_LINE_HEADERS = ("Source bin", "SKU", "Product", "Quantity", "Destination bin")
_DEST_COLUMN = 4


class ProcessTransfersPage(WorkflowPage):
    def __init__(self, database: Database) -> None:
        super().__init__(
            database,
            "Process transfers",
            "Ship, put away and confirm transfers that are still open.",
            steps(
                "Select a transfer",
                "Mark in transit when it leaves",
                "Choose a destination bin for each line",
                "Confirm receipt when it arrives",
            )
            + f"&nbsp;&nbsp;&nbsp;·&nbsp;&nbsp;&nbsp;Updates {mono_span('transfer.status')}, "
            f"{mono_span('transfer_line.dest_bin_id')}",
        )
        self._lines_data: list[Row] = []
        self._dest_options: list[Any] = []

        self._open = DataGrid(
            _OPEN_COLUMNS,
            lambda row: (row["transfer_id"],),
            refit=True,
            empty_text="No open transfers. Start one in New transfer.",
        )
        self._open.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._open.setMinimumHeight(140)
        self._open.setMaximumHeight(200)
        open_section = self.add_section("Open transfers (PENDING and IN_TRANSIT)")
        open_section.addWidget(self._open)

        self._title = label("Select a transfer above.", "fieldLabel")
        self._table = self._build_line_table()
        detail = self.add_section("Lines and put-away")
        detail.addWidget(self._title)
        detail.addWidget(self._table)

        self._cancel = self.add_action("Cancel transfer", self._cancel_transfer, "danger", left=True)
        self._save = self.add_action("Save put-away bins", self._save_putaway)
        self._ship = self.add_action("Mark in transit", self._ship_transfer)
        self._confirm = self.add_action("Confirm receipt", self._confirm_transfer, "primary")
        self.finish_layout()

        self._open.selectionModel().selectionChanged.connect(lambda *_: self._load_lines())
        self._update_actions()

    def _build_line_table(self) -> QTableWidget:
        table = QTableWidget(0, len(_LINE_HEADERS))
        table.setHorizontalHeaderLabels(list(_LINE_HEADERS))
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(36)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setMinimumHeight(150)
        header = table.horizontalHeader()
        header.setHighlightSections(False)
        for column, width in enumerate((110, 120, 220, 90)):
            header.resizeSection(column, width)
        header.setSectionResizeMode(_DEST_COLUMN, QHeaderView.ResizeMode.Stretch)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        table.horizontalHeaderItem(3).setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return table

    # ---- loading ------------------------------------------------------------

    def activate(self) -> None:
        self._reload(keep=self._current_id())

    def _reload(self, keep: int | None) -> None:
        try:
            rows = db.open_transfers(self.db)
        except DbError as err:
            self.show_error(err)
            return
        self._open.set_rows(rows, [(keep,)] if keep else [])
        if not self._open.selected_rows() and rows:
            self._open.select_row(0)
        self._load_lines()

    def _current(self) -> Row | None:
        rows = self._open.selected_rows()
        return rows[0] if rows else None

    def _current_id(self) -> int | None:
        current = self._current()
        return int(current["transfer_id"]) if current else None

    def _load_lines(self) -> None:
        self.banner.clear()
        transfer = self._current()
        self._table.setRowCount(0)
        self._lines_data = []
        if transfer is None:
            self._title.setText("Select a transfer above.")
            self._update_actions()
            return
        self._title.setText(
            f"Transfer #{transfer['transfer_id']}  ·  {transfer['status']}  ·  "
            f"{transfer['source_warehouse']} → {transfer['dest_warehouse']}"
        )
        try:
            self._lines_data = db.transfer_lines(self.db, transfer["transfer_id"])
            options = [o for o in self.options("bin") if o.data["warehouse_id"] == transfer["dest_warehouse_id"]]
        except DbError as err:
            self.show_error(err)
            return
        self._dest_options = options
        self._table.setRowCount(len(self._lines_data))
        for row, line in enumerate(self._lines_data):
            self._fill_line_row(row, line)
        self._update_actions()

    def _fill_line_row(self, row: int, line: Row) -> None:
        mono = theme.mono_font()
        cells = (line["source_bin_code"], line["sku"], line["product_name"], f"{line['quantity']:,}")
        for column, text in enumerate(cells):
            item = QTableWidgetItem(text)
            if column in (0, 1):
                item.setFont(mono)
            if column == 3:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, column, item)
        combo = QComboBox()
        combo.addItem("— Not assigned —", None)
        for option in self._dest_options:
            if option.id != line["source_bin_id"]:
                combo.addItem(option.label, option.id)
        combo.setCurrentIndex(max(0, combo.findData(line["dest_bin_id"])))
        combo.currentIndexChanged.connect(lambda *_, c=combo: set_style_property(c, "invalid", False))
        self._table.setCellWidget(row, _DEST_COLUMN, combo)

    def _putaway(self) -> operations.PutAway:
        putaway: operations.PutAway = {}
        for row, line in enumerate(self._lines_data):
            combo = self._table.cellWidget(row, _DEST_COLUMN)
            putaway[(line["source_bin_id"], line["product_id"])] = combo.currentData() if combo else None
        return putaway

    def _update_actions(self) -> None:
        transfer = self._current()
        allowed = ALLOWED_TRANSITIONS.get(transfer["status"], ()) if transfer else ()
        self._ship.setEnabled("IN_TRANSIT" in allowed)
        self._confirm.setEnabled("CONFIRMED" in allowed)
        self._cancel.setEnabled("CANCELLED" in allowed)
        self._save.setEnabled(transfer is not None and bool(self._lines_data))

    # ---- actions ------------------------------------------------------------

    def _run(self, action: Any, success: str, keep: bool = True) -> None:
        transfer_id = self._current_id()
        if transfer_id is None:
            return
        self.banner.clear()
        try:
            action(transfer_id)
        except RuleError as err:
            self._highlight_line(err)
            self.show_error(err)
            return
        except DbError as err:
            self.show_error(err)
            return
        self.message.emit(success.format(id=transfer_id))
        self._reload(keep=transfer_id if keep else None)
        self.data_changed.emit()

    def _highlight_line(self, err: RuleError) -> None:
        if err.field != "dest_bin_id":
            return
        rows = [err.line] if err.line is not None else range(self._table.rowCount())
        for row in rows:
            combo = self._table.cellWidget(row, _DEST_COLUMN)
            if combo is not None and (err.line is not None or combo.currentData() is None):
                set_style_property(combo, "invalid", True)

    def _save_putaway(self) -> None:
        putaway = self._putaway()
        self._run(lambda tid: operations.save_putaway(self.db, tid, putaway), "Saved destination bins for transfer #{id}.")

    def _ship_transfer(self) -> None:
        self._run(
            lambda tid: operations.ship_transfer(self.db, tid),
            "Transfer #{id} is IN_TRANSIT; its stock has left the source bins.",
        )

    def _confirm_transfer(self) -> None:
        putaway = self._putaway()
        transfer = self._current()
        destination = transfer["dest_warehouse"] if transfer else ""
        self._run(
            lambda tid: operations.confirm_transfer(self.db, tid, putaway),
            "Confirmed transfer #{id}; stock is now in " + destination + ".",
            keep=False,
        )

    def _cancel_transfer(self) -> None:
        transfer = self._current()
        if transfer is None:
            return
        question = (
            f"Cancel transfer #{transfer['transfer_id']} ({transfer['source_warehouse']} → "
            f"{transfer['dest_warehouse']}, {transfer['status']})? Cancelled transfers have no stock effect, "
            "so the units count in the source bins again. This cannot be reversed."
        )
        if not ask(self.window(), "Cancel transfer?", question, "Cancel transfer"):
            return
        self._run(lambda tid: operations.cancel_transfer(self.db, tid), "Cancelled transfer #{id}.", keep=False)
