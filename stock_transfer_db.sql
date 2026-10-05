-- =====================================================================
-- Multi-Warehouse Stock Transfer Management System
-- Review 2: 3NF schema (DDL + constraints) and sample data
-- Target: MySQL 8.0.16+ (CHECK constraints enforced), InnoDB
-- =====================================================================

CREATE DATABASE IF NOT EXISTS stock_transfer_db
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_0900_ai_ci;

USE stock_transfer_db;

-- Drop the view and child tables before parents so the script can be re-run cleanly.
DROP VIEW IF EXISTS v_bin_stock;
DROP TABLE IF EXISTS Damaged;
DROP TABLE IF EXISTS Dispatch_Line;
DROP TABLE IF EXISTS Transfer_Line;
DROP TABLE IF EXISTS Receipt_Line;
DROP TABLE IF EXISTS Dispatch;
DROP TABLE IF EXISTS Transfer;
DROP TABLE IF EXISTS Receipt;
DROP TABLE IF EXISTS Bin;
DROP TABLE IF EXISTS Zone;
DROP TABLE IF EXISTS Product;
DROP TABLE IF EXISTS Warehouse;
DROP TABLE IF EXISTS Supplier;

-- =====================================================================
-- STRONG ENTITIES
-- =====================================================================

-- 3NF: single-column PK supplier_id -> {name, contact}; atomic values, no non-key attribute depends on another.
CREATE TABLE Supplier (
    supplier_id  INT          NOT NULL AUTO_INCREMENT,
    name         VARCHAR(100) NOT NULL,
    contact      VARCHAR(100) NOT NULL,
    CONSTRAINT pk_supplier PRIMARY KEY (supplier_id),
    CONSTRAINT uq_supplier_name UNIQUE (name)
) ENGINE = InnoDB;

-- 3NF: warehouse_id -> {name, location} only; location is a plain attribute, not a key for other data.
CREATE TABLE Warehouse (
    warehouse_id INT          NOT NULL AUTO_INCREMENT,
    name         VARCHAR(100) NOT NULL,
    location     VARCHAR(150) NOT NULL,
    CONSTRAINT pk_warehouse PRIMARY KEY (warehouse_id),
    CONSTRAINT uq_warehouse_name UNIQUE (name)
) ENGINE = InnoDB;

-- 3NF: product_id -> {name, sku, reorder_level}; sku is a candidate key, so no transitive dependency arises.
CREATE TABLE Product (
    product_id    INT          NOT NULL AUTO_INCREMENT,
    name          VARCHAR(100) NOT NULL,
    sku           VARCHAR(30)  NOT NULL,
    reorder_level INT          NOT NULL DEFAULT 0,
    CONSTRAINT pk_product PRIMARY KEY (product_id),
    CONSTRAINT uq_product_sku UNIQUE (sku),
    CONSTRAINT chk_product_reorder CHECK (reorder_level >= 0)
) ENGINE = InnoDB;

-- =====================================================================
-- WEAK ENTITIES (existence-dependent on owner; FK is NOT NULL + CASCADE)
-- =====================================================================

-- 3NF: zone_id -> {zone_name, warehouse_id}; warehouse details live only in Warehouse, not repeated here.
CREATE TABLE Zone (
    zone_id      INT          NOT NULL AUTO_INCREMENT,
    zone_name    VARCHAR(50)  NOT NULL,
    warehouse_id INT          NOT NULL,
    CONSTRAINT pk_zone PRIMARY KEY (zone_id),
    CONSTRAINT uq_zone_per_warehouse UNIQUE (warehouse_id, zone_name),
    CONSTRAINT fk_zone_warehouse FOREIGN KEY (warehouse_id)
        REFERENCES Warehouse (warehouse_id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE = InnoDB;

-- 3NF: bin_id -> {bin_code, zone_id}; warehouse is reached through Zone, so storing it here would be transitive.
CREATE TABLE Bin (
    bin_id   INT         NOT NULL AUTO_INCREMENT,
    bin_code VARCHAR(20) NOT NULL,
    zone_id  INT         NOT NULL,
    CONSTRAINT pk_bin PRIMARY KEY (bin_id),
    CONSTRAINT uq_bin_code UNIQUE (bin_code),
    CONSTRAINT fk_bin_zone FOREIGN KEY (zone_id)
        REFERENCES Zone (zone_id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE = InnoDB;

-- =====================================================================
-- TRANSACTION HEADERS (1:N relationships mapped as FKs on the N side)
-- =====================================================================

-- 3NF: receipt_id -> {receipt_date, supplier_id, warehouse_id}; supplier/warehouse names are not duplicated here.
CREATE TABLE Receipt (
    receipt_id   INT  NOT NULL AUTO_INCREMENT,
    receipt_date DATE NOT NULL DEFAULT (CURRENT_DATE),
    supplier_id  INT  NOT NULL,
    warehouse_id INT  NOT NULL,
    CONSTRAINT pk_receipt PRIMARY KEY (receipt_id),
    CONSTRAINT fk_receipt_supplier FOREIGN KEY (supplier_id)
        REFERENCES Supplier (supplier_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_receipt_warehouse FOREIGN KEY (warehouse_id)
        REFERENCES Warehouse (warehouse_id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE = InnoDB;

-- 3NF: transfer_id -> {status, transfer_date, source_warehouse_id, dest_warehouse_id}; both FKs are direct facts of one transfer.
CREATE TABLE Transfer (
    transfer_id         INT         NOT NULL AUTO_INCREMENT,
    status              VARCHAR(12) NOT NULL DEFAULT 'PENDING',
    transfer_date       DATE        NOT NULL DEFAULT (CURRENT_DATE),
    source_warehouse_id INT         NOT NULL,
    dest_warehouse_id   INT         NOT NULL,
    CONSTRAINT pk_transfer PRIMARY KEY (transfer_id),
    CONSTRAINT chk_transfer_status
        CHECK (status IN ('PENDING', 'IN_TRANSIT', 'CONFIRMED', 'CANCELLED')),
    CONSTRAINT chk_transfer_diff_warehouse
        CHECK (source_warehouse_id <> dest_warehouse_id),
    -- RESTRICT (not CASCADE) is required: MySQL rejects CHECKs on columns used by cascading FK actions.
    CONSTRAINT fk_transfer_source FOREIGN KEY (source_warehouse_id)
        REFERENCES Warehouse (warehouse_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_transfer_dest FOREIGN KEY (dest_warehouse_id)
        REFERENCES Warehouse (warehouse_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB;

-- 3NF: dispatch_id -> {destination, dispatch_date, warehouse_id}; destination is free text, not a key to other attributes.
CREATE TABLE Dispatch (
    dispatch_id   INT          NOT NULL AUTO_INCREMENT,
    destination   VARCHAR(150) NOT NULL,
    dispatch_date DATE         NOT NULL DEFAULT (CURRENT_DATE),
    warehouse_id  INT          NOT NULL,
    CONSTRAINT pk_dispatch PRIMARY KEY (dispatch_id),
    CONSTRAINT fk_dispatch_warehouse FOREIGN KEY (warehouse_id)
        REFERENCES Warehouse (warehouse_id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE = InnoDB;

-- =====================================================================
-- RELATIONSHIPS WITH ATTRIBUTES (M:N / ternary -> own relation)
-- =====================================================================

-- 3NF: composite PK (receipt_id, bin_id, product_id) -> quantity; the only non-key attribute needs the whole key.
CREATE TABLE Receipt_Line (
    receipt_id INT NOT NULL,
    bin_id     INT NOT NULL,
    product_id INT NOT NULL,
    quantity   INT NOT NULL,
    CONSTRAINT pk_receipt_line PRIMARY KEY (receipt_id, bin_id, product_id),
    CONSTRAINT chk_receipt_line_qty CHECK (quantity > 0),
    CONSTRAINT fk_rl_receipt FOREIGN KEY (receipt_id)
        REFERENCES Receipt (receipt_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_rl_bin FOREIGN KEY (bin_id)
        REFERENCES Bin (bin_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_rl_product FOREIGN KEY (product_id)
        REFERENCES Product (product_id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE = InnoDB;

-- 3NF: composite PK (transfer_id, source_bin_id, product_id) -> {dest_bin_id, quantity}; Bin plays "from" and "to" roles.
CREATE TABLE Transfer_Line (
    transfer_id   INT NOT NULL,
    source_bin_id INT NOT NULL,
    product_id    INT NOT NULL,
    dest_bin_id   INT NULL,          -- NULL until put-away at the destination warehouse
    quantity      INT NOT NULL,
    CONSTRAINT pk_transfer_line PRIMARY KEY (transfer_id, source_bin_id, product_id),
    CONSTRAINT chk_transfer_line_qty CHECK (quantity > 0),
    CONSTRAINT chk_transfer_line_bins
        CHECK (dest_bin_id IS NULL OR dest_bin_id <> source_bin_id),
    CONSTRAINT fk_tl_transfer FOREIGN KEY (transfer_id)
        REFERENCES Transfer (transfer_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    -- RESTRICT on both bin FKs: their columns appear in chk_transfer_line_bins.
    CONSTRAINT fk_tl_source_bin FOREIGN KEY (source_bin_id)
        REFERENCES Bin (bin_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_tl_dest_bin FOREIGN KEY (dest_bin_id)
        REFERENCES Bin (bin_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_tl_product FOREIGN KEY (product_id)
        REFERENCES Product (product_id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE = InnoDB;

-- 3NF: composite PK (dispatch_id, bin_id, product_id) -> quantity; no partial or transitive dependency is possible.
CREATE TABLE Dispatch_Line (
    dispatch_id INT NOT NULL,
    bin_id      INT NOT NULL,
    product_id  INT NOT NULL,
    quantity    INT NOT NULL,
    CONSTRAINT pk_dispatch_line PRIMARY KEY (dispatch_id, bin_id, product_id),
    CONSTRAINT chk_dispatch_line_qty CHECK (quantity > 0),
    CONSTRAINT fk_dl_dispatch FOREIGN KEY (dispatch_id)
        REFERENCES Dispatch (dispatch_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_dl_bin FOREIGN KEY (bin_id)
        REFERENCES Bin (bin_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_dl_product FOREIGN KEY (product_id)
        REFERENCES Product (product_id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE = InnoDB;

-- 3NF: PK (bin_id, product_id, damage_date) -> {quantity, reason}; each damage event's facts depend on the full key.
CREATE TABLE Damaged (
    bin_id      INT          NOT NULL,
    product_id  INT          NOT NULL,
    damage_date DATE         NOT NULL DEFAULT (CURRENT_DATE),
    quantity    INT          NOT NULL,
    reason      VARCHAR(200) NOT NULL,
    CONSTRAINT pk_damaged PRIMARY KEY (bin_id, product_id, damage_date),
    CONSTRAINT chk_damaged_qty CHECK (quantity > 0),
    CONSTRAINT fk_damaged_bin FOREIGN KEY (bin_id)
        REFERENCES Bin (bin_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_damaged_product FOREIGN KEY (product_id)
        REFERENCES Product (product_id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE = InnoDB;

-- =====================================================================
-- TRIGGERS: confirmation before destination credit
-- (status lives in Transfer, dest_bin_id in Transfer_Line, so a CHECK cannot span them)
-- =====================================================================

DELIMITER $$

-- A transfer cannot become CONFIRMED while any of its lines lacks a destination bin.
CREATE TRIGGER trg_transfer_confirm_bu
BEFORE UPDATE ON Transfer
FOR EACH ROW
BEGIN
    IF NEW.status = 'CONFIRMED' AND EXISTS (
        SELECT 1 FROM Transfer_Line
        WHERE transfer_id = NEW.transfer_id AND dest_bin_id IS NULL
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Cannot confirm transfer: every line needs a dest_bin_id (put-away) first';
    END IF;
END$$

-- A line added to an already CONFIRMED transfer must carry its destination bin.
CREATE TRIGGER trg_transfer_line_dest_bi
BEFORE INSERT ON Transfer_Line
FOR EACH ROW
BEGIN
    IF NEW.dest_bin_id IS NULL AND EXISTS (
        SELECT 1 FROM Transfer
        WHERE transfer_id = NEW.transfer_id AND status = 'CONFIRMED'
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Lines on a CONFIRMED transfer must have a dest_bin_id';
    END IF;
END$$

-- The destination bin of a line on a CONFIRMED transfer cannot be cleared.
CREATE TRIGGER trg_transfer_line_dest_bu
BEFORE UPDATE ON Transfer_Line
FOR EACH ROW
BEGIN
    IF NEW.dest_bin_id IS NULL AND EXISTS (
        SELECT 1 FROM Transfer
        WHERE transfer_id = NEW.transfer_id AND status = 'CONFIRMED'
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Lines on a CONFIRMED transfer must have a dest_bin_id';
    END IF;
END$$

DELIMITER ;

-- =====================================================================
-- VIEW: which product is in which bin
-- Balances are derived from the movement tables, not stored, so no update anomalies.
-- Transfers leave the source bin once IN_TRANSIT or CONFIRMED (PENDING stock has not moved)
-- and are credited to the destination bin only when CONFIRMED.
-- =====================================================================

CREATE VIEW v_bin_stock AS
SELECT w.warehouse_id,
       w.name      AS warehouse_name,
       z.zone_name,
       b.bin_id,
       b.bin_code,
       p.product_id,
       p.sku,
       p.name      AS product_name,
       SUM(CASE WHEN m.movement = 'RECEIPT'      THEN  m.qty ELSE 0 END) AS received,
       SUM(CASE WHEN m.movement = 'TRANSFER_IN'  THEN  m.qty ELSE 0 END) AS transferred_in,
       SUM(CASE WHEN m.movement = 'TRANSFER_OUT' THEN -m.qty ELSE 0 END) AS transferred_out,
       SUM(CASE WHEN m.movement = 'DISPATCH'     THEN -m.qty ELSE 0 END) AS dispatched,
       SUM(CASE WHEN m.movement = 'DAMAGED'      THEN -m.qty ELSE 0 END) AS damaged,
       SUM(m.qty)  AS on_hand
FROM (
    SELECT 'RECEIPT' AS movement, bin_id, product_id, quantity AS qty
    FROM Receipt_Line
    UNION ALL
    SELECT 'TRANSFER_OUT', tl.source_bin_id, tl.product_id, -tl.quantity
    FROM Transfer_Line tl
    JOIN Transfer t ON t.transfer_id = tl.transfer_id
    WHERE t.status IN ('IN_TRANSIT', 'CONFIRMED')
    UNION ALL
    SELECT 'TRANSFER_IN', tl.dest_bin_id, tl.product_id, tl.quantity
    FROM Transfer_Line tl
    JOIN Transfer t ON t.transfer_id = tl.transfer_id
    WHERE t.status = 'CONFIRMED'
    UNION ALL
    SELECT 'DISPATCH', bin_id, product_id, -quantity
    FROM Dispatch_Line
    UNION ALL
    SELECT 'DAMAGED', bin_id, product_id, -quantity
    FROM Damaged
) AS m
JOIN Bin b       ON b.bin_id = m.bin_id
JOIN Zone z      ON z.zone_id = b.zone_id
JOIN Warehouse w ON w.warehouse_id = z.warehouse_id
JOIN Product p   ON p.product_id = m.product_id
GROUP BY w.warehouse_id, w.name, z.zone_name, b.bin_id, b.bin_code,
         p.product_id, p.sku, p.name;

-- =====================================================================
-- SAMPLE DATA
-- Explicit IDs keep FK references readable; all company names are fictional.
-- =====================================================================

INSERT INTO Supplier (supplier_id, name, contact) VALUES
    (1, 'Deccan Electricals Pvt Ltd',   '+91 40 4012 3456'),
    (2, 'Sahyadri Pipes & Fittings',    '+91 20 2567 8812'),
    (3, 'Kaveri Paints Co.',            '+91 80 4190 2275'),
    (4, 'Vajra Tools & Hardware',       '+91 22 2854 6630');

INSERT INTO Warehouse (warehouse_id, name, location) VALUES
    (1, 'Hyderabad Central DC',  'Shamshabad, Hyderabad, Telangana'),
    (2, 'Bengaluru East Hub',    'Hoskote, Bengaluru, Karnataka'),
    (3, 'Pune West Depot',       'Chakan, Pune, Maharashtra');

INSERT INTO Zone (zone_id, zone_name, warehouse_id) VALUES
    (1, 'Receiving Dock',         1),
    (2, 'Bulk Storage',           1),
    (3, 'Fast-Pick',              1),
    (4, 'Bulk Storage',           2),
    (5, 'Fast-Pick',              2),
    (6, 'Bulk Storage',           3),
    (7, 'Returns & Quarantine',   3);

INSERT INTO Bin (bin_id, bin_code, zone_id) VALUES
    ( 1, 'HYD-RD-01', 1),
    ( 2, 'HYD-RD-02', 1),
    ( 3, 'HYD-BS-01', 2),
    ( 4, 'HYD-BS-02', 2),
    ( 5, 'HYD-BS-03', 2),
    ( 6, 'HYD-FP-01', 3),
    ( 7, 'HYD-FP-02', 3),
    ( 8, 'BLR-BS-01', 4),
    ( 9, 'BLR-BS-02', 4),
    (10, 'BLR-BS-03', 4),
    (11, 'BLR-FP-01', 5),
    (12, 'BLR-FP-02', 5),
    (13, 'PUN-BS-01', 6),
    (14, 'PUN-BS-02', 6),
    (15, 'PUN-BS-03', 6),
    (16, 'PUN-RQ-01', 7),
    (17, 'PUN-RQ-02', 7);

INSERT INTO Product (product_id, name, sku, reorder_level) VALUES
    (1, 'LED Bulb 9W (Pack of 4)',       'ELE-LED-009',  200),
    (2, 'Ceiling Fan 1200mm',            'ELE-FAN-1200',  40),
    (3, 'PVC Pipe 1in x 3m',             'PLB-PVC-025',  150),
    (4, 'Copper Wire 1.5 sq mm (90m)',   'ELE-WIR-015',   60),
    (5, 'Wall Paint 20L White',          'PNT-WHT-020',   30),
    (6, 'Cordless Drill 18V',            'TLS-DRL-018',   15),
    (7, 'Modular Switch 6A',             'ELE-SWT-006',  300);

-- Receipts (inbound from suppliers) -- 3 headers + 4 lines
INSERT INTO Receipt (receipt_id, receipt_date, supplier_id, warehouse_id) VALUES
    (1, '2026-08-03', 1, 1),
    (2, '2026-08-05', 2, 2),
    (3, '2026-08-07', 3, 3);

INSERT INTO Receipt_Line (receipt_id, bin_id, product_id, quantity) VALUES
    (1,  3, 1, 1200),   -- LED bulbs  -> HYD-BS-01
    (1,  4, 7, 2500),   -- Switches   -> HYD-BS-02
    (2,  8, 3,  600),   -- PVC pipes  -> BLR-BS-01
    (3, 13, 5,  150);   -- Paint      -> PUN-BS-01

-- Transfers (inter-warehouse) -- 3 headers + 3 lines
-- Only the CONFIRMED transfer has been put away, so only it has a dest_bin_id.
INSERT INTO Transfer (transfer_id, status, transfer_date, source_warehouse_id, dest_warehouse_id) VALUES
    (1, 'CONFIRMED',  '2026-08-10', 1, 2),
    (2, 'IN_TRANSIT', '2026-08-14', 1, 3),
    (3, 'PENDING',    '2026-08-18', 2, 3);

INSERT INTO Transfer_Line (transfer_id, source_bin_id, product_id, dest_bin_id, quantity) VALUES
    (1, 3, 1,    9, 300),   -- LED bulbs HYD-BS-01 -> BLR-BS-02 (received)
    (2, 4, 7, NULL, 500),   -- Switches  HYD-BS-02 -> Pune (on the road)
    (3, 8, 3, NULL, 150);   -- PVC pipes BLR-BS-01 -> Pune (not yet shipped)

-- Dispatches (outbound to customers) -- 2 headers + 3 lines
INSERT INTO Dispatch (dispatch_id, destination, dispatch_date, warehouse_id) VALUES
    (1, 'BuildRight Constructions, Gachibowli, Hyderabad', '2026-08-12', 1),
    (2, 'Shree Ganesh Hardware, Kothrud, Pune',            '2026-08-16', 3);

INSERT INTO Dispatch_Line (dispatch_id, bin_id, product_id, quantity) VALUES
    (1,  3, 1, 150),
    (1,  4, 7, 400),
    (2, 13, 5,  40);

-- Damage events -- 2 rows
INSERT INTO Damaged (bin_id, product_id, damage_date, quantity, reason) VALUES
    (3, 1, '2026-08-04', 24, 'Cartons crushed during unloading'),
    (8, 3, '2026-08-12', 12, 'Pipes cracked by forklift impact');

-- =====================================================================
-- EXTENDED SAMPLE DATA (21 Aug - 4 Oct 2026)
-- More suppliers, products and movements, with transfers in every status,
-- so the reports (warehouse stock, stock ageing, bin utilization, damage,
-- reorder needs) have realistic data. Every row respects the business
-- rules: bins belong to the document's warehouse, movements are dated in
-- order, and no bin goes below zero.
-- =====================================================================

INSERT INTO Supplier (supplier_id, name, contact) VALUES
    (5, 'Nilgiri Cables & Wires',       '+91 422 245 7781'),
    (6, 'Godavari Sanitary Fittings',   '+91 891 276 4410'),
    (7, 'Malwa Switchgear Pvt Ltd',     '+91 731 249 3367');

INSERT INTO Product (product_id, name, sku, reorder_level) VALUES
    ( 8, 'Distribution Board 8-Way',     'ELE-DB-008',    20),
    ( 9, 'MCB 32A Single Pole',          'ELE-MCB-032',  100),
    (10, 'CPVC Elbow 1in (Pack of 10)',  'PLB-ELB-025',   80),
    (11, 'Ball Valve 1in Brass',         'PLB-VAL-025',   80),
    (12, 'Enamel Paint 1L Black',        'PNT-BLK-001',   50),
    (13, 'Hammer Drill Bit Set 5pc',     'TLS-BIT-005',   25);

-- Receipts -- 6 headers + 12 lines
INSERT INTO Receipt (receipt_id, receipt_date, supplier_id, warehouse_id) VALUES
    (4, '2026-08-21', 5, 1),
    (5, '2026-08-26', 6, 2),
    (6, '2026-09-02', 7, 3),
    (7, '2026-09-10', 4, 1),
    (8, '2026-09-18', 3, 2),
    (9, '2026-09-29', 1, 3);

INSERT INTO Receipt_Line (receipt_id, bin_id, product_id, quantity) VALUES
    (4,  5,  4, 120),   -- Copper wire   -> HYD-BS-03
    (4,  6,  9, 400),   -- MCBs          -> HYD-FP-01
    (5, 10, 10, 300),   -- CPVC elbows   -> BLR-BS-03
    (5, 11, 11,  90),   -- Ball valves   -> BLR-FP-01
    (6, 14,  8,  60),   -- Dist. boards  -> PUN-BS-02
    (6, 15,  2,  35),   -- Ceiling fans  -> PUN-BS-03
    (7,  7,  6,  40),   -- Drills        -> HYD-FP-02
    (7,  7, 13,  70),   -- Drill bits    -> HYD-FP-02
    (8, 12, 12, 180),   -- Enamel paint  -> BLR-FP-02
    (8, 12,  5,  80),   -- Wall paint    -> BLR-FP-02
    (9, 13,  1, 400),   -- LED bulbs     -> PUN-BS-01
    (9, 13,  7, 600);   -- Switches      -> PUN-BS-01

-- Transfers -- 5 headers + 5 lines, covering every status
INSERT INTO Transfer (transfer_id, status, transfer_date, source_warehouse_id, dest_warehouse_id) VALUES
    (4, 'CONFIRMED',  '2026-08-28', 1, 2),
    (5, 'CONFIRMED',  '2026-09-08', 2, 3),
    (6, 'CANCELLED',  '2026-09-15', 2, 1),
    (7, 'IN_TRANSIT', '2026-09-22', 1, 3),
    (8, 'PENDING',    '2026-10-01', 3, 1);

INSERT INTO Transfer_Line (transfer_id, source_bin_id, product_id, dest_bin_id, quantity) VALUES
    (4,  5,  4,   10,  40),   -- Copper wire  HYD-BS-03 -> BLR-BS-03 (received)
    (5, 11, 11,   15,  30),   -- Ball valves  BLR-FP-01 -> PUN-BS-03 (received)
    (6, 10, 10, NULL,  50),   -- CPVC elbows  BLR-BS-03 -> Hyderabad (cancelled, no stock effect)
    (7,  6,  9, NULL, 150),   -- MCBs         HYD-FP-01 -> Pune (on the road)
    (8, 14,  8, NULL,  15);   -- Dist. boards PUN-BS-02 -> Hyderabad (not yet shipped)

-- Dispatches -- 4 headers + 8 lines
INSERT INTO Dispatch (dispatch_id, destination, dispatch_date, warehouse_id) VALUES
    (3, 'Sri Sai Electricals, Kukatpally, Hyderabad',  '2026-09-05', 1),
    (4, 'Lakeview Interiors, Whitefield, Bengaluru',   '2026-09-14', 2),
    (5, 'Om Sai Builders, Hinjewadi, Pune',            '2026-09-25', 3),
    (6, 'Green Leaf Residency, Hebbal, Bengaluru',     '2026-10-03', 2);

INSERT INTO Dispatch_Line (dispatch_id, bin_id, product_id, quantity) VALUES
    (3,  5,  4,  30),
    (3,  6,  9, 120),
    (4, 10, 10, 120),
    (4, 11, 11,  25),
    (5, 14,  8,  20),
    (5, 15,  2,  12),
    (6, 12, 12,  60),
    (6, 12,  5,  25);

-- Damage events -- 3 rows
INSERT INTO Damaged (bin_id, product_id, damage_date, quantity, reason) VALUES
    ( 7,  6, '2026-09-12', 2, 'Battery packs swollen on arrival'),
    (15,  2, '2026-09-27', 3, 'Fan blades bent in transit'),
    (12, 12, '2026-10-04', 6, 'Tins dented, lids leaking');
