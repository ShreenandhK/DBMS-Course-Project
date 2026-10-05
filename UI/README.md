# Stock Transfer Manager — Technical Documentation

Desktop client for the `stock_transfer_db` MySQL database (Multi-Warehouse Stock Transfer
Management System). It provides read access to all 12 tables and the `v_bin_stock` view,
schema-driven insert and delete, transactional stock workflows, application-level business rules
that the schema does not enforce, analytical reports and CSV export.

| | |
|---|---|
| Language | Python 3.12+ (developed and tested on 3.14) |
| UI toolkit | PySide6-Essentials 6.11.2 (Qt 6), Fusion style |
| Database driver | mysql-connector-python 26.7.0 (C extension) |
| Credential storage | keyring 25.7.0 (Windows Credential Manager backend) |
| Database | MySQL Community Server 8.0, schema `stock_transfer_db` (`../stock_transfer_db.sql`) |
| Platform | Windows 10/11 |

## 1. Setup and run

Create the virtual environment and install the pinned dependencies (PowerShell, repository root):

```powershell
py -3 -m venv UI\venv
.\UI\venv\Scripts\python.exe -m pip install -r UI\requirements.txt
```

Run from the repository root:

```powershell
.\UI\venv\Scripts\python.exe .\UI\main.py
```

or from inside `UI`:

```powershell
.\venv\Scripts\python.exe .\main.py
```

`main.py` resolves the stylesheet and assets relative to its own location, so the working
directory does not matter; only the script path must be correct.

### One-click launcher

`Start Stock Transfer Manager.cmd` (repository root) runs `UI\launch.ps1` with
`-ExecutionPolicy Bypass`. The script is idempotent and ASCII-only (Windows PowerShell 5.1 reads
BOM-less files as ANSI):

| Step | Behaviour |
|---|---|
| Python | Imports `PySide6.QtWidgets`, `mysql.connector`, `keyring` from `UI\venv`; if the interpreter is missing or broken, recreates the venv with `py -3 -m venv --clear` (Python ≥ 3.12 required); if packages are missing, reinstalls `requirements.txt`. pip failures are classified (path too long / WinError 206, no network, other) |
| Target | Host and port from the app's saved settings (`HKCU\Software\StockTransfer\Stock Transfer Manager`), else `localhost:3306`; overridable with `-HostName` / `-Port` |
| Service | For a local host only: finds `MySQL80` (or the first `MySQL*` service, or `-ServiceName`); refuses with guidance if *Disabled*; starts it if *Stopped*/*Paused*, elevating through UAC only when `Start-Service` is denied; waits for *Running* |
| Port | Polls a TCP connect until it succeeds or `-WaitSeconds` (default 90) elapses |
| Database | If the `mysql` client and login path (`-LoginPath`, default `local`) work, checks `information_schema.schemata`; offers to `source stock_transfer_db.sql` when the schema is missing |
| Running copy | Detects `python*.exe` processes whose command line contains `UI\main.py` and asks before starting another |
| Start | Starts `pythonw.exe main.py` (no console); if it exits within 3 s, re-runs it with `python.exe` and prints the last lines of output |

Switches: `-CheckOnly` (all checks, no start), `-NoPause` (never wait for input, for automation).
Log: `%LOCALAPPDATA%\StockTransferManager\launcher.log`. Exit code 0 on success, 1 on any failure.

`requirements.txt` pins every package, including transitive dependencies, to the versions above.

## 2. Architecture

```
main.py ── LoginDialog ── credentials.py (Credential Manager, QSettings)
   │
MainWindow ── Sidebar · ActivityLog · status bar · menus/shortcuts
   │  pages (Page subclasses, created lazily, refreshed on every activation)
   ├── TablePage ×13 ── RecordDialog (insert) · ConfirmDeleteDialog
   ├── workflows/ ×6  ── receive · new transfer · process transfers · dispatch · damage · bin search
   └── ReportsPage    ── 6 report grids · CSV export
          │                                   │
   operations.py (workflows, business rules)  schema.py / reports.py (metadata)
          │                                   │
        db.py (every SQL statement, connection, transactions, error translation)
          │
   mysql-connector-python ── MySQL 8.0 · stock_transfer_db
```

### Layering rules

| Module | May contain | Must not contain |
|---|---|---|
| `db.py` | All SQL text, connection handling, transactions, MySQL error translation | Qt widgets, business rules |
| `schema.py`, `reports.py` | Table/report metadata: columns, form fields, keys, display formats | SQL, Qt |
| `operations.py` | Business rules and multi-statement workflows built on `db.py` functions | SQL, Qt |
| Widgets (`*_page.py`, `workflows/`, dialogs) | Layout and interaction; call `db` read functions and `operations`/`db` write functions | SQL |

Identifiers that cannot be bound as parameters (table and column names in generic INSERT/DELETE)
come only from the `TableSpec` definitions in `schema.py`; `db.insert_values` rejects any column
not declared as a form field of that table.

### Module reference

| Module | Responsibility |
|---|---|
| `main.py` | Creates `QApplication` (Fusion, forced light palette, application font, stylesheet), runs the login dialog, opens the main window maximized |
| `launch.ps1` | One-click start-up checks and repairs (section 1) |
| `stm/db.py` | `Database` (single connection), `Transaction`, statement listeners, list/lookup/count queries, stock queries, report queries, generic insert/delete, transfer updates, error translation |
| `stm/schema.py` | `TableSpec` per table: grid columns (`GridColumn`, `Style`), insert fields (`Field`, `Kind`), primary key, record description, distinct-value rules |
| `stm/operations.py` | Business rules (`check_insert`, `check_stock`, `check_bin_in_warehouse`, `check_transition`) and workflows (`receive`, `create_transfer`, `ship_transfer`, `save_putaway`, `confirm_transfer`, `cancel_transfer`, `dispatch`, `record_damage`) |
| `stm/reports.py` | `ReportSpec` per report: columns, row key, summary line |
| `stm/credentials.py` | Load/save connection settings and the optional remembered password |
| `stm/login_dialog.py` | Connection dialog; stays open with a translated message on failure |
| `stm/main_window.py` | Sidebar, page creation, splitter with the SQL activity panel, menus, shortcuts, status bar |
| `stm/navigation.py` | Page catalogue (`PAGES`: key → title, description, factory) and sidebar grouping (`GROUPS`); single source for sidebar labels, tooltips and the quick guide |
| `stm/quick_guide.py` | F1 dialog generated from `navigation` plus fixed text on stock, transfer states and shortcuts |
| `stm/page.py` | `Page` base class (hooks: `activate`, `refresh`, `new_record`, `delete_selected`, `focus_filter`, `export_csv`) and the shared page header (title, plain-language subtitle, technical detail line) |
| `stm/table_page.py` | Grid, filter, insert, delete, export for one table or the view |
| `stm/grid.py` | `DataGrid`: read-only `QTableView` over row dicts with sorting, filtering, selection by key, column fitting, column totals |
| `stm/table_model.py` | `RecordModel` (display/sort/alignment/font roles), `RecordFilterProxy`, `StatusChipDelegate` |
| `stm/record_dialog.py` | Insert form generated from `Field` definitions, client validation, rule and database error placement |
| `stm/dialogs.py` | Delete confirmation (with cascade preview), question and error dialogs |
| `stm/workflows/` | Workflow pages and their shared building blocks (`WorkflowPage`, `FormGrid`, `LineEditor`) |
| `stm/reports_page.py` | Tabbed report page |
| `stm/export.py` | CSV writer and save dialog |
| `stm/activity_log.py` | Panel that renders `StatementRecord`s |
| `stm/sidebar.py` | Grouped navigation list with painted row counts |
| `stm/theme.py`, `style.qss` | Fonts, painted colours, the single application stylesheet |

## 3. Data access

### Connection

One `mysql.connector` connection per session, opened with `autocommit=True`, `utf8mb4` /
`utf8mb4_0900_ai_ci` and a 10-second connection timeout. Autocommit makes every read see the
latest committed data, so a refresh reflects changes made by other clients (for example the
MySQL command line). Before each operation the connection is checked with `is_connected()` and,
if the server dropped it, re-established (up to two attempts).

Rows are fetched as dictionaries. `DECIMAL` results of `SUM()` over `INT` columns are normalised
to `int`, so quantities format and sort as integers.

### Transactions

All writes go through `Database.transaction()`:

```python
with database.transaction() as tx:      # START TRANSACTION
    tx.execute(sql, params)             # one or more statements
                                        # COMMIT on normal exit, ROLLBACK on any exception
```

`Transaction.execute` returns `(rowcount, lastrowid)`. Every statement, its bound values, its
row count or error, and the surrounding `START TRANSACTION` / `COMMIT` / `ROLLBACK` are emitted
as `StatementRecord`s to registered listeners; the SQL activity panel is one such listener.

| Operation | Statements, executed in one transaction |
|---|---|
| Insert (table page) | `INSERT INTO <table> (<declared columns>) VALUES (%s, …)` |
| Delete (table page) | `DELETE FROM <table> WHERE <pk1> = %s AND …`, once per selected row; all or nothing |
| Receive stock | `INSERT receipt`; `INSERT receipt_line` × n |
| New transfer | `INSERT transfer` (status `PENDING`); `INSERT transfer_line` × n |
| Save put-away bins | `UPDATE transfer_line SET dest_bin_id = %s WHERE <pk>` × n |
| Mark in transit | `UPDATE transfer SET status = 'IN_TRANSIT' WHERE transfer_id = %s AND status = 'PENDING'` |
| Confirm transfer | `UPDATE transfer_line SET dest_bin_id …` × n; `UPDATE transfer SET status = 'CONFIRMED' WHERE transfer_id = %s AND status = <current>` |
| Cancel transfer | `UPDATE transfer SET status = 'CANCELLED' WHERE transfer_id = %s AND status = <current>` |
| Dispatch stock | `INSERT dispatch`; `INSERT dispatch_line` × n |
| Record damage | `INSERT damaged` |

Status updates are conditional on the status the user saw (`AND status = <current>`). A row count
of 0 means another session changed the transfer; the transaction is rolled back and the user is
told to refresh. This gives optimistic concurrency without row locks held across user think-time.

### Read queries

| Function | Purpose and technique |
|---|---|
| `list_rows` | One query per table; joins replace foreign-key IDs with names (warehouse, zone, bin code, SKU); `transfer_line` joins `bin` twice (`LEFT JOIN` for the nullable destination) |
| `row_counts` | One statement of scalar subqueries: `COUNT(*)` per table, the view, and open transfers |
| `lookup` | Dropdown options per foreign key; labels formatted in Python; extra columns (for example a bin's `warehouse_id`) kept for filtering |
| `stock_position` | On hand for one bin/product from `v_bin_stock`, and quantity reserved by `PENDING` transfers (optionally excluding one transfer) |
| `stock_in_warehouse` | Bin/product balances in a warehouse joined to a derived table of reservations; source for pick lists |
| `open_transfers` | `PENDING`/`IN_TRANSIT` transfers with line count, units and lines without a destination bin (`GROUP BY` with conditional `SUM`) |
| `search_bins` | `bin ⨝ zone ⨝ warehouse` `LEFT JOIN v_bin_stock` and reservations; `LIKE` patterns built from escaped user input |
| `run_report` | The six report queries (section 6) |

All values are bound with `%s` placeholders. User text used in `LIKE` has `\`, `%` and `_`
escaped before it is bound.

## 4. Error handling

`translate_error` converts `mysql.connector.Error` into `DbError(message, code, field, detail)`.
`field` names the form column the error belongs to, so forms show the message under the right
input; `detail` keeps the raw server text, which also appears in the SQL activity panel.

| MySQL error | Translation | Source of the mapping |
|---|---|---|
| 1062 duplicate key | Plain sentence per unique/primary key, attached to the relevant field | `_UNIQUE_KEYS`, keyed by `table.key` as reported by MySQL 8 (e.g. `supplier.uq_supplier_name`) |
| 1451 row is referenced | "It is still referenced by receipts. Delete those receipts first." | Child table parsed from the constraint text, mapped to a plural noun |
| 1452 parent missing | "The selected warehouse no longer exists. Refresh and try again." attached to the FK column | FK column and parent table parsed from the constraint text |
| 3819 CHECK violated | The rule in plain words, attached to the field (e.g. `chk_transfer_diff_warehouse` → destination warehouse) | `_CHECKS`, one entry per CHECK constraint in the schema |
| 1644 trigger SIGNAL | The trigger's `MESSAGE_TEXT` unchanged | Raw message |
| 1048 / 1406 / 1264 / 1366 | Required / too long / out of range, attached to the column | Column parsed from the message |
| 2006 / 2013 | "Lost the connection to the database server." | — |

For multi-row deletes the error also carries `row_index`, so the message names the record that
was refused; the whole transaction is rolled back.

Connection failures in the login dialog are translated separately (1045 access denied, 1044 no
database access, 1049 unknown database, 2002/2003 server unreachable, 2005 unknown host).

## 5. Stock model and business rules

### Stock quantities

There is no balance table. Quantities are derived:

| Quantity | Definition |
|---|---|
| On hand | `v_bin_stock.on_hand` = received + confirmed transfers in − (in-transit and confirmed) transfers out − dispatched − damaged |
| Reserved | Sum of `transfer_line.quantity` on `PENDING` transfers from that source bin and product; still counted in on hand |
| Available | On hand − reserved |
| In transit | Lines of `IN_TRANSIT` transfers; counted in no bin |

### Rules enforced by the application

These rules are listed as not enforced by the schema (knowledge file, section 7).
`operations.py` checks them in the workflows and, through `check_insert`, in the generic insert
forms of the line tables.

| Rule | Applies to | Check |
|---|---|---|
| Bin belongs to the document's warehouse | receipt lines, dispatch lines, transfer source bins; destination bins against the destination warehouse | `bin ⨝ zone` warehouse compared with the header's warehouse |
| Quantity within available stock | transfers, dispatches | Sum of requested quantity per bin/product (lines are aggregated) ≤ on hand − reserved |
| Quantity within on-hand stock | damage | Requested ≤ on hand |
| Forward-only status | transfers | Allowed transitions below; `CONFIRMED` and `CANCELLED` are final |
| Destination bins before confirming | transfers | Every line has a `dest_bin_id`; also enforced in the database by `trg_transfer_confirm_bu` |
| Destination bin ≠ source bin | transfers | Also enforced in the database by `chk_transfer_line_bins` |
| Deletes never leave negative stock | receipts, receipt lines, transfers, transfer lines | `check_delete` computes the on-hand change per bin/product that removing the records would cause (receipt lines −qty; IN_TRANSIT/CONFIRMED lines +qty at the source; CONFIRMED lines −qty at the destination) and refuses if any bin would drop below zero. Checked before the confirmation dialog. Deleting dispatches or damage only adds stock and is not checked |

Transfer state machine (`operations.ALLOWED_TRANSITIONS`):

| From | Allowed to |
|---|---|
| PENDING | IN_TRANSIT, CONFIRMED, CANCELLED |
| IN_TRANSIT | CONFIRMED, CANCELLED |
| CONFIRMED | — |
| CANCELLED | — |

When a transfer leaves `PENDING` (ship or confirm), its own lines are excluded from the reservation
total and the stock is re-checked, because other movements may have happened since it was created.

Rule violations raise `RuleError(message, field, line)`; the UI places the message on the field
or highlights the offending line. Checks run immediately before the write transaction; the write
itself is atomic.

## 6. Reports

Each report is a single read-only query in `db._REPORT_SQL` with a matching `ReportSpec` in
`reports.py`. Reports are re-run when their tab is opened and on F5.

| Report | Query outline |
|---|---|
| Warehouse stock | `v_bin_stock` `LEFT JOIN` reservations derived table; `GROUP BY` warehouse, product; on hand, reserved, available |
| Pending and in transit | `transfer ⨝ transfer_line ⨝ warehouse ×2 ⨝ bin` (`LEFT JOIN` destination bin) for `PENDING`/`IN_TRANSIT`; age = `DATEDIFF(CURDATE(), transfer_date)` |
| Bin utilization | `bin ⨝ zone ⨝ warehouse` `LEFT JOIN` a derived table of bins with `SUM(on_hand) > 0`; per zone: bins, occupied, empty, occupied % (no capacity column exists) |
| Stock ageing | Inbound movements (`receipt_line ⨝ receipt` `UNION ALL` confirmed `transfer_line`) aggregated to first/last inbound date per bin/product, joined to stocked rows of `v_bin_stock`; age bands via `CASE` |
| Damaged stock | `damaged ⨝ bin ⨝ zone ⨝ warehouse ⨝ product` grouped by warehouse and product; `GROUP_CONCAT` of bins; damage % against inbound units from `v_bin_stock` |
| Reorder needs | `product` `LEFT JOIN` on-hand totals and in-transit totals; shortfall = `GREATEST(reorder_level − total, 0)`; status `REORDER`/`OK` |

All queries are valid under `ONLY_FULL_GROUP_BY`. CSV export (`export.write_csv`) writes the rows
currently visible in the grid, in display order, with raw values (unformatted numbers, ISO dates),
encoded as UTF-8 with BOM for spreadsheet compatibility.

## 7. User interface implementation

- **Navigation.** `navigation.GROUPS` orders the sidebar from everyday work to setup: *Tasks*
  (receive, new transfer, process transfers, dispatch, damage), *Look up* (bin stock, bin search,
  reports), *Movement records* (the document tables), *Locations*, *Products & suppliers*. Every
  entry and heading carries a one-line tooltip from its `PageEntry.description` /
  `TableSpec.description`; F1 opens a quick guide generated from the same data.
- **Pages.** Pages are created on first use from `navigation.PAGES` and `activate()` is called on
  every visit, so data is never stale after changes made elsewhere. `data_changed` from any page
  refreshes the sidebar counts. Page headers show a plain-language purpose line and a smaller
  detail line (task steps, or table name and key). Task pages keep the error banner and action
  buttons in a fixed bar below the scrollable form, so they are always visible.
- **Grids.** `DataGrid` wraps `RecordModel` + `RecordFilterProxy`. The model returns formatted
  text for `DisplayRole` and raw values for a custom sort role, so numbers and dates sort
  correctly; alignment and monospace font are driven by the column `Style`. The proxy filters with
  an escaped, case-insensitive regular expression over one or all columns. Selection is restored
  by primary key after every reload, and newly inserted rows are selected and scrolled into view.
  An empty grid paints an explanatory message (`DataGrid.empty_text`, or "No rows match the
  filter." when a filter hides every row).
- **Forms.** `RecordDialog` builds one editor per `Field`: line edit (text, code, integer), date
  edit, choice combo or foreign-key combo (with a "None" entry for nullable keys). Validation order:
  client checks (required, length, integer range, distinct pairs) → business rules
  (`operations.check_insert`) → database; each error is shown on its field or in a banner.
- **Delete.** Before confirming, `cascade_counts` reports the child rows that `ON DELETE CASCADE`
  will remove (warehouse → zones → bins, zone → bins, header → lines).
- **Styling.** One stylesheet (`style.qss`) on the Fusion style with an explicit light palette.
  `@ASSETS@` in the stylesheet is replaced at load time with the absolute path of `assets/`.
  Colours painted in code (status labels, sidebar) live in `theme.py`. Fonts: Segoe UI Variable
  Text / Segoe UI for text, Cascadia Mono / Consolas for codes and identifiers.
- **Keyboard.** Ctrl+N new record, Del delete selection, Ctrl+F filter (Esc clears), F5 refresh,
  Ctrl+E export CSV, Ctrl+L toggle the SQL activity panel. Window-level shortcuts do not steal keys
  from text inputs (Delete inside a filter box edits the text).

## 8. Credentials and settings

| Item | Storage |
|---|---|
| Host, port, user, database | `QSettings` → `HKEY_CURRENT_USER\Software\StockTransfer\Stock Transfer Manager` |
| Password (only when "Remember password" is ticked) | Windows Credential Manager, generic credential `StockTransferManager`, account `user@host:port`, via `keyring` |

Nothing is written inside the project directory, so no credential can be committed. Unticking
the option and connecting deletes the stored password. If the option is on but the stored
password has been removed outside the app, the box stays ticked and the password field is empty,
so typing it once stores it again. The application never logs credentials.

## 9. Known limitations

- Business-rule checks run before the write transaction without row locks, so two clients
  writing at the same moment could both pass a stock check. Moving the rules into triggers (open
  work item in the knowledge file, section 10) would close this window.
- Transfer status transitions are enforced by the application only; direct SQL can still set any
  status allowed by `chk_transfer_status`.
- Master data is insert/delete only; the only updates are transfer status and put-away bins.
- Bins have no capacity attribute, so utilization is the share of occupied bins.
- The trigger bodies reference `Transfer` / `Transfer_Line` in mixed case; the server must run
  with `lower_case_table_names = 1` (the Windows default).
- All queries run synchronously on the UI thread over one connection; adequate for this data
  volume.

## 10. Extending

- **New table:** add a `TableSpec` to `schema.py` (grid columns, fields, primary key, description)
  and include it in `TABLES`; add its list query to `db._LIST_SQL` and its count to `_COUNT_SQL`;
  add foreign-key lookups to `_LOOKUP_SQL` / `_LOOKUP_LABELS`, and unique-key and CHECK
  messages to `_UNIQUE_KEYS` / `_CHECKS`.
- **New report:** add the query to `db._REPORT_SQL` and a `ReportSpec` to `reports.REPORTS`.
- **New workflow:** implement the operation in `operations.py` using `db` functions inside one
  `Database.transaction()`, add a page under `workflows/`, and register it in `workflows.WORKFLOWS`.

## 11. Verification

Every feature was exercised against the live database by scripts that drive the real widgets
(dialogs, grids, shortcuts) and compare results with values computed independently from the
sample data. Test rows were inserted and deleted by the tests themselves, auto-increment counters
were reset afterwards, and a `mysqldump` of schema, data, triggers and view taken before testing
was compared with one taken after: identical.
