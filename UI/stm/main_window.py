"""Application main window: sidebar navigation, pages, SQL activity panel and status bar."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QGuiApplication, QKeySequence
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QSplitter, QStackedWidget, QWidget

from stm import APP_NAME, db, schema
from stm.activity_log import ActivityLog
from stm.db import Database, DbError
from stm.page import Page
from stm.reports_page import ReportsPage
from stm.sidebar import Sidebar
from stm.table_page import TablePage
from stm.workflows import WORKFLOWS

OPERATIONS = (*WORKFLOWS, ("reports", "Reports", ReportsPage))
FIRST_PAGE = "v_bin_stock"
ACTIVITY_HEIGHT = 150


class MainWindow(QMainWindow):
    def __init__(self, database: Database) -> None:
        super().__init__()
        self._db = database
        self._pages: dict[str, Page] = {}
        self._factories: dict[str, Callable[[], Page]] = self._page_factories()
        self.setWindowTitle(APP_NAME)
        available = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(min(1360, int(available.width() * 0.92)), min(820, int(available.height() * 0.9)))

        self._sidebar = Sidebar()
        self._stack = QStackedWidget()
        self._activity = ActivityLog()
        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._connection_label = QLabel(f"{database.info.label}   ·   MySQL {database.server_version}")
        self._message_label = QLabel()
        self._count_label = QLabel()
        database.add_listener(self._activity.record)

        self._build_central()
        self._build_status_bar()
        self._build_menu()
        self._sidebar.page_selected.connect(self._open_page)
        self.refresh_counts()
        self._sidebar.select(FIRST_PAGE)

    # ---- construction -----------------------------------------------------

    def _page_factories(self) -> dict[str, Callable[[], Page]]:
        factories: dict[str, Callable[[], Page]] = {
            key: (lambda factory=factory: factory(self._db)) for key, _label, factory in OPERATIONS
        }
        for spec in schema.TABLES:
            factories[spec.name] = lambda spec=spec: TablePage(self._db, spec)
        return factories

    def _build_central(self) -> None:
        self._sidebar.add_group("Operations", [(key, title) for key, title, _factory in OPERATIONS])
        for group, specs in schema.grouped():
            self._sidebar.add_group(group, [(spec.name, spec.title) for spec in specs])

        self._splitter.addWidget(self._stack)
        self._splitter.addWidget(self._activity)
        self._splitter.setCollapsible(0, False)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setSizes([10_000, ACTIVITY_HEIGHT])

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._sidebar)
        layout.addWidget(self._splitter, 1)
        self.setCentralWidget(central)

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)
        bar.addWidget(self._connection_label)
        bar.addWidget(self._message_label, 1)
        bar.addPermanentWidget(self._count_label)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self._action("&Export CSV…", QKeySequence("Ctrl+E"), self._export_csv))
        file_menu.addSeparator()
        file_menu.addAction(self._action("E&xit", QKeySequence.StandardKey.Quit, self.close))

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self._action("&New record", QKeySequence.StandardKey.New, self._new_record))
        edit_menu.addAction(self._action("&Delete selected", QKeySequence(Qt.Key.Key_Delete), self._delete_selected))
        edit_menu.addSeparator()
        edit_menu.addAction(self._action("&Filter rows", QKeySequence.StandardKey.Find, self._focus_filter))

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self._action("&Refresh", QKeySequence(QKeySequence.StandardKey.Refresh), self.refresh))
        activity = self._action("SQL &activity", QKeySequence("Ctrl+L"), self._toggle_activity)
        activity.setCheckable(True)
        activity.setChecked(True)
        self._activity_action = activity
        view_menu.addAction(activity)

    def _action(self, text: str, shortcut: QKeySequence | QKeySequence.StandardKey, slot: Callable[[], None]) -> QAction:
        action = QAction(text, self)
        action.setShortcut(shortcut)
        action.triggered.connect(slot)
        return action

    # ---- navigation -------------------------------------------------------

    def open_page(self, key: str) -> None:
        self._sidebar.select(key)

    def _open_page(self, key: str) -> None:
        page = self._pages.get(key)
        if page is None:
            page = self._create_page(key)
        self._stack.setCurrentWidget(page)
        if not page.shows_counts:
            self._count_label.clear()
        page.activate()
        page.focus_main()

    def _create_page(self, key: str) -> Page:
        page = self._factories[key]()
        page.counts_changed.connect(lambda visible, total, p=page: self._show_counts(p, visible, total))
        page.message.connect(self.show_message)
        page.data_changed.connect(self.refresh_counts)
        self._pages[key] = page
        self._stack.addWidget(page)
        return page

    def _current_page(self) -> Page | None:
        widget = self._stack.currentWidget()
        return widget if isinstance(widget, Page) else None

    # ---- actions ----------------------------------------------------------

    def refresh(self) -> None:
        page = self._current_page()
        if page is not None and page.refresh():
            self.show_message(f"Reloaded {page.title.lower()} from the database.")
        self.refresh_counts()

    def refresh_counts(self) -> None:
        try:
            self._sidebar.set_counts(db.row_counts(self._db))
        except DbError as err:
            self.show_message(f"Could not read row counts: {err.message}")

    def _new_record(self) -> None:
        if (page := self._current_page()) is not None:
            page.new_record()

    def _delete_selected(self) -> None:
        if (page := self._current_page()) is not None:
            page.delete_selected()

    def _export_csv(self) -> None:
        if (page := self._current_page()) is not None:
            page.export_csv()

    def _focus_filter(self) -> None:
        if (page := self._current_page()) is not None:
            page.focus_filter()

    def _toggle_activity(self) -> None:
        self._activity.setVisible(self._activity_action.isChecked())

    # ---- status bar -------------------------------------------------------

    def show_message(self, text: str) -> None:
        self._message_label.setText(text)

    def _show_counts(self, page: Page, visible: int, total: int) -> None:
        if page is not self._current_page():
            return
        noun = "row" if total == 1 else "rows"
        text = f"{total:,} {noun}" if visible == total else f"{visible:,} of {total:,} {noun}"
        self._count_label.setText(text)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._db.close()
        super().closeEvent(event)
