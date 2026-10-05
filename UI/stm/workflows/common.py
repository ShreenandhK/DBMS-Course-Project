"""Building blocks shared by the workflow pages."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

from PySide6.QtCore import QDate, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from stm import db
from stm.db import Database, DbError, Option
from stm.grid import DataGrid
from stm.operations import Line, RuleError
from stm.page import Page, page_header
from stm.record_dialog import parse_int
from stm.schema import CODE, NUMBER, GridColumn, Row
from stm.widgets import Banner, button, field_error_label, label, set_style_property, show_field_error


class WorkflowPage(Page):
    """Header, a scrollable body of sections, a banner for errors and a footer with actions."""

    def __init__(self, database: Database, title: str, subtitle: str) -> None:
        super().__init__()
        self.db = database
        self.title = title
        self.banner = Banner()
        self.footer = QHBoxLayout()
        self.footer.setSpacing(8)
        self.footer.addStretch(1)
        self._left_actions = 0

        body = QWidget()
        body.setObjectName("WorkflowBody")
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(20, 16, 20, 16)
        self.body.setSpacing(14)
        scroll = QScrollArea()
        scroll.setObjectName("WorkflowScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(page_header(title, subtitle))
        layout.addWidget(scroll, 1)

    def finish_layout(self) -> None:
        """Call after adding sections: appends the banner and the footer."""
        self.body.addWidget(self.banner)
        self.body.addLayout(self.footer)
        self.body.addStretch(1)

    def add_section(self, title: str) -> QVBoxLayout:
        section = QFrame()
        section.setObjectName("Section")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(label(title.upper(), "sectionTitle"))
        self.body.addWidget(section)
        return layout

    def add_action(self, text: str, slot: Callable[[], None], variant: str = "", left: bool = False) -> Any:
        """Add a footer button; ``left`` places it before the stretch, otherwise it is right-aligned."""
        widget = button(text, variant)
        widget.clicked.connect(slot)
        if left:
            self.footer.insertWidget(self._left_actions, widget)
            self._left_actions += 1
        else:
            self.footer.addWidget(widget)
        return widget

    def show_error(self, err: RuleError | DbError) -> None:
        detail = err.detail if isinstance(err, DbError) else "Business rule checked by the application"
        self.banner.show_message(err.message, detail)

    def options(self, lookup_name: str) -> list[Option]:
        try:
            return db.lookup(self.db, lookup_name)
        except DbError as err:
            self.message.emit(f"Could not load {lookup_name} list: {err.message}")
            return []


# ---- form helpers -------------------------------------------------------------


class FormGrid(QGridLayout):
    """Rows of caption / input / error, laid out in up to ``columns`` pairs per row."""

    def __init__(self, columns: int = 3) -> None:
        super().__init__()
        self._columns = columns
        self._count = 0
        self.setHorizontalSpacing(12)
        self.setVerticalSpacing(2)
        self.errors: dict[str, QLabel] = {}
        self.inputs: dict[str, QWidget] = {}

    def add(self, key: str, caption: str, widget: QWidget, span: int = 1) -> QWidget:
        row = (self._count // self._columns) * 2
        col = (self._count % self._columns) * 2
        self.addWidget(label(caption, "fieldLabel"), row, col)
        self.addWidget(widget, row, col + 1, 1, span * 2 - 1)
        error = field_error_label()
        self.addWidget(error, row + 1, col + 1, 1, span * 2 - 1)
        for stretch_col in range(col + 1, col + span * 2, 2):
            self.setColumnStretch(stretch_col, 1)
        self.errors[key] = error
        self.inputs[key] = widget
        self._count += span
        return widget

    def set_error(self, key: str | None, message: str | None) -> bool:
        if key not in self.errors:
            return False
        show_field_error(self.errors[key], message)
        set_style_property(self.inputs[key], "invalid", bool(message))
        return True

    def clear_errors(self) -> None:
        for key in self.errors:
            self.set_error(key, None)


def option_combo(placeholder: str) -> QComboBox:
    combo = QComboBox()
    combo.setPlaceholderText(placeholder)
    combo.setMaxVisibleItems(18)
    combo.setMinimumWidth(200)
    return combo


def fill_combo(combo: QComboBox, options: Sequence[Option], keep: bool = True) -> None:
    """Replace a combo's items, keeping the current selection when it still exists."""
    current = combo.currentData() if keep else None
    combo.blockSignals(True)
    combo.clear()
    for option in options:
        combo.addItem(option.label, option.id)
    combo.setCurrentIndex(combo.findData(current) if current is not None else -1)
    combo.blockSignals(False)


def date_edit() -> QDateEdit:
    editor = QDateEdit(QDate.currentDate())
    editor.setCalendarPopup(True)
    editor.setDisplayFormat("yyyy-MM-dd")
    return editor


def date_value(editor: QDateEdit) -> date:
    return editor.date().toPython()


def selected_id(combo: QComboBox) -> int | None:
    return combo.currentData() if combo.currentIndex() >= 0 else None


# ---- line editor --------------------------------------------------------------

PUTAWAY = "putaway"
PICK = "pick"


class LineEditor(QWidget):
    """Entry row plus a grid of document lines.

    ``putaway`` mode picks any bin and product (receiving). ``pick`` mode offers
    only bin/product balances that hold stock and caps quantities at what is
    available (transfers and dispatches).
    """

    changed = Signal()

    def __init__(self, mode: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = mode
        self._lines: list[Row] = []
        self._stock: dict[tuple[int, int], Row] = {}
        self._bins: dict[int, Option] = {}
        self._products: dict[int, Option] = {}

        self._bin = option_combo("Select bin…")
        self._product = option_combo("Select product…")
        self._pick = option_combo("Select stock to pick…")
        self._pick.setMinimumWidth(420)
        self._quantity = QLineEdit()
        self._quantity.setPlaceholderText("Quantity")
        self._quantity.setFixedWidth(110)
        self._add = button("Add line")
        self._remove = button("Remove line", "danger")
        self._remove.setEnabled(False)
        self._error = field_error_label()
        self._total = label("", "muted")

        columns = [
            GridColumn("bin_code", "Bin", CODE),
            GridColumn("sku", "SKU", CODE),
            GridColumn("product_name", "Product"),
            GridColumn("quantity", "Quantity", NUMBER, summed=True),
        ]
        if mode == PICK:
            columns.append(GridColumn("available", "Available", NUMBER))
        self.grid = DataGrid(columns, lambda row: (row["bin_id"], row["product_id"]), refit=True)
        self.grid.setMinimumHeight(150)
        self.grid.setSortingEnabled(False)

        self._build_layout()
        self._add.clicked.connect(self._add_line)
        self._quantity.returnPressed.connect(self._add_line)
        self._remove.clicked.connect(self._remove_selected)
        self.grid.selectionModel().selectionChanged.connect(
            lambda *_: self._remove.setEnabled(bool(self.grid.selected_rows()))
        )
        for widget in (self._bin, self._product, self._pick):
            widget.currentIndexChanged.connect(lambda *_: self._show_error(None))
        self._quantity.textChanged.connect(lambda *_: self._show_error(None))

    def _build_layout(self) -> None:
        entry = QHBoxLayout()
        entry.setSpacing(8)
        if self._mode == PICK:
            entry.addWidget(self._pick, 3)
        else:
            entry.addWidget(self._bin, 2)
            entry.addWidget(self._product, 3)
        entry.addWidget(self._quantity)
        entry.addWidget(self._add)

        footer = QHBoxLayout()
        footer.addWidget(self._remove)
        footer.addStretch(1)
        footer.addWidget(self._total)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(entry)
        layout.addWidget(self._error)
        layout.addWidget(self.grid)
        layout.addLayout(footer)
        self._refresh()

    # ---- sources ------------------------------------------------------------

    def set_bins(self, options: Sequence[Option]) -> None:
        self._bins = {option.id: option for option in options}
        fill_combo(self._bin, options)

    def set_products(self, options: Sequence[Option]) -> None:
        self._products = {option.id: option for option in options}
        fill_combo(self._product, options)

    def set_stock(self, rows: Sequence[Row]) -> None:
        self._stock = {stock_key(row): row for row in rows}
        fill_stock_combo(self._pick, rows, use_available=True)
        for line in self._lines:
            stock = self._stock.get(stock_key(line))
            line["available"] = stock["available"] if stock else 0
        self._refresh()

    # ---- lines ----------------------------------------------------------------

    def lines(self) -> list[Line]:
        return [Line(row["bin_id"], row["product_id"], row["quantity"]) for row in self._lines]

    def clear(self) -> None:
        self._lines = []
        self._quantity.clear()
        self._show_error(None)
        self._refresh()

    def show_line_error(self, index: int | None, message: str) -> None:
        if index is not None and 0 <= index < len(self._lines):
            row = self._lines[index]
            self.grid.select_keys([(row["bin_id"], row["product_id"])])
        self._show_error(message)

    def _add_line(self) -> None:
        quantity, error = parse_int(self._quantity.text().strip(), 1)
        if error or quantity is None:
            self._show_error(f"Quantity: {error or 'required.'}")
            return
        row = self._entry_row()
        if row is None:
            return
        key = (row["bin_id"], row["product_id"])
        existing = next((line for line in self._lines if (line["bin_id"], line["product_id"]) == key), None)
        total = quantity + (existing["quantity"] if existing else 0)
        if self._mode == PICK and total > row["available"]:
            self._show_error(f"Only {row['available']:,} available in {row['bin_code']}; {total:,} requested.")
            return
        if existing:
            existing["quantity"] = total
        else:
            row["quantity"] = quantity
            self._lines.append(row)
        self._quantity.clear()
        self._show_error(None)
        self._refresh(select=key)

    def _entry_row(self) -> Row | None:
        if self._mode == PICK:
            key = self._pick.currentData() if self._pick.currentIndex() >= 0 else None
            if key is None or key not in self._stock:
                self._show_error("Select the stock to pick.")
                return None
            stock = self._stock[key]
            return {
                "bin_id": stock["bin_id"],
                "bin_code": stock["bin_code"],
                "product_id": stock["product_id"],
                "sku": stock["sku"],
                "product_name": stock["product_name"],
                "available": stock["available"],
            }
        bin_id, product_id = selected_id(self._bin), selected_id(self._product)
        if bin_id is None or product_id is None:
            self._show_error("Select a bin and a product.")
            return None
        bin_option, product_option = self._bins[bin_id], self._products[product_id]
        return {
            "bin_id": bin_id,
            "bin_code": bin_option.data["bin_code"],
            "product_id": product_id,
            "sku": product_option.data["sku"],
            "product_name": product_option.data["name"],
        }

    def _remove_selected(self) -> None:
        keys = set(self.grid.selected_keys())
        self._lines = [line for line in self._lines if (line["bin_id"], line["product_id"]) not in keys]
        self._refresh()

    def _refresh(self, select: tuple[int, int] | None = None) -> None:
        self.grid.set_rows([dict(line) for line in self._lines], [select] if select else [])
        units = sum(line["quantity"] for line in self._lines)
        count = len(self._lines)
        self._total.setText(f"{count} line{'s' if count != 1 else ''}  ·  {units:,} units")
        self._remove.setEnabled(bool(self.grid.selected_rows()))
        self.changed.emit()

    def _show_error(self, message: str | None) -> None:
        show_field_error(self._error, message)


def stock_key(row: Row) -> str:
    """Combo data key for a bin/product balance (plain strings round-trip through Qt reliably)."""
    return f"{row['bin_id']}:{row['product_id']}"


def fill_stock_combo(combo: QComboBox, rows: Sequence[Row], use_available: bool) -> None:
    """List bin/product balances; entries with nothing to take are shown disabled."""
    current = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    noun = "available" if use_available else "on hand"
    for row in rows:
        amount = row["available"] if use_available else row["on_hand"]
        combo.addItem(f"{row['bin_code']}   {row['sku']}   {row['product_name']}   ·   {amount:,} {noun}", stock_key(row))
        if amount <= 0:
            combo.model().item(combo.count() - 1).setEnabled(False)
    combo.setCurrentIndex(combo.findData(current) if current is not None else -1)
    combo.blockSignals(False)
