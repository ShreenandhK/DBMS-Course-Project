"""Workflow pages: receiving, transfers, dispatch, damage and bin search."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from stm.db import Database
from stm.page import Page
from stm.workflows.bin_search import BinSearchPage
from stm.workflows.damage import DamagePage
from stm.workflows.dispatch import DispatchPage
from stm.workflows.receive import ReceivePage
from stm.workflows.transfers import NewTransferPage, ProcessTransfersPage


@dataclass(frozen=True)
class PageEntry:
    """A non-table page: sidebar key (must not clash with table names), label, tooltip, factory."""

    key: str
    title: str
    description: str
    factory: Callable[[Database], Page]


WORKFLOWS: tuple[PageEntry, ...] = (
    PageEntry("receive", "Receive stock", "Record goods arriving from a supplier and put them into bins.", ReceivePage),
    PageEntry("new_transfer", "New transfer", "Start moving stock from one warehouse to another.", NewTransferPage),
    PageEntry(
        "process_transfers",
        "Process transfers",
        "Ship, put away and confirm transfers that are still open.",
        ProcessTransfersPage,
    ),
    PageEntry("dispatch_stock", "Dispatch stock", "Send stock out of a warehouse to a customer.", DispatchPage),
    PageEntry("record_damage", "Record damage", "Write off damaged units from a bin.", DamagePage),
    PageEntry(
        "bin_search",
        "Bin search",
        "Find bins and what they hold by bin code, zone, SKU or product.",
        BinSearchPage,
    ),
)
