"""Insert form generated from a table's field definitions."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from stm import db, operations, theme
from stm.db import Database, DbError, Option
from stm.operations import RuleError
from stm.schema import MAX_INT, Field, Kind, TableSpec
from stm.widgets import Banner, button, field_error_label, hairline, label, set_style_property, show_field_error

NONE_LABEL = "— None —"


class FieldEditor:
    """Input widget for one field, plus its hint and inline error label."""

    def __init__(self, field: Field, options: list[Option] | None) -> None:
        self.field = field
        self.widget = self._create(options or [])
        self.error = field_error_label()

    def _create(self, options: list[Option]) -> QWidget:
        kind = self.field.kind
        if kind in (Kind.TEXT, Kind.CODE, Kind.INTEGER):
            return self._line_edit()
        if kind is Kind.DATE:
            editor = QDateEdit(QDate.currentDate())
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("yyyy-MM-dd")
            return editor
        combo = QComboBox()
        combo.setMaxVisibleItems(18)
        if kind is Kind.CHOICE:
            for choice in self.field.choices:
                combo.addItem(choice, choice)
            combo.setCurrentIndex(max(0, combo.findData(self.field.default)))
            return combo
        if not self.field.required:
            combo.addItem(NONE_LABEL, None)
        for option in options:
            combo.addItem(option.label, option.id)
        combo.setPlaceholderText(f"Select {self.field.label.lower()}…")
        combo.setCurrentIndex(0 if not self.field.required else -1)
        return combo

    def _line_edit(self) -> QLineEdit:
        editor = QLineEdit()
        if self.field.max_length:
            editor.setMaxLength(self.field.max_length)
        if self.field.default is not None:
            editor.setText(str(self.field.default))
        if self.field.kind is Kind.CODE:
            editor.setFont(theme.mono_font(10))
            editor.textEdited.connect(lambda text, e=editor: _keep_upper(e, text))
        return editor

    def on_change(self, slot: Callable[[], None]) -> None:
        widget = self.widget
        if isinstance(widget, QLineEdit):
            widget.textChanged.connect(slot)
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(slot)
        elif isinstance(widget, QDateEdit):
            widget.dateChanged.connect(slot)

    def set_error(self, message: str | None) -> None:
        show_field_error(self.error, message)
        set_style_property(self.widget, "invalid", bool(message))

    def read(self) -> tuple[Any, str | None]:
        """Return (value, error message) after validating the input."""
        widget = self.widget
        if isinstance(widget, QDateEdit):
            return widget.date().toPython(), None
        if isinstance(widget, QComboBox):
            value = widget.currentData() if widget.currentIndex() >= 0 else None
            if value is None and self.field.required:
                return None, f"Select a {self.field.label.lower()}."
            return value, None
        assert isinstance(widget, QLineEdit)
        text = widget.text().strip()
        if not text:
            return None, "Required." if self.field.required else None
        if self.field.kind is Kind.INTEGER:
            return parse_int(text, self.field.minimum)
        if self.field.max_length and len(text) > self.field.max_length:
            return None, f"At most {self.field.max_length} characters."
        return text, None


def _keep_upper(editor: QLineEdit, text: str) -> None:
    if text != text.upper():
        position = editor.cursorPosition()
        editor.setText(text.upper())
        editor.setCursorPosition(position)


def parse_int(text: str, minimum: int | None) -> tuple[int | None, str | None]:
    """Parse a whole number typed by the user; return (value, error message)."""
    try:
        value = int(text.replace(",", ""))
    except ValueError:
        return None, "Enter a whole number."
    if minimum == 1 and value < 1:
        return None, "Must be greater than zero."
    if minimum is not None and value < minimum:
        return None, "Cannot be negative." if minimum == 0 else f"Must be at least {minimum}."
    if value > MAX_INT:
        return None, "Too large."
    return value, None


class RecordDialog(QDialog):
    """Collects one new row for ``spec``, validates it and inserts it."""

    def __init__(self, database: Database, spec: TableSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = database
        self._spec = spec
        self.inserted_key: tuple[Any, ...] | None = None
        self.setWindowTitle(f"New {spec.singular}")
        self.setMinimumWidth(520)

        self._editors = [FieldEditor(f, self._options_for(f)) for f in spec.fields]
        self._banner = Banner()
        self._submit = button("Insert", "primary")
        self._submit.setDefault(True)
        self._cancel = button("Cancel")

        self._build_layout()
        self._submit.clicked.connect(self._on_submit)
        self._cancel.clicked.connect(self.reject)
        for editor in self._editors:
            editor.on_change(lambda *_signal_args, e=editor: self._clear_error(e))
        if self._editors:
            self._editors[0].widget.setFocus()

    def _options_for(self, field: Field) -> list[Option] | None:
        if field.kind is not Kind.REFERENCE or field.reference is None:
            return None
        try:
            return db.lookup(self._db, field.reference)
        except DbError:
            return []

    def _build_layout(self) -> None:
        header = QVBoxLayout()
        header.setSpacing(2)
        header.addWidget(label(f"New {self._spec.singular}", "dialogTitle"))
        subtitle = label(
            f"Inserts one row into table "
            f"<span style=\"font-family:'Cascadia Mono','Consolas'\">{self._spec.name}</span>",
            "muted",
        )
        subtitle.setTextFormat(Qt.TextFormat.RichText)
        header.addWidget(subtitle)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(4)
        form.setColumnMinimumWidth(0, 130)
        form.setColumnStretch(1, 1)
        row = 0
        for editor in self._editors:
            caption = label(editor.field.label + ("" if editor.field.required else "  (optional)"), "fieldLabel")
            form.addWidget(caption, row, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            form.addWidget(editor.widget, row, 1)
            row += 1
            notes = QVBoxLayout()
            notes.setSpacing(0)
            notes.setContentsMargins(0, 0, 0, 6)
            notes.addWidget(editor.error)
            if editor.field.hint:
                notes.addWidget(label(editor.field.hint, "fieldHint"))
            form.addLayout(notes, row, 1)
            row += 1

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._cancel)
        buttons.addWidget(self._submit)

        body = QVBoxLayout(self)
        body.setContentsMargins(22, 18, 22, 16)
        body.setSpacing(14)
        body.addLayout(header)
        body.addWidget(hairline())
        body.addLayout(form)
        body.addWidget(self._banner)
        body.addLayout(buttons)

    def _clear_error(self, editor: FieldEditor) -> None:
        editor.set_error(None)
        self._banner.clear()

    def _collect(self) -> dict[str, Any] | None:
        values: dict[str, Any] = {}
        valid = True
        for editor in self._editors:
            value, error = editor.read()
            editor.set_error(error)
            valid &= error is None
            if value is not None:
                values[editor.field.column] = value
        for rule in self._spec.distinct:
            first, second = values.get(rule.first), values.get(rule.second)
            if first is not None and first == second:
                self._editor(rule.second).set_error(rule.message)
                valid = False
        return values if valid else None

    def _editor(self, column: str) -> FieldEditor:
        return next(e for e in self._editors if e.field.column == column)

    def _on_submit(self) -> None:
        self._banner.clear()
        values = self._collect()
        if values is None:
            self._focus_first_error()
            return
        try:
            operations.check_insert(self._db, self._spec, values)
            self.inserted_key = db.insert_row(self._db, self._spec, values)
        except RuleError as err:
            self._show_error(err.message, err.field, "Business rule checked by the application")
            return
        except DbError as err:
            self._show_error(err.message, err.field, err.detail)
            return
        self.accept()

    def _show_error(self, message: str, column: str | None, detail: str) -> None:
        target = next((e for e in self._editors if e.field.column == column), None)
        if target is not None:
            target.set_error(message)
            target.widget.setFocus()
        else:
            self._banner.show_message(message, detail)

    def _focus_first_error(self) -> None:
        for editor in self._editors:
            if editor.error.text():
                editor.widget.setFocus()
                return
