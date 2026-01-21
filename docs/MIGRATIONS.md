## Migration notes

001_create_trades_audit.sql

- Purpose: Create `trades_audit` table to persist exchange `user_trades` for external-close auditing.
- Usage: run the SQL against the application's SQLite DB (see config.DB_PATH).

Example:

```bash
sqlite3 /path/to/klines.db
.read migrations/001_create_trades_audit.sql
```

This migration is idempotent (uses IF NOT EXISTS).
