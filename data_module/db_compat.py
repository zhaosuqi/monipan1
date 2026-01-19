"""Database compatibility helpers for pymysql and sqlite3.

Provides helpers to detect sqlite connections and execute SQL using the
appropriate placehol  der  style (%s for pymysql, ? for sqlite3).
"""
from typing import Any, Iterable, Sequence


def _is_sqlite_conn(conn) -> bool:
    try:
        import sqlite3 as _sqlite
        return isinstance(conn, _sqlite.Connection)
    except Exception:
        return False


def adapt_sql_for_conn(sql: str, conn) -> str:
    if _is_sqlite_conn(conn):
        return sql.replace('%s', '?')
    return sql


def execute_one_compatible(conn, sql: str, params: Sequence[Any] = None):
    if params is None:
        params = ()
    cur = conn.cursor()
    try:
        cur.execute(adapt_sql_for_conn(sql, conn), params)
        return cur
    finally:
        try:
            cur.close()
        except Exception:
            pass


def execute_many_compatible(conn, sql: str, params_list: Iterable[Sequence[Any]]):
    cur = conn.cursor()
    try:
        cur.executemany(adapt_sql_for_conn(sql, conn), params_list)
        return cur
    finally:
        try:
            cur.close()
        except Exception:
            pass
