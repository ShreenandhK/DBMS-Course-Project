"""Sidebar structure: which pages exist, how they are grouped and what each one is for."""
from __future__ import annotations

from dataclasses import dataclass

from stm import schema
from stm.reports_page import ReportsPage
from stm.table_page import TablePage
from stm.workflows import WORKFLOWS, PageEntry


@dataclass(frozen=True)
class Group:
    title: str
    description: str
    keys: tuple[str, ...]


REPORTS = PageEntry(
    "reports", "Reports", "Stock, transfer, bin use, ageing, damage and reorder reports.", ReportsPage
)


def _table_entry(spec: schema.TableSpec) -> PageEntry:
    return PageEntry(spec.name, spec.title, spec.description, lambda database, spec=spec: TablePage(database, spec))


PAGES: dict[str, PageEntry] = {
    entry.key: entry for entry in (*WORKFLOWS, REPORTS, *(_table_entry(spec) for spec in schema.TABLES))
}

GROUPS: tuple[Group, ...] = (
    Group(
        "Tasks",
        "Guided tasks. Each records a complete movement in one step and checks the rules first.",
        ("receive", "new_transfer", "process_transfers", "dispatch_stock", "record_damage"),
    ),
    Group(
        "Look up",
        "See current stock, search bins and run reports. Nothing is changed here.",
        ("v_bin_stock", "bin_search", "reports"),
    ),
    Group(
        "Movement records",
        "The individual records the tasks write. View, add or delete them directly.",
        ("receipt", "receipt_line", "transfer", "transfer_line", "dispatch", "dispatch_line", "damaged"),
    ),
    Group(
        "Locations",
        "Where stock can be stored: warehouse, then zone, then bin.",
        ("warehouse", "zone", "bin"),
    ),
    Group(
        "Products & suppliers",
        "What is stored and who delivers it.",
        ("product", "supplier"),
    ),
)

FIRST_PAGE = "v_bin_stock"
