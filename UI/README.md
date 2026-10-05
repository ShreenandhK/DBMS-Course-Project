# Stock Transfer Manager

Desktop client for the `stock_transfer_db` MySQL database (Multi-Warehouse Stock Transfer
Management System). It lists every table and the `v_bin_stock` view, inserts and deletes rows
through generated forms, and shows every write statement it sends to the server.

Built with Python 3, PySide6 (Qt 6) and mysql-connector-python.

## Requirements

- Windows 10 or 11
- Python 3.12 or newer (developed on 3.14)
- MySQL Server 8.0 with `stock_transfer_db` loaded from `../stock_transfer_db.sql`

## Setup

From the repository root:

```bash
cd UI
py -3 -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
```

## Run

```bash
venv\Scripts\python main.py
```

The login dialog is prefilled with `localhost`, `3306`, `root` and `stock_transfer_db`. Enter the
MySQL password and press **Connect**. A failed connection shows the reason (wrong password,
server not running, unknown database) and keeps the dialog open.

**Remember password on this computer** stores the password in Windows Credential Manager as the
generic credential `StockTransferManager`. Host, port, user and database are saved under
`HKEY_CURRENT_USER\Software\StockTransfer`. Nothing is written inside the project folder. To
forget the password, untick the box and connect once, or remove the credential in Credential
Manager.

## Using the app

| Area | What it does |
|---|---|
| Sidebar | Operations (workflows), then all 12 tables and the **Bin stock** view, grouped by area, with live row counts |
| Grid | Click a header to sort (third click restores database order). Foreign keys show names, codes and SKUs instead of IDs |
| Filter | Text filter over all columns or one chosen column; the status bar shows `visible of total` rows |
| New | Form generated from the table definition. Foreign keys are dropdowns; inputs are checked before anything is sent |
| Delete | Deletes the selected rows in one transaction after a confirmation that names each record and lists cascaded child rows |
| SQL activity | Bottom panel listing each `START TRANSACTION`, `INSERT`/`UPDATE`/`DELETE` with its values, rows affected, and `COMMIT`/`ROLLBACK` |
| Export CSV | Saves the rows currently shown (after filter and sort) of any table or report as a CSV file (UTF-8, opens in Excel) |

Reads run in autocommit mode, so **Refresh** always shows changes made from other clients such
as the MySQL command line.

### Operations (workflows)

| Page | What it writes |
|---|---|
| Receive stock | One `receipt` and its `receipt_line` rows (put-away into bins of the receiving warehouse), in one transaction |
| New transfer | A PENDING `transfer` and its `transfer_line` rows, picked from stock in the source warehouse |
| Process transfers | Mark in transit (`status` → IN_TRANSIT), save put-away bins (`dest_bin_id`), confirm (bins + `status` → CONFIRMED in one transaction) or cancel |
| Dispatch stock | One `dispatch` and its `dispatch_line` rows, picked from stock in that warehouse |
| Record damage | One `damaged` row; the units leave usable stock |
| Bin search | Read only: bins and their contents by bin code, zone, SKU or product, with reserved and available quantities |

### Business rules checked by the application

The database enforces keys, foreign keys, CHECK constraints and the confirmation triggers. These
rules are not in the schema, so the application checks them before writing (in the workflows and
in the insert forms of the table pages):

| Rule | Example message |
|---|---|
| A bin on a receipt, transfer or dispatch belongs to that document's warehouse (destination bins to the destination warehouse) | "Bin HYD-BS-01 belongs to Hyderabad Central DC, not Pune West Depot." |
| Transfer and dispatch quantities fit the bin's stock, minus stock reserved by PENDING transfers | "Only 438 of PLB-PVC-025 available in BLR-BS-01 (588 on hand, 150 reserved by pending transfers); 500 requested." |
| Damage quantity fits the bin's stock | "Only 110 of PNT-WHT-020 on hand in PUN-BS-01; 500 requested." |
| Transfers only move forward: PENDING → IN_TRANSIT → CONFIRMED, or to CANCELLED; CONFIRMED and CANCELLED are final | "Transfer #1 is CONFIRMED; it cannot change to PENDING. Allowed: none (final state)." |
| Every line has a destination bin before confirming | "Every line needs a destination bin before the transfer can be confirmed." |

Status changes use `UPDATE transfer SET status = ? WHERE transfer_id = ? AND status = ?`, so a
transfer changed by someone else in the meantime is reported instead of overwritten.

### Reports

**Operations → Reports** runs read-only queries (joins, subqueries, aggregation over `v_bin_stock`)
each time a tab is opened or F5 is pressed. Every report can be filtered and exported to CSV.

| Report | What it shows |
|---|---|
| Warehouse stock | Units on hand per warehouse and product, bins used, reserved by PENDING transfers, available |
| Pending and in transit | Transfer lines not yet confirmed, with age in days; IN_TRANSIT units are in no bin |
| Bin utilization | Bins per zone, occupied versus empty, occupied % (bins have no capacity column) |
| Stock ageing | Days since the first inbound movement (receipt or confirmed transfer) into each stocked bin, in 30-day bands |
| Damaged stock | Damage incidents and units per warehouse and product, as a % of units received into that warehouse |
| Reorder needs | Company-wide stock (on hand plus in transit) against each product's reorder level, with the shortfall |

### Keyboard

| Key | Action |
|---|---|
| Ctrl+N | New record on the current table |
| Del | Delete selected rows |
| Ctrl+F | Focus the filter box (Esc clears it) |
| F5 | Reload the current page (or re-run the report) and the sidebar counts |
| Ctrl+E | Export the rows shown to CSV |
| Ctrl+L | Show or hide the SQL activity panel |

### Database errors

| MySQL error | Cause | What the app shows |
|---|---|---|
| 1062 | Duplicate unique or primary key | Message under the field, e.g. "A supplier with this name already exists." |
| 1451 | Deleting a row that other rows reference | "Could not delete supplier “…”. It is still referenced by receipts. Delete those receipts first." |
| 1452 | Referenced parent row is missing | "The selected warehouse no longer exists. Refresh and try again." |
| 3819 | CHECK constraint violated | The rule in plain words, e.g. "Source and destination warehouse must be different." |
| 1644 | Trigger rejected the change | The trigger's own message, e.g. "Lines on a CONFIRMED transfer must have a dest_bin_id" |

The raw MySQL text, including the constraint name, is shown underneath and in the SQL activity
panel.

## Project layout

```
UI/
├── main.py              entry point: application setup, login, main window
├── requirements.txt     pinned dependencies
├── style.qss            the single application stylesheet
├── assets/              monochrome UI glyphs
└── stm/
    ├── db.py            connection, every SQL statement, transactions, error translation
    ├── schema.py        table definitions: grid columns, form fields, keys (no SQL)
    ├── operations.py    workflows and the business rules the schema does not enforce (no SQL)
    ├── credentials.py   remembered login (Credential Manager + registry)
    ├── login_dialog.py  startup connection dialog
    ├── main_window.py   sidebar, pages, menus, shortcuts, status bar
    ├── sidebar.py       grouped navigation with row counts
    ├── page.py          base class and header shared by all pages
    ├── table_page.py    grid, filter, New / Delete / Refresh for one table
    ├── grid.py          sortable, filterable data grid
    ├── table_model.py   grid model, sort/filter proxy, status chips
    ├── record_dialog.py generated insert form with inline validation
    ├── reports.py       report definitions: columns, keys, summary lines (no SQL)
    ├── reports_page.py  tabbed reports page
    ├── export.py        CSV export
    ├── dialogs.py       confirmation and error dialogs
    ├── activity_log.py  SQL activity panel
    ├── widgets.py       small shared widget helpers
    ├── theme.py         fonts and painted colours
    └── workflows/       receive, new transfer, process transfers, dispatch, damage, bin search
```

## Demo script

Total time about five minutes. Before starting, make sure the `MySQL80` service is running and
open a MySQL prompt next to the app to show each change at the database level:

```bash
mysql --login-path=local stock_transfer_db
```

(or `mysql -u root -p stock_transfer_db`).

### 1. View records

1. Start the app and press **Connect**. It opens on **Bin stock** (view `v_bin_stock`):
   5 rows, **On hand total 3,324**. Each balance is derived from receipts, transfers, dispatches
   and damage; there is no stock table.
2. Click **Transfers**. Point out the status labels: CONFIRMED, IN_TRANSIT, PENDING.
3. Press **Ctrl+F**, type `pune`. The grid shows 2 of 3 rows and the status bar reads
   `2 of 3 rows`. Press **Esc**.
4. Click **Bins**. Each bin shows its zone and warehouse by name (joined through `zone`), not by ID.
   Click the **Bin code** header to sort.

### 2. Insert

1. Click **Suppliers**: 4 rows.
   Before, in MySQL: `SELECT * FROM supplier;` returns 4 rows.
2. Press **Ctrl+N**. Enter Name `Shakti Hardware Pvt Ltd`, Contact `+91 44 2345 6789`.
   Press **Insert**.
3. After: the new row (ID 5) is selected, the sidebar count changes from 4 to 5, the status bar
   reads `Inserted supplier “Shakti Hardware Pvt Ltd”.` and the SQL activity panel shows
   `START TRANSACTION`, the `INSERT` with its values, `1 row affected`, `COMMIT`.
   In MySQL: `SELECT * FROM supplier;` returns 5 rows.
4. Insert that changes stock: click **Receipt lines**, press **Ctrl+N** and choose
   Receipt `#3 … Kaveri Paints Co. → Pune West Depot`, Bin `PUN-BS-02`,
   Product `PNT-WHT-020  Wall Paint 20L White`, Quantity `50`. Press **Insert**.
   Click **Bin stock**: a new row for PUN-BS-02 with 50 on hand; 6 rows, total 3,374.
   In MySQL: `SELECT bin_code, sku, on_hand FROM v_bin_stock;`
5. Constraints (optional):
   - Suppliers → **Ctrl+N** → Name `Deccan Electricals Pvt Ltd` → Insert: "A supplier with this
     name already exists." under Name (1062).
   - Transfers → **Ctrl+N** → same warehouse in From and To → Insert: blocked with "Source and
     destination warehouse must be different." (mirrors CHECK `chk_transfer_diff_warehouse`).
   - Transfer lines → **Ctrl+N** → Transfer `#1 CONFIRMED`, Source bin `HYD-BS-02`,
     Product `ELE-SWT-006`, Quantity `5`, no destination bin → Insert: the trigger
     `trg_transfer_line_dest_bi` rejects it (1644).

### 3. Delete

1. Click **Receipt lines**, select the row `3 · PUN-BS-02 · PNT-WHT-020 · 50`, press **Del**.
   The dialog names the record. Press **Delete**. Click **Bin stock**: back to 5 rows, 3,324.
2. Click **Suppliers**, select `Shakti Hardware Pvt Ltd`, press **Del**, then **Delete**.
   The count goes from 5 back to 4. In MySQL: `SELECT * FROM supplier;` returns 4 rows.
3. Refused delete: select `Deccan Electricals Pvt Ltd`, press **Del**, then **Delete**.
   The app shows "It is still referenced by receipts" (1451, constraint `fk_receipt_supplier`).
   The SQL panel shows the `DELETE` followed by `ROLLBACK`, and the row stays.
4. Cascade preview (optional): click **Warehouses**, select `Hyderabad Central DC`, press
   **Del**. The dialog says it also deletes 3 zones and 7 bins (ON DELETE CASCADE). Press
   **Cancel**.

### 4. Workflows (optional, if time allows)

1. **Bin search**: type `pvc`. BLR-BS-01 shows 588 on hand, 150 reserved (pending transfer #3),
   438 available.
2. **New transfer**: From `Hyderabad Central DC`, To `Bengaluru East Hub`. Pick
   `HYD-BS-01  ELE-LED-009 … 726 available`, Quantity `800`, **Add line**: refused, only 726
   available. Change to `100`, **Add line**, **Create transfer**. The status bar reads
   `Created transfer #4 (PENDING) …`.
3. **Process transfers**: select transfer 4. **Confirm receipt** with no destination bin is
   refused. **Mark in transit**: Bin stock now shows HYD-BS-01 at 626 (the 100 units are in no
   bin). Select transfer 4 again, choose destination `BLR-BS-03`, **Confirm receipt**: Bin stock
   shows BLR-BS-03 with 100. The SQL panel shows the `UPDATE transfer_line` and
   `UPDATE transfer ... WHERE ... AND status = 'IN_TRANSIT'` in one transaction.
4. To undo: **Transfers** → select transfer 4 → **Del** → **Delete** (its line is removed by
   ON DELETE CASCADE), then reset the counter as below.

### 5. Reports (optional)

1. Click **Reports**. **Warehouse stock** totals 3,324 on hand, 150 reserved, 3,174 available.
2. Click **Reorder needs**: 3 products below reorder level (Copper Wire, Ceiling Fan, Cordless
   Drill), shortfall 115 units. Modular Switch counts its 500 in-transit units.
3. Click **Bin utilization**: 5 of 17 bins occupied (29.4%).
4. Press **Ctrl+E** and save the CSV; open it in Excel to show the same rows.

### After the demo

InnoDB never reuses an auto-increment value, so after inserting and deleting the supplier the
next new supplier would get ID 6. To put the counters back to their previous values (each only
takes effect if no higher ID exists):

```sql
ALTER TABLE supplier AUTO_INCREMENT = 5;
ALTER TABLE transfer AUTO_INCREMENT = 4;
```
