"""Remembered login details.

Host, port, user and database go to per-user QSettings (the Windows registry).
The password, only when the user opts in, goes to the OS credential vault
(Windows Credential Manager) through ``keyring``. Nothing is written inside the
project folder, so nothing here can end up in version control.
"""
from __future__ import annotations

from dataclasses import dataclass

import keyring
from keyring.errors import KeyringError, PasswordDeleteError
from PySide6.QtCore import QSettings

from stm import APP_NAME, ORG_NAME
from stm.db import ConnectionInfo

KEYRING_SERVICE = "StockTransferManager"

DEFAULT_INFO = ConnectionInfo(host="localhost", port=3306, user="root", database="stock_transfer_db")


@dataclass(frozen=True)
class SavedLogin:
    info: ConnectionInfo
    password: str
    remember: bool


def load() -> SavedLogin:
    settings = _settings()
    info = ConnectionInfo(
        host=str(settings.value("host", DEFAULT_INFO.host)),
        port=_as_int(settings.value("port", DEFAULT_INFO.port), DEFAULT_INFO.port),
        user=str(settings.value("user", DEFAULT_INFO.user)),
        database=str(settings.value("database", DEFAULT_INFO.database)),
    )
    # Keep the box ticked even if the stored password has gone missing, so typing it once re-saves it.
    remember = str(settings.value("remember_password", "false")).lower() == "true"
    password = _read_password(info) if remember else None
    return SavedLogin(info, password or "", remember)


def save(info: ConnectionInfo, password: str, remember: bool) -> None:
    settings = _settings()
    settings.setValue("host", info.host)
    settings.setValue("port", info.port)
    settings.setValue("user", info.user)
    settings.setValue("database", info.database)
    stored = _write_password(info, password) if remember else False
    if not remember:
        _delete_password(info)
    settings.setValue("remember_password", "true" if stored else "false")


def _settings() -> QSettings:
    return QSettings(ORG_NAME, APP_NAME)


def _account(info: ConnectionInfo) -> str:
    return f"{info.user}@{info.host}:{info.port}"


def _read_password(info: ConnectionInfo) -> str | None:
    try:
        return keyring.get_password(KEYRING_SERVICE, _account(info))
    except KeyringError:
        return None


def _write_password(info: ConnectionInfo, password: str) -> bool:
    try:
        keyring.set_password(KEYRING_SERVICE, _account(info), password)
        return True
    except KeyringError:
        return False


def _delete_password(info: ConnectionInfo) -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, _account(info))
    except (PasswordDeleteError, KeyringError):
        pass


def _as_int(value: object, fallback: int) -> int:
    try:
        return int(str(value))
    except ValueError:
        return fallback
