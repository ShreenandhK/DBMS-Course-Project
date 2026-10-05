"""Application main window: sidebar navigation, table pages and status bar."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QStackedWidget, QWidget

from stm import APP_NAME, db, schema
from stm.activity_log import ActivityLog
from stm.db import Database, DbError
from stm.sidebar import Sidebar
from stm.table_page import TablePage

FIRST_PAGE = "transfer"


class MainWindow(QMainWindow):
    def __init__(self, database: Database) -> None:
        super().__init__()
        self._db = database
        self._pages: dict[str, TablePage] = {}
        self.setWindowTitle(APP_NAME)
        self.resize(1360, 820)

        self._sidebar = Sidebar()
        self._stack = QStackedWidget()
        self._connection_label = QLabel(f"{database.info.label}   ·   MySQL {database.server_version}")
        self._message_label = QLabel()
        self._count_label = QLabel()
        self._activity = ActivityLog(self)
        database.add_listener(self._activity.record)

        self._build_central()
        self._build_status_bar()
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._activity)
        self.resizeDocks([self._activity], [150], Qt.Orientation.Vertical)
        self._build_menu()
        self._sidebar.page_selected.connect(self._open_page)
        self.refresh_counts()
        self._sidebar.select(FIRST_PAGE)

    # ---- construction -----------------------------------------------------

    def _build_central(self) -> None:
        for group, specs in schema.grouped():
            self._sidebar.add_group(group, [(spec.name, spec.title) for spec in specs])
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._sidebar)
        layout.addWidget(self._stack, 1)
        self.setCentralWidget(central)

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)
        bar.addWidget(self._connection_label)
        bar.addWidget(self._message_label, 1)
        bar.addPermanentWidget(self._count_label)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self._action("E&xit", QKeySequence.StandardKey.Quit, self.close))

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self._action("&New record", QKeySequence.StandardKey.New, self._new_record))
        edit_menu.addAction(self._action("&Delete selected", QKeySequence(Qt.Key.Key_Delete), self._delete_selected))
        edit_menu.addSeparator()
        edit_menu.addAction(self._action("&Filter rows", QKeySequence.StandardKey.Find, self._focus_filter))

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self._action("&Refresh", QKeySequence(QKeySequence.StandardKey.Refresh), self.refresh))
        activity = self._activity.toggleViewAction()
        activity.setText("SQL &activity")
        activity.setShortcut(QKeySequence("Ctrl+L"))
        view_menu.addAction(activity)

    def _action(self, text: str, shortcut: QKeySequence | QKeySequence.StandardKey, slot: object) -> QAction:
        action = QAction(text, self)
        action.setShortcut(shortcut)
        action.triggered.connect(slot)
        return action

    # ---- navigation -------------------------------------------------------

    def _open_page(self, name: str) -> None:
        page = self._pages.get(name) or self._create_page(name)
        self._stack.setCurrentWidget(page)
        page.reload()
        page.focus_grid()

    def _create_page(self, name: str) -> TablePage:
        page = TablePage(self._db, schema.BY_NAME[name])
        page.counts_changed.connect(lambda visible, total, p=page: self._show_counts(p, visible, total))
        page.message.connect(self.show_message)
        page.data_changed.connect(self._after_change)
        self._pages[name] = page
        self._stack.addWidget(page)
        return page

    def _current_page(self) -> TablePage | None:
        widget = self._stack.currentWidget()
        return widget if isinstance(widget, TablePage) else None

    # ---- actions ----------------------------------------------------------

    def refresh(self) -> None:
        page = self._current_page()
        if page is not None and page.reload():
            self.show_message(f"Reloaded {page.spec.title.lower()} from the database.")
        self.refresh_counts()

    def refresh_counts(self) -> None:
        try:
            self._sidebar.set_counts(db.row_counts(self._db))
        except DbError as err:
            self.show_message(f"Could not read row counts: {err.message}")

    def _after_change(self) -> None:
        self.refresh_counts()

    def _new_record(self) -> None:
        page = self._current_page()
        if page is not None:
            page.new_record()

    def _delete_selected(self) -> None:
        page = self._current_page()
        if page is not None:
            page.delete_selected()

    def _focus_filter(self) -> None:
        page = self._current_page()
        if page is not None:
            page.focus_filter()

    # ---- status bar -------------------------------------------------------

    def show_message(self, text: str) -> None:
        self._message_label.setText(text)

    def _show_counts(self, page: TablePage, visible: int, total: int) -> None:
        if page is not self._current_page():
            return
        noun = "row" if total == 1 else "rows"
        text = f"{total:,} {noun}" if visible == total else f"{visible:,} of {total:,} {noun}"
        self._count_label.setText(text)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._db.close()
        super().closeEvent(event)
