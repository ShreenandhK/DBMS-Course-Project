"""Description of every table the app shows: grid columns, form fields, keys and record names.

This module holds no SQL. The list queries in ``stm.db`` return columns whose
aliases match the ``GridColumn.key`` values defined here, and inserts use the
``Field.column`` names as column identifiers.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

Row = dict[str, Any]

TRANSFER_STATUSES: tuple[str, ...] = ("PENDING", "IN_TRANSIT", "CONFIRMED", "CANCELLED")
MAX_INT = 2_147_483_647


class Style(Enum):
    TEXT = auto()
    CODE = auto()  # monospace identifiers such as SKU and bin code
    ID = auto()  # monospace, right-aligned, no thousands separator
    NUMBER = auto()  # right-aligned with thousands separators
    DATE = auto()
    STATUS = auto()  # transfer status chip


class Kind(Enum):
    TEXT = auto()
    CODE = auto()  # monospace, upper-case identifier
    INTEGER = auto()
    DATE = auto()
    CHOICE = auto()
    REFERENCE = auto()  # foreign key, picked from a lookup


@dataclass(frozen=True)
class GridColumn:
    key: str
    label: str
    style: Style = Style.TEXT
    strong: bool = False  # semibold, for the column a reader looks at first
    summed: bool = False  # total of visible rows shown above the grid


@dataclass(frozen=True)
class Field:
    column: str
    label: str
    kind: Kind = Kind.TEXT
    required: bool = True
    max_length: int | None = None
    minimum: int | None = None
    reference: str | None = None
    choices: tuple[str, ...] = ()
    default: Any = None
    hint: str = ""


@dataclass(frozen=True)
class Distinct:
    """Two fields that must not hold the same value (mirrors a CHECK constraint)."""

    first: str
    second: str
    message: str


@dataclass(frozen=True)
class TableSpec:
    name: str
    title: str
    singular: str
    group: str
    primary_key: tuple[str, ...]
    grid: tuple[GridColumn, ...]
    describe: Callable[[Row], str]
    fields: tuple[Field, ...] = ()
    distinct: tuple[Distinct, ...] = ()
    auto_key: bool = False
    is_view: bool = False

    def key_of(self, row: Row) -> tuple[Any, ...]:
        return tuple(row[column] for column in self.primary_key)

    @property
    def can_insert(self) -> bool:
        return not self.is_view and bool(self.fields)


def _q(text: object) -> str:
    return f"“{text}”"


def _qty(row: Row) -> str:
    return f"{row['quantity']:,}"


ID = Style.ID
CODE = Style.CODE
NUMBER = Style.NUMBER
DATE = Style.DATE
STATUS = Style.STATUS


def _ref(column: str, label: str, reference: str, *, required: bool = True, hint: str = "") -> Field:
    return Field(column, label, Kind.REFERENCE, required=required, reference=reference, hint=hint)


def _quantity(label: str = "Quantity") -> Field:
    return Field("quantity", label, Kind.INTEGER, minimum=1, hint="Whole units, greater than zero")


def _date(column: str, label: str = "Date") -> Field:
    return Field(column, label, Kind.DATE)


SUPPLIER = TableSpec(
    name="supplier",
    title="Suppliers",
    singular="supplier",
    group="Master data",
    primary_key=("supplier_id",),
    auto_key=True,
    grid=(
        GridColumn("supplier_id", "ID", ID),
        GridColumn("name", "Name"),
        GridColumn("contact", "Contact"),
    ),
    fields=(
        Field("name", "Name", max_length=100),
        Field("contact", "Contact", max_length=100, hint="Phone number, e.g. +91 40 4012 3456"),
    ),
    describe=lambda r: f"supplier {_q(r['name'])}",
)

PRODUCT = TableSpec(
    name="product",
    title="Products",
    singular="product",
    group="Master data",
    primary_key=("product_id",),
    auto_key=True,
    grid=(
        GridColumn("product_id", "ID", ID),
        GridColumn("sku", "SKU", CODE),
        GridColumn("name", "Name"),
        GridColumn("reorder_level", "Reorder level", NUMBER),
    ),
    fields=(
        Field("sku", "SKU", Kind.CODE, max_length=30, hint="Unique code, e.g. ELE-LED-012"),
        Field("name", "Name", max_length=100),
        Field(
            "reorder_level",
            "Reorder level",
            Kind.INTEGER,
            minimum=0,
            default=0,
            hint="Minimum total units before reordering",
        ),
    ),
    describe=lambda r: f"product {r['sku']} {_q(r['name'])}",
)

WAREHOUSE = TableSpec(
    name="warehouse",
    title="Warehouses",
    singular="warehouse",
    group="Locations",
    primary_key=("warehouse_id",),
    auto_key=True,
    grid=(
        GridColumn("warehouse_id", "ID", ID),
        GridColumn("name", "Name"),
        GridColumn("location", "Location"),
    ),
    fields=(
        Field("name", "Name", max_length=100),
        Field("location", "Location", max_length=150, hint="Area, city, state"),
    ),
    describe=lambda r: f"warehouse {_q(r['name'])}",
)

ZONE = TableSpec(
    name="zone",
    title="Zones",
    singular="zone",
    group="Locations",
    primary_key=("zone_id",),
    auto_key=True,
    grid=(
        GridColumn("zone_id", "ID", ID),
        GridColumn("zone_name", "Zone"),
        GridColumn("warehouse_name", "Warehouse"),
    ),
    fields=(
        _ref("warehouse_id", "Warehouse", "warehouse"),
        Field("zone_name", "Zone name", max_length=50, hint="Unique within the warehouse"),
    ),
    describe=lambda r: f"zone {_q(r['zone_name'])} in {r['warehouse_name']}",
)

BIN = TableSpec(
    name="bin",
    title="Bins",
    singular="bin",
    group="Locations",
    primary_key=("bin_id",),
    auto_key=True,
    grid=(
        GridColumn("bin_id", "ID", ID),
        GridColumn("bin_code", "Bin code", CODE),
        GridColumn("zone_name", "Zone"),
        GridColumn("warehouse_name", "Warehouse"),
    ),
    fields=(
        _ref("zone_id", "Zone", "zone"),
        Field("bin_code", "Bin code", Kind.CODE, max_length=20, hint="Format WH-ZONE-NN, e.g. HYD-BS-04"),
    ),
    describe=lambda r: f"bin {r['bin_code']}",
)

RECEIPT = TableSpec(
    name="receipt",
    title="Receipts",
    singular="receipt",
    group="Inbound",
    primary_key=("receipt_id",),
    auto_key=True,
    grid=(
        GridColumn("receipt_id", "Receipt", ID),
        GridColumn("receipt_date", "Date", DATE),
        GridColumn("supplier_name", "Supplier"),
        GridColumn("warehouse_name", "Warehouse"),
    ),
    fields=(
        _ref("supplier_id", "Supplier", "supplier"),
        _ref("warehouse_id", "Warehouse", "warehouse"),
        _date("receipt_date", "Receipt date"),
    ),
    describe=lambda r: f"receipt #{r['receipt_id']} ({r['receipt_date']}, {r['supplier_name']})",
)

RECEIPT_LINE = TableSpec(
    name="receipt_line",
    title="Receipt lines",
    singular="receipt line",
    group="Inbound",
    primary_key=("receipt_id", "bin_id", "product_id"),
    grid=(
        GridColumn("receipt_id", "Receipt", ID),
        GridColumn("bin_code", "Bin", CODE),
        GridColumn("sku", "SKU", CODE),
        GridColumn("product_name", "Product"),
        GridColumn("quantity", "Quantity", NUMBER),
    ),
    fields=(
        _ref("receipt_id", "Receipt", "receipt"),
        _ref("bin_id", "Bin", "bin"),
        _ref("product_id", "Product", "product"),
        _quantity("Quantity received"),
    ),
    describe=lambda r: f"receipt #{r['receipt_id']} line: {_qty(r)} × {r['sku']} into {r['bin_code']}",
)

TRANSFER = TableSpec(
    name="transfer",
    title="Transfers",
    singular="transfer",
    group="Transfers",
    primary_key=("transfer_id",),
    auto_key=True,
    grid=(
        GridColumn("transfer_id", "Transfer", ID),
        GridColumn("status", "Status", STATUS),
        GridColumn("transfer_date", "Date", DATE),
        GridColumn("source_warehouse", "From warehouse"),
        GridColumn("dest_warehouse", "To warehouse"),
    ),
    fields=(
        _ref("source_warehouse_id", "From warehouse", "warehouse"),
        _ref("dest_warehouse_id", "To warehouse", "warehouse"),
        _date("transfer_date", "Transfer date"),
        Field("status", "Status", Kind.CHOICE, choices=TRANSFER_STATUSES, default="PENDING"),
    ),
    distinct=(
        Distinct("source_warehouse_id", "dest_warehouse_id", "Source and destination warehouse must be different."),
    ),
    describe=lambda r: (
        f"transfer #{r['transfer_id']} ({r['source_warehouse']} → {r['dest_warehouse']}, {r['status']})"
    ),
)

TRANSFER_LINE = TableSpec(
    name="transfer_line",
    title="Transfer lines",
    singular="transfer line",
    group="Transfers",
    primary_key=("transfer_id", "source_bin_id", "product_id"),
    grid=(
        GridColumn("transfer_id", "Transfer", ID),
        GridColumn("status", "Transfer status", STATUS),
        GridColumn("source_bin_code", "Source bin", CODE),
        GridColumn("sku", "SKU", CODE),
        GridColumn("product_name", "Product"),
        GridColumn("dest_bin_code", "Dest bin", CODE),
        GridColumn("quantity", "Quantity", NUMBER),
    ),
    fields=(
        _ref("transfer_id", "Transfer", "transfer"),
        _ref("source_bin_id", "Source bin", "bin"),
        _ref("product_id", "Product", "product"),
        _quantity("Quantity"),
        _ref(
            "dest_bin_id",
            "Destination bin",
            "bin",
            required=False,
            hint="Leave empty until put-away; required once the transfer is confirmed",
        ),
    ),
    distinct=(Distinct("source_bin_id", "dest_bin_id", "Destination bin must be different from the source bin."),),
    describe=lambda r: (
        f"transfer #{r['transfer_id']} line: {_qty(r)} × {r['sku']} from {r['source_bin_code']}"
    ),
)

DISPATCH = TableSpec(
    name="dispatch",
    title="Dispatches",
    singular="dispatch",
    group="Outbound",
    primary_key=("dispatch_id",),
    auto_key=True,
    grid=(
        GridColumn("dispatch_id", "Dispatch", ID),
        GridColumn("dispatch_date", "Date", DATE),
        GridColumn("warehouse_name", "Warehouse"),
        GridColumn("destination", "Destination"),
    ),
    fields=(
        _ref("warehouse_id", "Warehouse", "warehouse"),
        Field("destination", "Destination", max_length=150, hint="Customer and delivery address"),
        _date("dispatch_date", "Dispatch date"),
    ),
    describe=lambda r: f"dispatch #{r['dispatch_id']} to {r['destination']}",
)

DISPATCH_LINE = TableSpec(
    name="dispatch_line",
    title="Dispatch lines",
    singular="dispatch line",
    group="Outbound",
    primary_key=("dispatch_id", "bin_id", "product_id"),
    grid=(
        GridColumn("dispatch_id", "Dispatch", ID),
        GridColumn("bin_code", "Bin", CODE),
        GridColumn("sku", "SKU", CODE),
        GridColumn("product_name", "Product"),
        GridColumn("quantity", "Quantity", NUMBER),
    ),
    fields=(
        _ref("dispatch_id", "Dispatch", "dispatch"),
        _ref("bin_id", "Bin", "bin"),
        _ref("product_id", "Product", "product"),
        _quantity("Quantity shipped"),
    ),
    describe=lambda r: f"dispatch #{r['dispatch_id']} line: {_qty(r)} × {r['sku']} from {r['bin_code']}",
)

DAMAGED = TableSpec(
    name="damaged",
    title="Damaged stock",
    singular="damage record",
    group="Stock",
    primary_key=("bin_id", "product_id", "damage_date"),
    grid=(
        GridColumn("bin_code", "Bin", CODE),
        GridColumn("sku", "SKU", CODE),
        GridColumn("product_name", "Product"),
        GridColumn("damage_date", "Date", DATE),
        GridColumn("quantity", "Quantity", NUMBER, summed=True),
        GridColumn("reason", "Reason"),
    ),
    fields=(
        _ref("bin_id", "Bin", "bin"),
        _ref("product_id", "Product", "product"),
        _date("damage_date", "Damage date"),
        _quantity("Quantity damaged"),
        Field("reason", "Reason", max_length=200),
    ),
    describe=lambda r: f"damage record: {_qty(r)} × {r['sku']} in {r['bin_code']} on {r['damage_date']}",
)

BIN_STOCK = TableSpec(
    name="v_bin_stock",
    title="Bin stock",
    singular="bin stock row",
    group="Stock",
    primary_key=("bin_id", "product_id"),
    is_view=True,
    grid=(
        GridColumn("warehouse_name", "Warehouse"),
        GridColumn("bin_code", "Bin", CODE),
        GridColumn("sku", "SKU", CODE),
        GridColumn("product_name", "Product"),
        GridColumn("on_hand", "On hand", NUMBER, strong=True, summed=True),
        GridColumn("received", "Received", NUMBER),
        GridColumn("transferred_in", "Transfer in", NUMBER),
        GridColumn("transferred_out", "Transfer out", NUMBER),
        GridColumn("dispatched", "Dispatched", NUMBER),
        GridColumn("damaged", "Damaged", NUMBER),
    ),
    describe=lambda r: f"{r['sku']} in {r['bin_code']}",
)

TABLES: tuple[TableSpec, ...] = (
    BIN_STOCK,
    DAMAGED,
    RECEIPT,
    RECEIPT_LINE,
    TRANSFER,
    TRANSFER_LINE,
    DISPATCH,
    DISPATCH_LINE,
    WAREHOUSE,
    ZONE,
    BIN,
    PRODUCT,
    SUPPLIER,
)

GROUP_ORDER: tuple[str, ...] = ("Stock", "Inbound", "Transfers", "Outbound", "Locations", "Master data")

BY_NAME: dict[str, TableSpec] = {spec.name: spec for spec in TABLES}


def grouped() -> list[tuple[str, list[TableSpec]]]:
    return [(group, [spec for spec in TABLES if spec.group == group]) for group in GROUP_ORDER]
