-- Migration: Create trades_audit table
-- Run on sqlite3 database file: sqlite3 <DB_PATH>

CREATE TABLE IF NOT EXISTS trades_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id TEXT,
    order_id TEXT,
    price REAL,
    qty REAL,
    commission REAL,
    commission_asset TEXT,
    is_buyer INTEGER,
    trade_time TEXT,
    created_time TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Example usage:
-- sqlite3 /path/to/klines.db 
-- sqlite> .read migrations/001_create_trades_audit.sql
