-- Verification for stock_transfer_db: engines, exact row counts, FKs, full table dump.
USE stock_transfer_db;

-- 1) Storage engine per table (FKs are only enforced on InnoDB)
SELECT TABLE_NAME, ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'stock_transfer_db'
ORDER BY TABLE_NAME;

-- 2) Exact row counts (COUNT(*), not the InnoDB TABLE_ROWS estimate)
SELECT 'Supplier'      AS table_name, COUNT(*) AS row_count FROM Supplier
UNION ALL SELECT 'Warehouse',     COUNT(*) FROM Warehouse
UNION ALL SELECT 'Zone',          COUNT(*) FROM Zone
UNION ALL SELECT 'Bin',           COUNT(*) FROM Bin
UNION ALL SELECT 'Product',       COUNT(*) FROM Product
UNION ALL SELECT 'Receipt',       COUNT(*) FROM Receipt
UNION ALL SELECT 'Receipt_Line',  COUNT(*) FROM Receipt_Line
UNION ALL SELECT 'Transfer',      COUNT(*) FROM Transfer
UNION ALL SELECT 'Transfer_Line', COUNT(*) FROM Transfer_Line
UNION ALL SELECT 'Dispatch',      COUNT(*) FROM Dispatch
UNION ALL SELECT 'Dispatch_Line', COUNT(*) FROM Dispatch_Line
UNION ALL SELECT 'Damaged',       COUNT(*) FROM Damaged;

-- 3) Every foreign key column that actually exists in the catalog
SELECT TABLE_NAME, CONSTRAINT_NAME, COLUMN_NAME,
       REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'stock_transfer_db'
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, CONSTRAINT_NAME;

SELECT COUNT(*) AS fk_columns_found, 19 AS fk_columns_expected
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'stock_transfer_db'
  AND REFERENCED_TABLE_NAME IS NOT NULL;

-- 4) Full contents of every table (ORDER BY: InnoDB may scan a covering secondary index otherwise)
SELECT * FROM Supplier      ORDER BY supplier_id;
SELECT * FROM Warehouse     ORDER BY warehouse_id;
SELECT * FROM Zone          ORDER BY zone_id;
SELECT * FROM Bin           ORDER BY bin_id;
SELECT * FROM Product       ORDER BY product_id;
SELECT * FROM Receipt       ORDER BY receipt_id;
SELECT * FROM Receipt_Line  ORDER BY receipt_id, bin_id, product_id;
SELECT * FROM Transfer      ORDER BY transfer_id;
SELECT * FROM Transfer_Line ORDER BY transfer_id, source_bin_id, product_id;
SELECT * FROM Dispatch      ORDER BY dispatch_id;
SELECT * FROM Dispatch_Line ORDER BY dispatch_id, bin_id, product_id;
SELECT * FROM Damaged       ORDER BY bin_id, product_id, damage_date;

-- 5) Triggers and the derived bin-stock view
SELECT TRIGGER_NAME, EVENT_MANIPULATION, EVENT_OBJECT_TABLE, ACTION_TIMING
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = 'stock_transfer_db'
ORDER BY EVENT_OBJECT_TABLE, TRIGGER_NAME;

SELECT warehouse_name, bin_code, sku, product_name,
       received, transferred_in, transferred_out, dispatched, damaged, on_hand
FROM v_bin_stock
ORDER BY warehouse_id, bin_code, sku;
