#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立的K线数据获取脚本
不依赖其他模块,可以独立运行

使用方法:
    python fetch_klines.py                    # 获取最新1000条
    python fetch_klines.py --limit 500        # 获取最新500条
    python fetch_klines.py --days 7           # 获取最近7天
    python fetch_klines.py --start "2024-01-01" --end "2024-01-10"  # 指定时间范围
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

# 可选依赖处理
try:
    from binance.cm_futures import CMFutures
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    print("警告: 未安装binance包,请运行: pip install python-binance")
    sys.exit(1)


class SimpleConfig:
    """简单的配置类,避免依赖config模块"""

    def __init__(self):
        # API配置
        self.BINANCE_API_KEY = ""
        self.BINANCE_API_SECRET = ""
        self.BINANCE_TESTNET = False
        self.BINANCE_PROXY = ""

        # 交易对配置
        self.SYMBOL = "BTCUSD_PERP"
        self.KLINE_INTERVAL = "1m"
        self.KLINE_LIMIT = 1000

    def load_from_env(self):
        """从环境变量加载配置"""
        import os
        self.BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
        self.BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', '')
        self.BINANCE_TESTNET = os.getenv('BINANCE_TESTNET', '0').lower() in ('1', 'true', 'yes')
        self.SYMBOL = os.getenv('SYMBOL', 'BTCUSD_PERP')
        self.KLINE_INTERVAL = os.getenv('KLINE_INTERVAL', '1m')
        self.KLINE_LIMIT = int(os.getenv('KLINE_LIMIT', '1000'))

    def load_from_file(self, config_file: str):
        """从文件加载配置"""
        try:
            with open(config_file, 'r') as f:
                data = json.load(f)
                for key, value in data.items():
                    if hasattr(self, key):
                        setattr(self, key, value)
        except FileNotFoundError:
            pass


class SimpleLogger:
    """简单的日志类,避免依赖logger模块"""

    @staticmethod
    def info(msg: str):
        print(f"[INFO] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}")

    @staticmethod
    def error(msg: str):
        print(f"[ERROR] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}", file=sys.stderr)

    @staticmethod
    def warning(msg: str):
        print(f"[WARNING] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}")

    @staticmethod
    def debug(msg: str):
        print(f"[DEBUG] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}")


class StandaloneKlineFetcher:
    """独立的K线数据获取器"""

    def __init__(self, config: SimpleConfig):
        self.config = config
        self.logger = SimpleLogger()

        # 初始化Binance客户端
        self.client = CMFutures(
            key=config.BINANCE_API_KEY,
            secret=config.BINANCE_API_SECRET
        )

        # 配置testnet
        if config.BINANCE_TESTNET:
            self.client.API_URL = 'https://testnet.binancefuture.com'
            self.logger.info("使用Binance测试网")
        else:
            self.client.API_URL = 'https://dapi.binance.com'
            self.logger.info("使用Binance主网")

        # 配置代理
        if config.BINANCE_PROXY:
            self.client.session.proxies = {
                'http': config.BINANCE_PROXY,
                'https': config.BINANCE_PROXY,
            }
            self.logger.info(f"使用代理: {config.BINANCE_PROXY}")

    def fetch_latest_klines(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取最新的K线数据"""
        try:
            limit = limit or self.config.KLINE_LIMIT
            self.logger.info(f"获取最新{limit}条K线...")

            klines = self.client.klines(
                symbol=self.config.SYMBOL,
                interval=self.config.KLINE_INTERVAL,
                limit=limit
            )

            result = []
            for kline in klines:
                result.append({
                    'open_time': kline[0],
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5]),
                    'close_time': kline[6],
                    'quote_volume': float(kline[7]),
                    'trades': int(kline[8]),
                    'taker_buy_base': float(kline[9]),
                    'taker_buy_quote': float(kline[10]),
                })

            self.logger.info(f"成功获取{len(result)}条K线")
            return result

        except Exception as e:
            self.logger.error(f"获取K线失败: {e}")
            return []

    def fetch_klines_by_time(
        self,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """获取指定时间范围的K线"""
        try:
            start_ts = int(start_time.timestamp() * 1000)
            end_ts = int(end_time.timestamp() * 1000) if end_time else None

            self.logger.info(f"获取K线: {start_time} 至 {end_time or '现在'}")

            klines = self.client.klines(
                symbol=self.config.SYMBOL,
                interval=self.config.KLINE_INTERVAL,
                startTime=start_ts,
                endTime=end_ts,
                limit=limit
            )

            result = []
            for kline in klines:
                result.append({
                    'open_time': kline[0],
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5]),
                    'close_time': kline[6],
                    'quote_volume': float(kline[7]),
                    'trades': int(kline[8]),
                    'taker_buy_base': float(kline[9]),
                    'taker_buy_quote': float(kline[10]),
                })

            self.logger.info(f"成功获取{len(result)}条K线")
            return result

        except Exception as e:
            self.logger.error(f"获取K线失败: {e}")
            return []

    def fetch_historical_klines(
        self,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """获取历史K线数据"""
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)

            self.logger.info(f"获取最近{days}天的历史K线...")

            all_klines = []
            current_start = start_time

            while current_start < end_time:
                klines = self.fetch_klines_by_time(
                    current_start,
                    end_time,
                    limit=1000
                )

                if not klines:
                    break

                all_klines.extend(klines)

                # 更新起始时间为最后一条K线的时间
                current_start = datetime.fromtimestamp(
                    klines[-1]['close_time'] / 1000
                ) + timedelta(seconds=1)

                self.logger.debug(f"已获取{len(all_klines)}条K线")

            self.logger.info(f"获取历史K线完成: {len(all_klines)}条")
            return all_klines

        except Exception as e:
            self.logger.error(f"获取历史K线失败: {e}")
            return []

    def save_to_json(self, klines: List[Dict[str, Any]], filename: str):
        """保存K线数据到JSON文件"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(klines, f, indent=2, ensure_ascii=False)
            self.logger.info(f"K线数据已保存到: {filename}")
        except Exception as e:
            self.logger.error(f"保存文件失败: {e}")

    def save_to_csv(self, klines: List[Dict[str, Any]], filename: str):
        """保存K线数据到CSV文件"""
        try:
            import csv

            if not klines:
                self.logger.warning("没有数据可保存")
                return

            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=klines[0].keys())
                writer.writeheader()
                writer.writerows(klines)

            self.logger.info(f"K线数据已保存到: {filename}")
        except Exception as e:
            self.logger.error(f"保存文件失败: {e}")

    def save_to_sqlite(
        self,
        klines: List[Dict[str, Any]],
        db_path: str,
        table_name: str = 'klines_1m',
        symbol: Optional[str] = None
    ):
        """
        保存K线数据到SQLite数据库

        Args:
            klines: K线数据列表
            db_path: 数据库文件路径
            table_name: 表名
            symbol: 交易对符号(用于创建带符号的表)
        """
        try:
            # 如果指定了symbol,在表名中包含symbol
            if symbol:
                # 将符号中的/替换为_
                safe_symbol = symbol.replace('/', '_')
                table_name = f"klines_1m_{safe_symbol}"

            # 连接数据库
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # 创建表
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
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
                    symbol TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建索引
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table_name}_open_time
                ON {table_name}(open_time)
            """)

            # 插入数据
            inserted_count = 0
            updated_count = 0

            for kline in klines:
                open_time = datetime.fromtimestamp(kline['open_time'] / 1000).isoformat()
                close_time = datetime.fromtimestamp(kline['close_time'] / 1000).isoformat()

                try:
                    cursor.execute(f"""
                        INSERT INTO {table_name} (
                            open_time, open, high, low, close, volume,
                            close_time, quote_volume, trades, taker_buy_base, taker_buy_quote, symbol
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        open_time,
                        kline['open'],
                        kline['high'],
                        kline['low'],
                        kline['close'],
                        kline['volume'],
                        close_time,
                        kline['quote_volume'],
                        kline['trades'],
                        kline['taker_buy_base'],
                        kline['taker_buy_quote'],
                        symbol or self.config.SYMBOL
                    ))
                    inserted_count += 1
                except sqlite3.IntegrityError:
                    # 数据已存在,更新
                    cursor.execute(f"""
                        UPDATE {table_name} SET
                            open = ?, high = ?, low = ?, close = ?, volume = ?,
                            close_time = ?, quote_volume = ?, trades = ?,
                            taker_buy_base = ?, taker_buy_quote = ?, symbol = ?
                        WHERE open_time = ?
                    """, (
                        kline['open'],
                        kline['high'],
                        kline['low'],
                        kline['close'],
                        kline['volume'],
                        close_time,
                        kline['quote_volume'],
                        kline['trades'],
                        kline['taker_buy_base'],
                        kline['taker_buy_quote'],
                        symbol or self.config.SYMBOL,
                        open_time
                    ))
                    updated_count += 1

            conn.commit()

            # 查询统计
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            total_count = cursor.fetchone()[0]

            conn.close()

            self.logger.info(f"数据已保存到SQLite: {db_path}")
            self.logger.info(f"  表名: {table_name}")
            self.logger.info(f"  新增: {inserted_count}条")
            self.logger.info(f"  更新: {updated_count}条")
            self.logger.info(f"  总计: {total_count}条")

        except Exception as e:
            self.logger.error(f"保存到SQLite失败: {e}", exc_info=True)

    def query_from_sqlite(
        self,
        db_path: str,
        table_name: str = 'klines_1m',
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        从SQLite数据库查询K线数据

        Args:
            db_path: 数据库文件路径
            table_name: 表名
            limit: 返回记录数

        Returns:
            K线数据列表
        """
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(f"""
                SELECT open_time, open, high, low, close, volume,
                       close_time, quote_volume, trades, taker_buy_base, taker_buy_quote
                FROM {table_name}
                ORDER BY open_time DESC
                LIMIT ?
            """, (limit,))

            rows = cursor.fetchall()
            result = []

            for row in rows:
                result.append({
                    'open_time': int(datetime.fromisoformat(row['open_time']).timestamp() * 1000),
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                    'volume': row['volume'],
                    'close_time': int(datetime.fromisoformat(row['close_time']).timestamp() * 1000),
                    'quote_volume': row['quote_volume'],
                    'trades': row['trades'],
                    'taker_buy_base': row['taker_buy_base'],
                    'taker_buy_quote': row['taker_buy_quote']
                })

            conn.close()

            self.logger.info(f"从{table_name}查询到{len(result)}条数据")
            return result

        except Exception as e:
            self.logger.error(f"查询SQLite失败: {e}")
            return []


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='独立的K线数据获取工具')
    parser.add_argument('--limit', type=int, help='获取最新N条K线')
    parser.add_argument('--days', type=int, help='获取最近N天的K线')
    parser.add_argument('--start', type=str, help='开始时间 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='结束时间 (YYYY-MM-DD)')
    parser.add_argument('--symbol', type=str, default='BTCUSD_PERP', help='交易对')
    parser.add_argument('--interval', type=str, default='1m', help='K线间隔')
    parser.add_argument('--output', type=str, help='输出文件 (JSON或CSV格式)')
    parser.add_argument('--db', type=str, help='SQLite数据库文件路径')
    parser.add_argument('--table', type=str, default='klines_1m', help='数据库表名')
    parser.add_argument('--config', type=str, help='配置文件路径')
    parser.add_argument('--testnet', action='store_true', help='使用测试网')
    parser.add_argument('--query', action='store_true', help='查询数据库中的最新数据')

    args = parser.parse_args()

    # 加载配置
    config = SimpleConfig()
    config.load_from_env()

    if args.config:
        config.load_from_file(args.config)

    # 命令行参数覆盖配置
    if args.symbol:
        config.SYMBOL = args.symbol
    if args.interval:
        config.KLINE_INTERVAL = args.interval
    if args.testnet:
        config.BINANCE_TESTNET = True

    # 创建获取器
    fetcher = StandaloneKlineFetcher(config)

    # 查询模式
    if args.query and args.db:
        fetcher.logger.info(f"查询数据库: {args.db}")
        klines = fetcher.query_from_sqlite(args.db, args.table, limit=args.limit or 10)

        if klines:
            print(f"\n{'='*60}")
            print(f"数据库查询结果")
            print(f"{'='*60}")
            print(f"数据库: {args.db}")
            print(f"表名: {args.table}")
            print(f"数据条数: {len(klines)}")
            print(f"时间范围: {datetime.fromtimestamp(klines[0]['open_time']/1000)} 至 {datetime.fromtimestamp(klines[-1]['open_time']/1000)}")
            print(f"最新价格: {klines[0]['close']}")
            print(f"{'='*60}\n")

            # 显示数据
            for kline in klines:
                print(f"  {datetime.fromtimestamp(kline['open_time']/1000)} | "
                      f"O:{kline['open']:.2f} H:{kline['high']:.2f} "
                      f"L:{kline['low']:.2f} C:{kline['close']:.2f} "
                      f"V:{kline['volume']:.2f}")

        return klines

    # 获取数据
    klines = []

    if args.start and args.end:
        # 指定时间范围
        start_time = datetime.strptime(args.start, '%Y-%m-%d')
        end_time = datetime.strptime(args.end, '%Y-%m-%d') if args.end else datetime.now()
        klines = fetcher.fetch_klines_by_time(start_time, end_time)
    elif args.days:
        # 指定天数
        klines = fetcher.fetch_historical_klines(days=args.days)
    else:
        # 获取最新N条
        klines = fetcher.fetch_latest_klines(limit=args.limit)

    if not klines:
        fetcher.logger.error("未获取到任何数据")
        sys.exit(1)

    # 显示统计信息
    print(f"\n{'='*60}")
    print(f"K线数据统计")
    print(f"{'='*60}")
    print(f"交易对: {config.SYMBOL}")
    print(f"K线间隔: {config.KLINE_INTERVAL}")
    print(f"数据条数: {len(klines)}")
    print(f"时间范围: {datetime.fromtimestamp(klines[0]['open_time']/1000)} 至 {datetime.fromtimestamp(klines[-1]['close_time']/1000)}")
    print(f"最新价格: {klines[-1]['close']}")
    print(f"{'='*60}\n")

    # 保存数据
    if args.db:
        # 保存到SQLite数据库
        fetcher.save_to_sqlite(klines, args.db, args.table, args.symbol)
    elif args.output:
        if args.output.endswith('.json'):
            fetcher.save_to_json(klines, args.output)
        elif args.output.endswith('.csv'):
            fetcher.save_to_csv(klines, args.output)
        else:
            # 默认使用JSON格式
            fetcher.save_to_json(klines, args.output)

    # 显示前5条和后5条数据
    print(f"\n前5条数据:")
    for kline in klines[:5]:
        print(f"  {datetime.fromtimestamp(kline['open_time']/1000)} | "
              f"O:{kline['open']:.2f} H:{kline['high']:.2f} "
              f"L:{kline['low']:.2f} C:{kline['close']:.2f} "
              f"V:{kline['volume']:.2f}")

    if len(klines) > 10:
        print(f"  ... (省略 {len(klines)-10} 条) ...")
        print(f"\n后5条数据:")
        for kline in klines[-5:]:
            print(f"  {datetime.fromtimestamp(kline['open_time']/1000)} | "
                  f"O:{kline['open']:.2f} H:{kline['high']:.2f} "
                  f"L:{kline['low']:.2f} C:{kline['close']:.2f} "
                  f"V:{kline['volume']:.2f}")

    return klines


if __name__ == '__main__':
    main()
