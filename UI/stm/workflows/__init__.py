"""Workflow pages: receiving, transfers, dispatch, damage and bin search."""
from __future__ import annotations

from collections.abc import Callable

from stm.db import Database
from stm.page import Page
from stm.workflows.bin_search import BinSearchPage
from stm.workflows.damage import DamagePage
from stm.workflows.dispatch import DispatchPage
from stm.workflows.receive import ReceivePage
from stm.workflows.transfers import NewTransferPage, ProcessTransfersPage

# (sidebar key, sidebar label, page factory); keys must not clash with table names.
WORKFLOWS: tuple[tuple[str, str, Callable[[Database], Page]], ...] = (
    ("receive", "Receive stock", ReceivePage),
    ("new_transfer", "New transfer", NewTransferPage),
    ("process_transfers", "Process transfers", ProcessTransfersPage),
    ("dispatch_stock", "Dispatch stock", DispatchPage),
    ("record_damage", "Record damage", DamagePage),
    ("bin_search", "Bin search", BinSearchPage),
)
