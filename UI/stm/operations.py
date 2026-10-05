"""Warehouse workflows and the business rules the database does not enforce.

Rules checked here (see the knowledge file, section 7):
- a bin used on a receipt, transfer or dispatch belongs to that document's warehouse;
- a transfer, dispatch or damage quantity does not exceed what the bin holds;
  stock reserved by PENDING transfers is not available to other transfers or dispatches;
- a transfer only moves forward: PENDING -> IN_TRANSIT -> CONFIRMED, or to CANCELLED;
  CONFIRMED and CANCELLED are final;
- deleting a record never leaves a bin with negative stock.

Rules are checked before the write transaction starts. Each workflow then writes
its header and lines in a single transaction. This module holds no SQL.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from stm import db, schema
from stm.db import Database

ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "PENDING": ("IN_TRANSIT", "CONFIRMED", "CANCELLED"),
    "IN_TRANSIT": ("CONFIRMED", "CANCELLED"),
    "CONFIRMED": (),
    "CANCELLED": (),
}


class RuleError(Exception):
    """A business rule violation, phrased for the user.

    ``field`` names the form column it belongs to; ``line`` the 0-based line index.
    """

    def __init__(self, message: str, *, field: str | None = None, line: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field
        self.line = line


@dataclass(frozen=True)
class Line:
    bin_id: int
    product_id: int
    quantity: int


# ---- rule checks --------------------------------------------------------------


def check_transition(transfer_id: int, current: str, new: str) -> None:
    if new not in ALLOWED_TRANSITIONS.get(current, ()):
        allowed = ", ".join(ALLOWED_TRANSITIONS.get(current, ())) or "none (final state)"
        raise RuleError(f"Transfer #{transfer_id} is {current}; it cannot change to {new}. Allowed: {allowed}.")


def check_bin_in_warehouse(
    database: Database, bin_id: int, warehouse_id: int, *, field: str, line: int | None = None, role: str = "Bin"
) -> None:
    location = db.bin_location(database, bin_id)
    if location is None:
        raise RuleError(f"{role} no longer exists.", field=field, line=line)
    if location["warehouse_id"] != warehouse_id:
        expected = db.warehouse_name(database, warehouse_id)
        raise RuleError(
            f"{role} {location['bin_code']} belongs to {location['warehouse_name']}, not {expected}.",
            field=field,
            line=line,
        )


def check_stock(
    database: Database,
    lines: Sequence[Line],
    *,
    respect_reservations: bool,
    exclude_transfer_id: int | None = None,
    field: str = "quantity",
) -> None:
    """Quantities drawn from each bin/product (summed over lines) must fit what is there."""
    wanted: dict[tuple[int, int], int] = defaultdict(int)
    first_line: dict[tuple[int, int], int] = {}
    for index, line in enumerate(lines):
        key = (line.bin_id, line.product_id)
        wanted[key] += line.quantity
        first_line.setdefault(key, index)
    for (bin_id, product_id), quantity in wanted.items():
        position = db.stock_position(database, bin_id, product_id, exclude_transfer_id)
        limit = position.available if respect_reservations else position.on_hand
        if quantity <= limit:
            continue
        raise RuleError(
            _shortage_message(database, bin_id, product_id, quantity, position, respect_reservations),
            field=field,
            line=first_line[(bin_id, product_id)],
        )


def _shortage_message(
    database: Database, bin_id: int, product_id: int, quantity: int, position: db.StockPosition, reservations: bool
) -> str:
    location = db.bin_location(database, bin_id)
    product = db.product_row(database, product_id)
    bin_code = location["bin_code"] if location else f"bin {bin_id}"
    sku = product["sku"] if product else f"product {product_id}"
    if reservations and position.reserved:
        return (
            f"Only {max(position.available, 0):,} of {sku} available in {bin_code} "
            f"({position.on_hand:,} on hand, {position.reserved:,} reserved by pending transfers); "
            f"{quantity:,} requested."
        )
    return f"Only {max(position.on_hand, 0):,} of {sku} on hand in {bin_code}; {quantity:,} requested."


def check_insert(database: Database, spec: schema.TableSpec, values: dict[str, Any]) -> None:
    """Business rules for single-row inserts made from the table pages."""
    if spec is schema.RECEIPT_LINE:
        receipt = db.header_row(database, "receipt", values["receipt_id"])
        if receipt:
            check_bin_in_warehouse(database, values["bin_id"], receipt["warehouse_id"], field="bin_id")
    elif spec is schema.DISPATCH_LINE:
        dispatch_row = db.header_row(database, "dispatch", values["dispatch_id"])
        if dispatch_row:
            check_bin_in_warehouse(database, values["bin_id"], dispatch_row["warehouse_id"], field="bin_id")
        check_stock(database, [_line(values, "bin_id")], respect_reservations=True)
    elif spec is schema.TRANSFER_LINE:
        transfer = db.header_row(database, "transfer", values["transfer_id"])
        if transfer:
            check_bin_in_warehouse(
                database, values["source_bin_id"], transfer["source_warehouse_id"], field="source_bin_id", role="Source bin"
            )
            if values.get("dest_bin_id") is not None:
                check_bin_in_warehouse(
                    database, values["dest_bin_id"], transfer["dest_warehouse_id"], field="dest_bin_id",
                    role="Destination bin",
                )
        check_stock(database, [_line(values, "source_bin_id")], respect_reservations=True)
    elif spec is schema.DAMAGED:
        check_stock(database, [_line(values, "bin_id")], respect_reservations=False)


def check_delete(database: Database, spec: schema.TableSpec, rows: Sequence[dict[str, Any]]) -> None:
    """Refuse a delete that would leave any bin with negative stock.

    Deleting a record undoes its movement. Removing a receipt (line) or a confirmed transfer
    takes stock back out of a bin; if that stock was already dispatched, transferred or written
    off, the bin would go below zero.
    """
    change: dict[tuple[int, int], int] = defaultdict(int)
    for row in rows:
        for bin_id, product_id, delta in _stock_change_if_deleted(database, spec, row):
            change[(bin_id, product_id)] += delta
    for (bin_id, product_id), delta in change.items():
        if delta >= 0:
            continue
        on_hand = db.stock_position(database, bin_id, product_id).on_hand
        if on_hand + delta < 0:
            location = db.bin_location(database, bin_id)
            product = db.product_row(database, product_id)
            bin_code = location["bin_code"] if location else f"bin {bin_id}"
            sku = product["sku"] if product else f"product {product_id}"
            raise RuleError(
                f"Deleting this would leave {bin_code} with {on_hand + delta:,} of {sku} "
                f"({on_hand:,} on hand now, {-delta:,} would be taken out). Some of this stock has already "
                "been dispatched, transferred or written off; delete or reverse those records first."
            )


def _stock_change_if_deleted(
    database: Database, spec: schema.TableSpec, row: dict[str, Any]
) -> list[tuple[int, int, int]]:
    """(bin_id, product_id, change in on-hand) caused by deleting one record."""
    if spec is schema.RECEIPT_LINE:
        return [(row["bin_id"], row["product_id"], -row["quantity"])]
    if spec is schema.RECEIPT:
        return [
            (line["bin_id"], line["product_id"], -line["quantity"])
            for line in db.receipt_lines(database, row["receipt_id"])
        ]
    if spec is schema.TRANSFER_LINE:
        return _transfer_line_change(row["status"], row)
    if spec is schema.TRANSFER:
        return [
            change
            for line in db.transfer_lines(database, row["transfer_id"])
            for change in _transfer_line_change(row["status"], line)
        ]
    return []  # dispatches and damage only ever add stock back when deleted


def _transfer_line_change(status: str, line: dict[str, Any]) -> list[tuple[int, int, int]]:
    changes = []
    if status in ("IN_TRANSIT", "CONFIRMED"):
        changes.append((line["source_bin_id"], line["product_id"], line["quantity"]))
    if status == "CONFIRMED" and line.get("dest_bin_id") is not None:
        changes.append((line["dest_bin_id"], line["product_id"], -line["quantity"]))
    return changes


def _line(values: dict[str, Any], bin_column: str) -> Line:
    return Line(values[bin_column], values["product_id"], values["quantity"])


def _require_lines(lines: Sequence[Line]) -> None:
    if not lines:
        raise RuleError("Add at least one line.")


def _check_bins(database: Database, lines: Iterable[Line], warehouse_id: int) -> None:
    for index, line in enumerate(lines):
        check_bin_in_warehouse(database, line.bin_id, warehouse_id, field="bin_id", line=index)


# ---- workflows --------------------------------------------------------------


def receive(database: Database, supplier_id: int, warehouse_id: int, receipt_date: date, lines: Sequence[Line]) -> int:
    """Post a receipt and put its lines away into bins of the receiving warehouse."""
    _require_lines(lines)
    _check_bins(database, lines, warehouse_id)
    with database.transaction() as tx:
        (receipt_id,) = db.insert_values(
            tx,
            schema.RECEIPT,
            {"supplier_id": supplier_id, "warehouse_id": warehouse_id, "receipt_date": receipt_date},
        )
        for line in lines:
            db.insert_values(
                tx,
                schema.RECEIPT_LINE,
                {"receipt_id": receipt_id, "bin_id": line.bin_id, "product_id": line.product_id, "quantity": line.quantity},
            )
    return int(receipt_id)


def create_transfer(
    database: Database, source_id: int, dest_id: int, transfer_date: date, lines: Sequence[Line]
) -> int:
    """Initiate a PENDING transfer; its stock stays in the source bins and is reserved."""
    if source_id == dest_id:
        raise RuleError("Source and destination warehouse must be different.", field="dest_warehouse_id")
    _require_lines(lines)
    _check_bins(database, lines, source_id)
    check_stock(database, lines, respect_reservations=True)
    with database.transaction() as tx:
        (transfer_id,) = db.insert_values(
            tx,
            schema.TRANSFER,
            {
                "source_warehouse_id": source_id,
                "dest_warehouse_id": dest_id,
                "transfer_date": transfer_date,
                "status": "PENDING",
            },
        )
        for line in lines:
            db.insert_values(
                tx,
                schema.TRANSFER_LINE,
                {
                    "transfer_id": transfer_id,
                    "source_bin_id": line.bin_id,
                    "product_id": line.product_id,
                    "quantity": line.quantity,
                },
            )
    return int(transfer_id)


PutAway = dict[tuple[int, int], int | None]  # (source_bin_id, product_id) -> destination bin


def ship_transfer(database: Database, transfer_id: int) -> None:
    """PENDING -> IN_TRANSIT: stock leaves the source bins."""
    transfer = _transfer(database, transfer_id)
    check_transition(transfer_id, transfer["status"], "IN_TRANSIT")
    _check_transfer_stock(database, transfer_id)
    _change_status(database, transfer_id, transfer["status"], "IN_TRANSIT", {})


def save_putaway(database: Database, transfer_id: int, putaway: PutAway) -> None:
    """Record destination bins without changing the transfer status."""
    transfer = _transfer(database, transfer_id)
    if transfer["status"] not in ("PENDING", "IN_TRANSIT"):
        raise RuleError(f"Transfer #{transfer_id} is {transfer['status']}; its put-away bins can no longer change.")
    _check_putaway(database, transfer, putaway)
    with database.transaction() as tx:
        _write_putaway(tx, transfer_id, putaway)


def confirm_transfer(database: Database, transfer_id: int, putaway: PutAway) -> None:
    """Save put-away bins and mark the transfer CONFIRMED in one transaction; credits the destination."""
    transfer = _transfer(database, transfer_id)
    check_transition(transfer_id, transfer["status"], "CONFIRMED")
    _check_putaway(database, transfer, putaway)
    missing = [key for key, bin_id in putaway.items() if bin_id is None]
    if missing or len(putaway) != len(db.transfer_lines(database, transfer_id)):
        raise RuleError("Every line needs a destination bin before the transfer can be confirmed.", field="dest_bin_id")
    if transfer["status"] == "PENDING":
        _check_transfer_stock(database, transfer_id)
    _change_status(database, transfer_id, transfer["status"], "CONFIRMED", putaway)


def cancel_transfer(database: Database, transfer_id: int) -> None:
    transfer = _transfer(database, transfer_id)
    check_transition(transfer_id, transfer["status"], "CANCELLED")
    _change_status(database, transfer_id, transfer["status"], "CANCELLED", {})


def dispatch(
    database: Database, warehouse_id: int, destination: str, dispatch_date: date, lines: Sequence[Line]
) -> int:
    """Ship stock to a customer from bins of one warehouse."""
    if not destination.strip():
        raise RuleError("Destination is required.", field="destination")
    _require_lines(lines)
    _check_bins(database, lines, warehouse_id)
    check_stock(database, lines, respect_reservations=True)
    with database.transaction() as tx:
        (dispatch_id,) = db.insert_values(
            tx,
            schema.DISPATCH,
            {"warehouse_id": warehouse_id, "destination": destination.strip(), "dispatch_date": dispatch_date},
        )
        for line in lines:
            db.insert_values(
                tx,
                schema.DISPATCH_LINE,
                {"dispatch_id": dispatch_id, "bin_id": line.bin_id, "product_id": line.product_id, "quantity": line.quantity},
            )
    return int(dispatch_id)


def record_damage(
    database: Database, line: Line, damage_date: date, reason: str
) -> tuple[Any, ...]:
    """Write off damaged units from a bin (they leave usable stock)."""
    if not reason.strip():
        raise RuleError("Reason is required.", field="reason")
    check_stock(database, [line], respect_reservations=False)
    return db.insert_row(
        database,
        schema.DAMAGED,
        {
            "bin_id": line.bin_id,
            "product_id": line.product_id,
            "damage_date": damage_date,
            "quantity": line.quantity,
            "reason": reason.strip(),
        },
    )


# ---- transfer helpers ---------------------------------------------------------


def _transfer(database: Database, transfer_id: int) -> dict[str, Any]:
    transfer = db.header_row(database, "transfer", transfer_id)
    if transfer is None:
        raise RuleError(f"Transfer #{transfer_id} no longer exists.")
    return transfer


def _check_transfer_stock(database: Database, transfer_id: int) -> None:
    lines = [
        Line(row["source_bin_id"], row["product_id"], row["quantity"])
        for row in db.transfer_lines(database, transfer_id)
    ]
    _require_lines(lines)
    check_stock(database, lines, respect_reservations=True, exclude_transfer_id=transfer_id)


def _check_putaway(database: Database, transfer: dict[str, Any], putaway: PutAway) -> None:
    for index, ((source_bin_id, _product_id), dest_bin_id) in enumerate(putaway.items()):
        if dest_bin_id is None:
            continue
        if dest_bin_id == source_bin_id:
            raise RuleError("Destination bin must be different from the source bin.", field="dest_bin_id", line=index)
        check_bin_in_warehouse(
            database, dest_bin_id, transfer["dest_warehouse_id"], field="dest_bin_id", line=index, role="Destination bin"
        )


def _write_putaway(tx: db.Transaction, transfer_id: int, putaway: PutAway) -> None:
    for (source_bin_id, product_id), dest_bin_id in putaway.items():
        db.set_destination_bin(tx, transfer_id, source_bin_id, product_id, dest_bin_id)


def _change_status(database: Database, transfer_id: int, current: str, new: str, putaway: PutAway) -> None:
    with database.transaction() as tx:
        _write_putaway(tx, transfer_id, putaway)
        if not db.update_transfer_status(tx, transfer_id, new, current):
            raise RuleError(f"Transfer #{transfer_id} changed while you were working on it. Refresh and try again.")
