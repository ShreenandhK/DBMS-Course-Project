"""Report definitions: columns, keys and summary lines. The SQL lives in ``stm.db``."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from stm.schema import CODE, DATE, ID, NUMBER, PERCENT, STATUS, GridColumn, Row


@dataclass(frozen=True)
class ReportSpec:
    key: str
    title: str
    description: str
    columns: tuple[GridColumn, ...]
    key_columns: tuple[str, ...]
    summary: Callable[[list[Row]], str]

    def key_of(self, row: Row) -> tuple[Any, ...]:
        return tuple(row[column] for column in self.key_columns)


def _units(rows: list[Row], column: str) -> int:
    return sum(row.get(column) or 0 for row in rows)


def _plural(count: int, noun: str) -> str:
    return f"{count:,} {noun}{'' if count == 1 else 's'}"


def _warehouse_summary(rows: list[Row]) -> str:
    return (
        f"On hand <b>{_units(rows, 'on_hand'):,}</b>  ·  Reserved {_units(rows, 'reserved'):,}"
        f"  ·  Available <b>{_units(rows, 'available'):,}</b>"
    )


def _transfers_summary(rows: list[Row]) -> str:
    transfers = len({row["transfer_id"] for row in rows})
    in_transit = sum(row["quantity"] for row in rows if row["status"] == "IN_TRANSIT")
    pending = sum(row["quantity"] for row in rows if row["status"] == "PENDING")
    return (
        f"{_plural(transfers, 'transfer')}  ·  In transit (in no bin) <b>{in_transit:,}</b>"
        f"  ·  Pending (still in source bins) <b>{pending:,}</b>"
    )


def _utilization_summary(rows: list[Row]) -> str:
    bins, occupied = _units(rows, "bins"), _units(rows, "occupied")
    share = 100 * occupied / bins if bins else 0
    return f"Occupied <b>{occupied:,}</b> of {bins:,} bins ({share:.1f}%)  ·  Units {_units(rows, 'units'):,}"


def _ageing_summary(rows: list[Row]) -> str:
    oldest = max((row["age_days"] for row in rows), default=0)
    over_60 = sum(row["on_hand"] for row in rows if row["age_days"] > 60)
    return f"Oldest stock <b>{oldest}</b> days  ·  Units older than 60 days <b>{over_60:,}</b>"


def _damage_summary(rows: list[Row]) -> str:
    return f"{_plural(_units(rows, 'incidents'), 'incident')}  ·  Units damaged <b>{_units(rows, 'units'):,}</b>"


def _reorder_summary(rows: list[Row]) -> str:
    below = [row for row in rows if row["status"] == "REORDER"]
    return f"<b>{_plural(len(below), 'product')}</b> below reorder level  ·  Shortfall {_units(below, 'shortfall'):,} units"


REPORTS: tuple[ReportSpec, ...] = (
    ReportSpec(
        key="warehouse_stock",
        title="Warehouse stock",
        description="Units on hand per warehouse and product (from v_bin_stock); reserved = held by PENDING transfers.",
        columns=(
            GridColumn("warehouse_name", "Warehouse"),
            GridColumn("sku", "SKU", CODE),
            GridColumn("product_name", "Product"),
            GridColumn("bins", "Bins", NUMBER),
            GridColumn("on_hand", "On hand", NUMBER, strong=True),
            GridColumn("reserved", "Reserved", NUMBER),
            GridColumn("available", "Available", NUMBER),
        ),
        key_columns=("warehouse_id", "product_id"),
        summary=_warehouse_summary,
    ),
    ReportSpec(
        key="open_transfers",
        title="Pending and in transit",
        description="Transfer lines not yet confirmed. IN_TRANSIT units are in no bin; PENDING units still count in the source bin.",
        columns=(
            GridColumn("transfer_id", "Transfer", ID),
            GridColumn("status", "Status", STATUS),
            GridColumn("transfer_date", "Date", DATE),
            GridColumn("age_days", "Age (days)", NUMBER, strong=True),
            GridColumn("source_warehouse", "From"),
            GridColumn("dest_warehouse", "To"),
            GridColumn("source_bin_code", "Source bin", CODE),
            GridColumn("sku", "SKU", CODE),
            GridColumn("product_name", "Product"),
            GridColumn("quantity", "Quantity", NUMBER),
            GridColumn("dest_bin_code", "Dest bin", CODE),
        ),
        key_columns=("transfer_id", "source_bin_id", "product_id"),
        summary=_transfers_summary,
    ),
    ReportSpec(
        key="bin_utilization",
        title="Bin utilization",
        description="Bins per zone and how many hold stock. Bins have no capacity column, so utilization is the share of occupied bins.",
        columns=(
            GridColumn("warehouse_name", "Warehouse"),
            GridColumn("zone_name", "Zone"),
            GridColumn("bins", "Bins", NUMBER),
            GridColumn("occupied", "Occupied", NUMBER),
            GridColumn("empty_bins", "Empty", NUMBER),
            GridColumn("utilization", "Occupied %", PERCENT, strong=True),
            GridColumn("units", "Units on hand", NUMBER),
        ),
        key_columns=("zone_id",),
        summary=_utilization_summary,
    ),
    ReportSpec(
        key="stock_ageing",
        title="Stock ageing",
        description="Days since the first inbound movement (receipt or confirmed transfer) into each bin that still holds the product.",
        columns=(
            GridColumn("warehouse_name", "Warehouse"),
            GridColumn("bin_code", "Bin", CODE),
            GridColumn("sku", "SKU", CODE),
            GridColumn("product_name", "Product"),
            GridColumn("on_hand", "On hand", NUMBER),
            GridColumn("first_in", "First inbound", DATE),
            GridColumn("last_in", "Last inbound", DATE),
            GridColumn("age_days", "Age (days)", NUMBER, strong=True),
            GridColumn("age_band", "Age band"),
        ),
        key_columns=("bin_id", "product_id"),
        summary=_ageing_summary,
    ),
    ReportSpec(
        key="damaged_stock",
        title="Damaged stock",
        description="Damage per warehouse and product; damage % = units damaged / units received or transferred into that warehouse.",
        columns=(
            GridColumn("warehouse_name", "Warehouse"),
            GridColumn("sku", "SKU", CODE),
            GridColumn("product_name", "Product"),
            GridColumn("incidents", "Incidents", NUMBER),
            GridColumn("units", "Units damaged", NUMBER, strong=True),
            GridColumn("inbound", "Units received", NUMBER),
            GridColumn("damage_rate", "Damage %", PERCENT),
            GridColumn("bins", "Bins", CODE),
            GridColumn("last_date", "Last damage", DATE),
        ),
        key_columns=("warehouse_id", "product_id"),
        summary=_damage_summary,
    ),
    ReportSpec(
        key="reorder_needs",
        title="Reorder needs",
        description="Company-wide stock (on hand plus in transit) against each product's reorder level.",
        columns=(
            GridColumn("sku", "SKU", CODE),
            GridColumn("product_name", "Product"),
            GridColumn("reorder_level", "Reorder level", NUMBER),
            GridColumn("on_hand", "On hand", NUMBER),
            GridColumn("in_transit", "In transit", NUMBER),
            GridColumn("total", "Total", NUMBER, strong=True),
            GridColumn("shortfall", "Shortfall", NUMBER),
            GridColumn("status", "Status", STATUS),
        ),
        key_columns=("product_id",),
        summary=_reorder_summary,
    ),
)
