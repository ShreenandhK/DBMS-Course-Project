"""CSV export of what a grid currently shows."""
from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QFileDialog, QWidget

from stm.schema import GridColumn, Row


def _cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    return value


def write_csv(path: Path, columns: Sequence[GridColumn], rows: Iterable[Row]) -> int:
    """Write rows with raw (unformatted) values; UTF-8 with BOM so Excel reads it correctly."""
    count = 0
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([column.label for column in columns])
        for row in rows:
            writer.writerow([_cell(row.get(column.key)) for column in columns])
            count += 1
    return count


def ask_path(parent: QWidget, name: str) -> Path | None:
    folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    suggested = str(Path(folder) / f"{name}_{date.today().isoformat()}.csv")
    chosen, _ = QFileDialog.getSaveFileName(parent, "Export CSV", suggested, "CSV files (*.csv)")
    return Path(chosen) if chosen else None
