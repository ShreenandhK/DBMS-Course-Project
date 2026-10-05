"""Data access for stock_transfer_db.

Every SQL statement the application runs lives in this module. Values are always
bound as parameters; table and column identifiers come only from the fixed
definitions in ``stm.schema``.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

import mysql.connector
from mysql.connector import errorcode

Row = dict[str, Any]

CONNECT_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class ConnectionInfo:
    host: str
    port: int
    user: str
    database: str

    @property
    def label(self) -> str:
        return f"{self.user}@{self.host}:{self.port} / {self.database}"


class DbError(Exception):
    """A database failure, phrased for the person using the app.

    ``field`` names the column the error belongs to when one can be identified,
    so forms can show it next to the right input. ``detail`` keeps the raw
    MySQL text for the activity log.
    """

    def __init__(
        self, message: str, *, code: int | None = None, field: str | None = None, detail: str = ""
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.field = field
        self.detail = detail


@dataclass(frozen=True)
class StatementRecord:
    """One statement sent inside a write transaction, for the activity log."""

    sql: str
    params: tuple[Any, ...] = ()
    rowcount: int | None = None
    error: str | None = None
    at: datetime = field(default_factory=datetime.now)


StatementListener = Callable[[StatementRecord], None]


class Transaction:
    """Statement runner handed out by ``Database.transaction()``."""

    def __init__(self, connection: Any, emit: StatementListener) -> None:
        self._conn = connection
        self._emit = emit

    def execute(self, sql: str, params: Sequence[Any] = ()) -> tuple[int, int | None]:
        """Run one write statement; return (rows affected, last insert id)."""
        bound = tuple(params)
        cursor = self._conn.cursor()
        try:
            cursor.execute(sql, bound)
        except mysql.connector.Error as err:
            self._emit(StatementRecord(_compact(sql), bound, error=f"{err.errno}: {err.msg}"))
            raise
        finally:
            rowcount, last_id = cursor.rowcount, cursor.lastrowid
            cursor.close()
        self._emit(StatementRecord(_compact(sql), bound, rowcount))
        return rowcount, last_id

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[Row]:
        return _fetch_all(self._conn, sql, params)


class Database:
    """A single connection to the server, in autocommit mode for reads."""

    def __init__(self, info: ConnectionInfo, password: str) -> None:
        self.info = info
        self._conn = _open(info, password)
        self._listeners: list[StatementListener] = []
        self.server_version = ".".join(str(part) for part in self._conn.get_server_version())

    def add_listener(self, listener: StatementListener) -> None:
        self._listeners.append(listener)

    def close(self) -> None:
        try:
            self._conn.close()
        except mysql.connector.Error:
            pass

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[Row]:
        self._ensure_connected()
        try:
            return _fetch_all(self._conn, sql, params)
        except mysql.connector.Error as err:
            raise translate_error(err) from err

    @contextmanager
    def transaction(self) -> Iterator[Transaction]:
        """Run the block as one transaction: commit on success, roll back on any error."""
        self._ensure_connected()
        self._conn.start_transaction()
        self._emit(StatementRecord("START TRANSACTION"))
        try:
            yield Transaction(self._conn, self._emit)
            self._conn.commit()
            self._emit(StatementRecord("COMMIT"))
        except mysql.connector.Error as err:
            self._rollback()
            raise translate_error(err) from err
        except BaseException:
            self._rollback()
            raise

    def _rollback(self) -> None:
        try:
            self._conn.rollback()
        finally:
            self._emit(StatementRecord("ROLLBACK"))

    def _emit(self, record: StatementRecord) -> None:
        for listener in self._listeners:
            listener(record)

    def _ensure_connected(self) -> None:
        if self._conn.is_connected():
            return
        try:
            self._conn.reconnect(attempts=2, delay=1)
        except mysql.connector.Error as err:
            raise DbError("Lost the connection to the database server.", code=err.errno) from err


def _open(info: ConnectionInfo, password: str) -> Any:
    try:
        return mysql.connector.connect(
            host=info.host,
            port=info.port,
            user=info.user,
            password=password,
            database=info.database,
            autocommit=True,
            charset="utf8mb4",
            collation="utf8mb4_0900_ai_ci",
            connection_timeout=CONNECT_TIMEOUT_SECONDS,
        )
    except mysql.connector.Error as err:
        raise DbError(_connect_message(err, info), code=err.errno) from err


def _connect_message(err: mysql.connector.Error, info: ConnectionInfo) -> str:
    match err.errno:
        case errorcode.ER_ACCESS_DENIED_ERROR:
            return f"Access denied for user '{info.user}'. Check the user name and password."
        case errorcode.ER_DBACCESS_DENIED_ERROR:
            return f"User '{info.user}' has no access to database '{info.database}'."
        case errorcode.ER_BAD_DB_ERROR:
            return f"Database '{info.database}' does not exist on this server."
        case errorcode.CR_CONN_HOST_ERROR | errorcode.CR_CONNECTION_ERROR:
            return f"Cannot reach MySQL at {info.host}:{info.port}. Check that the server is running."
        case errorcode.CR_UNKNOWN_HOST:
            return f"Unknown host '{info.host}'."
        case _:
            return f"Could not connect: {err.msg}"


def _fetch_all(connection: Any, sql: str, params: Sequence[Any]) -> list[Row]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(sql, tuple(params))
        return [{key: _normalize(value) for key, value in row.items()} for row in cursor.fetchall()]
    finally:
        cursor.close()


def _normalize(value: Any) -> Any:
    # SUM() over INT columns comes back as DECIMAL; quantities are whole units.
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8")
    return value


def _compact(sql: str) -> str:
    return " ".join(sql.split())


# --- Error translation -------------------------------------------------------

_TABLE_NOUNS: dict[str, tuple[str, str]] = {
    "supplier": ("supplier", "suppliers"),
    "warehouse": ("warehouse", "warehouses"),
    "product": ("product", "products"),
    "zone": ("zone", "zones"),
    "bin": ("bin", "bins"),
    "receipt": ("receipt", "receipts"),
    "receipt_line": ("receipt line", "receipt lines"),
    "transfer": ("transfer", "transfers"),
    "transfer_line": ("transfer line", "transfer lines"),
    "dispatch": ("dispatch", "dispatches"),
    "dispatch_line": ("dispatch line", "dispatch lines"),
    "damaged": ("damage record", "damage records"),
}

# UNIQUE / PRIMARY KEY name as MySQL reports it -> (column, message).
_UNIQUE_KEYS: dict[str, tuple[str, str]] = {
    "supplier.uq_supplier_name": ("name", "A supplier with this name already exists."),
    "warehouse.uq_warehouse_name": ("name", "A warehouse with this name already exists."),
    "product.uq_product_sku": ("sku", "This SKU is already used by another product."),
    "zone.uq_zone_per_warehouse": ("zone_name", "This warehouse already has a zone with this name."),
    "bin.uq_bin_code": ("bin_code", "This bin code is already in use."),
    "receipt_line.PRIMARY": ("product_id", "This receipt already has a line for this bin and product."),
    "transfer_line.PRIMARY": (
        "product_id",
        "This transfer already has a line for this source bin and product.",
    ),
    "dispatch_line.PRIMARY": ("product_id", "This dispatch already has a line for this bin and product."),
    "damaged.PRIMARY": (
        "damage_date",
        "Damage for this bin and product is already recorded on this date.",
    ),
}

# CHECK constraint -> (column, rule in plain words).
_CHECKS: dict[str, tuple[str, str]] = {
    "chk_product_reorder": ("reorder_level", "Reorder level cannot be negative."),
    "chk_receipt_line_qty": ("quantity", "Received quantity must be greater than zero."),
    "chk_transfer_line_qty": ("quantity", "Transfer quantity must be greater than zero."),
    "chk_dispatch_line_qty": ("quantity", "Dispatched quantity must be greater than zero."),
    "chk_damaged_qty": ("quantity", "Damaged quantity must be greater than zero."),
    "chk_transfer_status": ("status", "Status must be PENDING, IN_TRANSIT, CONFIRMED or CANCELLED."),
    "chk_transfer_diff_warehouse": (
        "dest_warehouse_id",
        "Source and destination warehouse must be different.",
    ),
    "chk_transfer_line_bins": ("dest_bin_id", "Destination bin must be different from the source bin."),
}


def translate_error(err: mysql.connector.Error) -> DbError:
    """Turn a MySQL error into a DbError with a plain-language message."""
    code = err.errno
    raw = err.msg or str(err)
    detail = f"MySQL {code}: {raw}"
    match code:
        case errorcode.ER_DUP_ENTRY:
            column, message = _lookup(_UNIQUE_KEYS, r"for key '([\w.]+)'", raw, "This record already exists.")
        case errorcode.ER_ROW_IS_REFERENCED_2:
            column, message = None, _dependents_message(raw)
        case errorcode.ER_NO_REFERENCED_ROW_2:
            column, message = _missing_parent(raw)
        case errorcode.ER_CHECK_CONSTRAINT_VIOLATED:
            column, message = _lookup(_CHECKS, r"constraint '(\w+)'", raw, "A data rule was violated.")
        case errorcode.ER_SIGNAL_EXCEPTION:
            column, message = None, raw
        case errorcode.ER_BAD_NULL_ERROR:
            column, message = _column(raw), "This field is required."
        case errorcode.ER_DATA_TOO_LONG:
            column, message = _column(raw), "Too long for this field."
        case errorcode.ER_WARN_DATA_OUT_OF_RANGE | errorcode.ER_TRUNCATED_WRONG_VALUE_FOR_FIELD:
            column, message = _column(raw), "Value is not valid for this field."
        case errorcode.CR_SERVER_GONE_ERROR | errorcode.CR_SERVER_LOST:
            column, message = None, "Lost the connection to the database server."
        case _:
            column, message = None, raw
    return DbError(message, code=code, field=column, detail=detail)


def _lookup(
    table: dict[str, tuple[str, str]], pattern: str, raw: str, fallback: str
) -> tuple[str | None, str]:
    match = re.search(pattern, raw)
    if match and match.group(1) in table:
        return table[match.group(1)]
    return None, fallback


def _dependents_message(raw: str) -> str:
    match = re.search(r"fails \(`[^`]*`\.`(\w+)`", raw)
    child = _TABLE_NOUNS.get(match.group(1).lower(), ("", "other records"))[1] if match else "other records"
    return f"It is still referenced by {child}. Delete those {child} first."


def _missing_parent(raw: str) -> tuple[str | None, str]:
    match = re.search(r"FOREIGN KEY \(`(\w+)`\) REFERENCES `(\w+)`", raw)
    if not match:
        return None, "A referenced record does not exist."
    parent = _TABLE_NOUNS.get(match.group(2).lower(), (match.group(2), ""))[0]
    return match.group(1), f"The selected {parent} no longer exists. Refresh and try again."


def _column(raw: str) -> str | None:
    match = re.search(r"[Cc]olumn '(\w+)'", raw)
    return match.group(1) if match else None
