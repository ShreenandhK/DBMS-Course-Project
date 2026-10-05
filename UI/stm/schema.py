"""Description of every table the app shows: grid columns, keys and record names.

This module holds no SQL. The list queries in ``stm.db`` return columns whose
aliases match the ``GridColumn.key`` values defined here.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

Row = dict[str, Any]


class Style(Enum):
    TEXT = auto()
    CODE = auto()  # monospace identifiers such as SKU and bin code
    ID = auto()  # monospace, right-aligned, no thousands separator
    NUMBER = auto()  # right-aligned with thousands separators
    DATE = auto()
    STATUS = auto()  # transfer status chip


@dataclass(frozen=True)
class GridColumn:
    key: str
    label: str
    style: Style = Style.TEXT


@dataclass(frozen=True)
class TableSpec:
    name: str
    title: str
    singular: str
    group: str
    primary_key: tuple[str, ...]
    grid: tuple[GridColumn, ...]
    describe: Callable[[Row], str]
    auto_key: bool = False
    is_view: bool = False

    def key_of(self, row: Row) -> tuple[Any, ...]:
        return tuple(row[column] for column in self.primary_key)


def _q(text: object) -> str:
    return f"“{text}”"


def _qty(row: Row) -> str:
    return f"{row['quantity']:,}"


ID = Style.ID
CODE = Style.CODE
NUMBER = Style.NUMBER
DATE = Style.DATE
STATUS = Style.STATUS

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
        GridColumn("quantity", "Quantity", NUMBER),
        GridColumn("reason", "Reason"),
    ),
    describe=lambda r: f"damage record: {_qty(r)} × {r['sku']} in {r['bin_code']} on {r['damage_date']}",
)

TABLES: tuple[TableSpec, ...] = (
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
