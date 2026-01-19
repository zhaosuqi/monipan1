#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库K线读取器 - 从SQLite数据库读取K线数据
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import sqlite3
import pandas as pd

from core.logger import get_logger
from core.config import config

logger = get_logger(__name__)


class DbKlineReader:
    """
    数据库K线读取器

    从SQLite数据库读取历史K线数据，用于回测和验证
    """

    def __init__(self, db_path: str, table_name: str = 'klines_1m'):
        """
        初始化数据库K线读取器

        Args:
            db_path: 数据库文件路径
            table_name: 表名
        """
        self.db_path = db_path
        self.table_name = table_name
        self.conn = None

        logger.info(f"初始化数据库K线读取器")
        logger.info(f"数据库路径: {db_path}")
        logger.info(f"数据表名: {table_name}")

        # 测试连接
        self._connect()
        self._verify_table()

    def _connect(self):
        """连接数据库"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # 返回字典格式
            logger.info("成功连接到数据库")
        except Exception as e:
            logger.error(f"连接数据库失败: {e}")
            raise

    def _verify_table(self):
        """验证表是否存在"""
        cursor = self.conn.cursor()
        cursor.execute(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='{self.table_name}'"
        )
        result = cursor.fetchone()

        if not result:
            logger.error(f"表 {self.table_name} 不存在")
            raise ValueError(f"表 {self.table_name} 不存在于数据库 {self.db_path}")

        logger.info(f"表 {self.table_name} 验证通过")

    def get_klines(
        self,
        limit: int = 1000,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取K线数据

        Args:
            limit: 获取数量
            symbol: 交易对（如果表包含多个交易对）

        Returns:
            K线数据列表
        """
        cursor = self.conn.cursor()

        # 构建查询
        if symbol:
            query = f"""
                SELECT * FROM {self.table_name}
                WHERE symbol = ?
                ORDER BY open_time ASC
                LIMIT ?
            """
            cursor.execute(query, (symbol, limit))
        else:
            query = f"""
                SELECT * FROM {self.table_name}
                ORDER BY open_time ASC
                LIMIT ?
            """
            cursor.execute(query, (limit,))

        rows = cursor.fetchall()

        # 转换为字典列表
        klines = []
        for row in rows:
            kline = dict(row)
            # 转换时间格式
            klines.append(kline)

        logger.debug(f"从数据库获取了 {len(klines)} 条K线数据")
        return klines

    def get_klines_by_time_range(
        self,
        start_time: str,
        end_time: str,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        按时间范围获取K线数据

        Args:
            start_time: 开始时间 (格式: '2024-01-01 00:00:00' 或 '2024-01-01T00:00:00')
            end_time: 结束时间 (格式: '2024-01-10 23:59:59' 或 '2024-01-10T23:59:59')
            symbol: 交易对

        Returns:
            K线数据列表
        """
        cursor = self.conn.cursor()

        # 标准化时间格式（保持空格，不转换为T，因为数据库存储格式是空格）
        start_time_normalized = start_time.replace('T', ' ')  # 将T转换为空格
        end_time_normalized = end_time.replace('T', ' ')      # 将T转换为空格

        # 构建查询
        if symbol:
            query = f"""
                SELECT * FROM {self.table_name}
                WHERE symbol = ?
                  AND open_time >= ?
                  AND open_time <= ?
                ORDER BY open_time ASC
            """
            cursor.execute(query, (symbol, start_time_normalized, end_time_normalized))
        else:
            query = f"""
                SELECT * FROM {self.table_name}
                WHERE open_time >= ?
                  AND open_time <= ?
                ORDER BY open_time ASC
            """
            cursor.execute(query, (start_time_normalized, end_time_normalized))

        rows = cursor.fetchall()

        # 转换为字典列表
        klines = [dict(row) for row in rows]

        logger.info(f"按时间范围获取K线: {start_time} 至 {end_time}")
        logger.info(f"获取到 {len(klines)} 条K线数据")

        return klines

    def get_warmup_data(self, days: int = 200) -> List[Dict[str, Any]]:
        """
        获取预热数据（用于指标计算）

        Args:
            days: 预热天数

        Returns:
            历史K线数据列表
        """
        # 计算开始时间
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)

        start_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end_time.strftime('%Y-%m-%d %H:%M:%S')

        logger.info(f"获取预热数据: {days}天 ({start_str} 至 {end_str})")

        return self.get_klines_by_time_range(start_str, end_str)

    def get_total_count(self, symbol: Optional[str] = None) -> int:
        """
        获取总记录数

        Args:
            symbol: 交易对

        Returns:
            总记录数
        """
        cursor = self.conn.cursor()

        if symbol:
            cursor.execute(
                f"SELECT COUNT(*) FROM {self.table_name} WHERE symbol = ?",
                (symbol,)
            )
        else:
            cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}")

        count = cursor.fetchone()[0]
        return count

    def get_time_range(self, symbol: Optional[str] = None) -> str:
        """
        获取时间范围

        Args:
            symbol: 交易对

        Returns:
            时间范围字符串
        """
        cursor = self.conn.cursor()

        if symbol:
            cursor.execute(
                f"SELECT MIN(open_time), MAX(open_time) FROM {self.table_name} WHERE symbol = ?",
                (symbol,)
            )
        else:
            cursor.execute(
                f"SELECT MIN(open_time), MAX(open_time) FROM {self.table_name}"
            )

        row = cursor.fetchone()
        if row and row[0] and row[1]:
            return f"{row[0]} 至 {row[1]}"
        return "无数据"

    def get_latest_kline(self, symbol: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        获取最新一条K线

        Args:
            symbol: 交易对

        Returns:
            最新K线数据
        """
        cursor = self.conn.cursor()

        if symbol:
            query = f"""
                SELECT * FROM {self.table_name}
                WHERE symbol = ?
                ORDER BY open_time DESC
                LIMIT 1
            """
            cursor.execute(query, (symbol,))
        else:
            query = f"""
                SELECT * FROM {self.table_name}
                ORDER BY open_time DESC
                LIMIT 1
            """
            cursor.execute(query)

        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def get_ohlcv(
        self,
        limit: int = 1000,
        symbol: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取OHLCV格式的DataFrame（用于指标计算）

        Args:
            limit: 获取数量
            symbol: 交易对

        Returns:
            pandas DataFrame
        """
        klines = self.get_klines(limit=limit, symbol=symbol)

        if not klines:
            return pd.DataFrame()

        # 转换为DataFrame
        df = pd.DataFrame(klines)

        # 确保列名正确
        column_mapping = {
            'open_time': 'open_time',
            'open': 'open',
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'volume': 'volume'
        }

        # 重命名列
        df = df.rename(columns=column_mapping)

        # 转换时间格式
        if 'open_time' in df.columns:
            df['datetime'] = pd.to_datetime(df['open_time'])

        return df

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            logger.info("数据库连接已关闭")

    def __del__(self):
        """析构函数"""
        self.close()
