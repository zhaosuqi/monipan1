#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库管理模块
"""

import sqlite3
import threading
from pathlib import Path
from typing import List, Tuple, Any, Optional
from contextlib import contextmanager


class Database:
    """数据库管理类"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, db_path: Optional[str] = None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db_path: Optional[str] = None):
        if hasattr(self, '_initialized') and self._initialized:
            return

        from .config import config
        self.db_path = db_path or config.DB_PATH
        self._local = threading.local()

        # 确保数据库目录存在
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # 初始化表
        self._init_tables()

        self._initialized = True

    def _get_connection(self) -> sqlite3.Connection:
        """获取线程本地的数据库连接"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0,
                isolation_level=None
            )
            self._local.conn.row_factory = sqlite3.Row
            # 启用WAL模式以支持更好的并发访问
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=30000")
        return self._local.conn

    @contextmanager
    def transaction(self):
        """事务上下文管理器"""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise

    def execute(self, sql: str, params: Tuple = ()) -> sqlite3.Cursor:
        """执行SQL"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return cursor

    def executemany(self, sql: str, params_list: List[Tuple]) -> sqlite3.Cursor:
        """批量执行SQL"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.executemany(sql, params_list)
        return cursor

    def fetchone(self, sql: str, params: Tuple = ()) -> Optional[sqlite3.Row]:
        """查询单条记录"""
        cursor = self.execute(sql, params)
        return cursor.fetchone()

    def fetchall(self, sql: str, params: Tuple = ()) -> List[sqlite3.Row]:
        """查询所有记录"""
        cursor = self.execute(sql, params)
        return cursor.fetchall()

    def _init_tables(self):
        """初始化数据库表"""
        # K线数据表
        self.execute("""
            CREATE TABLE IF NOT EXISTS klines_1m (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                open_time TEXT UNIQUE NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                close_time TEXT NOT NULL,
                quote_volume REAL NOT NULL,
                trades INTEGER NOT NULL,
                taker_buy_base REAL NOT NULL,
                taker_buy_quote REAL NOT NULL,
                ignore TEXT
            )
        """)

        # 指标数据表
        self.execute("""
            CREATE TABLE IF NOT EXISTS klines_1m_macd_smooth_ma (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                open_time TEXT UNIQUE NOT NULL,
                close REAL NOT NULL,
                -- 15分钟指标
                macd15m REAL,
                dif15m REAL,
                dea15m REAL,
                j_15 REAL,
                -- 1小时指标
                macd1h REAL,
                dif1h REAL,
                dea1h REAL,
                j_1h REAL,
                -- 4小时指标
                macd4h REAL,
                dif4h REAL,
                dea4h REAL,
                j_4h REAL,
                -- 1天指标
                macd1d REAL,
                dif1d REAL,
                dea1d REAL,
                j_1d REAL,
                -- 时间戳
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 订单表
        self.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE NOT NULL,
                trace_id TEXT NOT NULL,
                symbol TEXT NOT NULL DEFAULT 'BTCUSD_PERP',
                side TEXT NOT NULL CHECK(side IN ('long', 'short')),
                order_type TEXT NOT NULL CHECK(order_type IN (
                    'OPEN', 'TP', 'SL', 'CLOSE_RETREAT',
                    'EOD_CLOSE', 'CLOSE_DECAY', 'MACD_SIGNAL'
                )),
                status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN (
                    'PENDING', 'FILLED', 'PARTIALLY_FILLED',
                    'CANCELED', 'EXPIRED'
                )),
                price REAL NOT NULL,
                contracts REAL NOT NULL,
                filled_contracts REAL DEFAULT 0,
                avg_fill_price REAL,
                created_time TEXT NOT NULL,
                updated_time TEXT NOT NULL,
                filled_time TEXT,
                parent_order_id TEXT,
                position_id TEXT,
                tp_level TEXT,
                sl_trigger_price REAL,
                fee_rate REAL,
                fee_usd REAL,
                notes TEXT,
                kline_close_time TEXT
            )
        """)

        # 订单状态历史表
        self.execute("""
            CREATE TABLE IF NOT EXISTS order_status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT NOT NULL,
                change_time TEXT NOT NULL,
                reason TEXT,
                FOREIGN KEY (order_id) REFERENCES orders(order_id)
            )
        """)

        # 回测日志表
        self.execute("""
            CREATE TABLE IF NOT EXISTS backtestlog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                summary_id INTEGER,
                log_time TEXT NOT NULL,
                event TEXT NOT NULL,
                side TEXT,
                price REAL,
                contracts REAL,
                pnl_usd REAL,
                details TEXT,
                fee_rate REAL,
                fee_usd REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                trace_id TEXT,
                realized_pnl REAL
            )
        """)

        # 回测模拟K线表
        self.execute("""
            CREATE TABLE IF NOT EXISTS klines_1m_sim (
                open_time TEXT PRIMARY KEY,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL
            )
        """)

        # 回测交易日志表
        self.execute("""
            CREATE TABLE IF NOT EXISTS sim_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_time TEXT,
                event TEXT,
                side TEXT,
                price REAL,
                contracts REAL,
                pnl REAL,
                details TEXT,
                fee_rate REAL,
                fee_usd REAL,
                trace_id TEXT,
                realized_pnl REAL
            )
        """)

        # 创建索引
        self.execute("CREATE INDEX IF NOT EXISTS idx_klines_time ON klines_1m(open_time)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_indicators_time ON klines_1m_macd_smooth_ma(open_time)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_orders_trace ON orders(trace_id)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_backtestlog_time ON backtestlog(log_time)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_sim_log_time ON sim_log(log_time)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_klines_sim_time ON klines_1m_sim(open_time)")

        self._get_connection().commit()

    def close(self):
        """关闭数据库连接"""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


# 全局数据库实例
def get_db() -> Database:
    """获取数据库实例"""
    return Database()
