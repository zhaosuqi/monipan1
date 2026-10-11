#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K线数据连续性检查与修复脚本

功能:
1. 检查最近半年(默认180天) klines_1m 表数据的连续性，避免数据同步不一致
2. 发现不连续(相邻记录间隔超过1分钟)时，定位最早的断点
3. 删除断点之后的所有K线数据，同时删除 klines_1m_macd_smooth_ma 表中
   对应时间的数据，并输出日志
4. 复用 realtime_kline_sync.py 的REST补数逻辑，从断点处重新获取数据补齐
   (不监听WebSocket)
5. 补数完成后调用 sync_macd_indicators.py 重新计算MACD指标

原理说明:
    MACD/KDJ等指标是基于连续1分钟序列递推计算的，断档之后已写入的指标
    是基于错误(ffill桥接)序列计算的，因此发现断点后需要删除断点之后的
    全部数据，重新拉取K线并重算指标，才能保证两表数据一致。

使用方法:
    python data/kline_continuity_repair.py              # 检查并自动修复
    python data/kline_continuity_repair.py --dry-run    # 仅检查，不删除不修复
    python data/kline_continuity_repair.py --days 90    # 只检查最近90天

所有时间使用UTC时间
"""

import argparse
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from core.config import config
from core.logger import get_logger

# 币安 REST API
from binance.cm_futures import CMFutures

logger = get_logger('kline_continuity_repair')

# 默认检查最近180天(半年)的数据
DEFAULT_CHECK_DAYS = 180
# 相邻K线允许的间隔容忍(秒)，1分钟K线理论间隔为60秒
GAP_TOLERANCE_SECONDS = 61


class KlineContinuityRepair:
    """K线连续性检查与修复器"""

    def __init__(self):
        self.db_path = config.DB_PATH
        self.symbol = config.SYMBOL
        self.interval = '1m'

        # 初始化币安客户端 (仅用于REST API补数据，不使用WebSocket)
        self.client = CMFutures(
            key=config.BINANCE_API_KEY,
            secret=config.BINANCE_API_SECRET
        )

        logger.info(f"初始化完成 - 交易对: {self.symbol}, 数据库: {self.db_path}")

    # ------------------------------------------------------------------
    # 以下方法复制自 realtime_kline_sync.py (REST补数据部分，不含WebSocket)
    # ------------------------------------------------------------------

    def get_db_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,
            isolation_level=None
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        return conn

    def get_last_kline_time(self) -> Optional[datetime]:
        """获取klines_1m表最后一条数据的open_time (UTC时间)"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT open_time
                FROM klines_1m
                ORDER BY open_time DESC
                LIMIT 1
            """)

            row = cursor.fetchone()
            conn.close()

            if row:
                last_time_str = row['open_time']
                # 解析ISO格式时间字符串
                last_time = datetime.fromisoformat(last_time_str)
                # 确保是UTC时间
                if last_time.tzinfo is None:
                    last_time = last_time.replace(tzinfo=timezone.utc)
                logger.info(f"数据库最后K线时间 (open_time): {last_time}")
                return last_time
            else:
                logger.warning("klines_1m表为空")
                return None

        except Exception as e:
            logger.error(f"获取最后K线时间失败: {e}")
            return None

    def fetch_klines_rest(
        self,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        通过REST API获取K线数据

        Args:
            start_time: 开始时间 (UTC)
            end_time: 结束时间 (UTC)，默认为当前时间
            limit: 每次请求数量限制

        Returns:
            K线数据列表
        """
        try:
            params = {
                'symbol': self.symbol,
                'interval': self.interval,
                'limit': limit,
                'startTime': int(start_time.timestamp() * 1000)
            }

            if end_time:
                params['endTime'] = int(end_time.timestamp() * 1000)

            logger.debug(f"REST请求K线: {start_time} ~ {end_time or 'now'}")

            klines = self.client.klines(**params)

            result = []
            for kline in klines:
                # 解析K线数据
                open_time_utc = datetime.fromtimestamp(kline[0] / 1000, tz=timezone.utc)
                close_time_utc = datetime.fromtimestamp(kline[6] / 1000, tz=timezone.utc)

                result.append({
                    'symbol': self.symbol,
                    'interval': self.interval,
                    'open_time': open_time_utc,
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5]),
                    'close_time': close_time_utc,
                    'quote_asset_volume': float(kline[7]),
                    'number_of_trades': int(kline[8]),
                    'taker_buy_base': float(kline[9]),
                    'taker_buy_quote': float(kline[10]),
                })

            logger.debug(f"获取到 {len(result)} 条K线")
            return result

        except Exception as e:
            logger.error(f"REST获取K线失败: {e}")
            return []

    def save_klines_to_db(self, klines: List[Dict[str, Any]]) -> int:
        """
        保存K线数据到klines_1m表

        Args:
            klines: K线数据列表

        Returns:
            成功插入的数量
        """
        if not klines:
            return 0

        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            inserted_count = 0

            for kline in klines:
                try:
                    # 格式化时间为ISO格式
                    open_time_str = kline['open_time'].strftime('%Y-%m-%dT%H:%M:%S')
                    close_time_str = kline['close_time'].strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]

                    sql = """
                        INSERT OR REPLACE INTO klines_1m
                        (symbol, interval, open_time, open, high, low, close, volume,
                         close_time, quote_asset_volume, number_of_trades,
                         taker_buy_base, taker_buy_quote)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """

                    cursor.execute(sql, (
                        kline['symbol'],
                        kline['interval'],
                        open_time_str,
                        kline['open'],
                        kline['high'],
                        kline['low'],
                        kline['close'],
                        kline['volume'],
                        close_time_str,
                        kline['quote_asset_volume'],
                        kline['number_of_trades'],
                        kline['taker_buy_base'],
                        kline['taker_buy_quote'],
                    ))
                    inserted_count += 1

                except sqlite3.IntegrityError:
                    # 已存在，跳过
                    continue
                except Exception as e:
                    logger.warning(f"插入单条K线失败: {e}")
                    continue

            conn.commit()
            conn.close()

            if inserted_count > 0:
                logger.info(f"✓ 已保存 {inserted_count} 条K线到 klines_1m 表")

            return inserted_count

        except Exception as e:
            logger.error(f"保存K线到数据库失败: {e}")
            return 0

    def sync_historical_klines(self) -> int:
        """
        同步历史K线数据 (从数据库最后一条到当前时间)

        Returns:
            同步的K线数量
        """
        logger.info("=" * 50)
        logger.info("开始同步历史K线数据...")

        # 获取最后一条K线时间
        last_time = self.get_last_kline_time()

        if last_time is None:
            logger.error("klines_1m表为空，无法确定补数起点，终止补数")
            return 0

        # 计算需要同步的时间范围
        # 从最后一条K线的下一分钟开始
        start_time = last_time + timedelta(minutes=1)
        end_time = datetime.now(timezone.utc)

        # 如果开始时间已经超过当前时间，不需要同步
        if start_time >= end_time:
            logger.info("数据已是最新，无需同步历史数据")
            return 0

        logger.info(f"同步时间范围: {start_time} ~ {end_time}")

        # 计算需要获取的分钟数
        duration_minutes = int((end_time - start_time).total_seconds() / 60)
        logger.info(f"需要同步约 {duration_minutes} 分钟的数据")

        total_synced = 0
        current_start = start_time

        # 分批获取 (每次最多1000条)
        while current_start < end_time:
            # 强制分片：每次请求 900 分钟范围内的数据
            # 将步长设为 900 (小于 limit 1000)，确保在 limit 限制内能取完该时间段的所有数据
            # 这样可以避免因 limit 截断导致的边界数据丢失问题
            batch_end_time = current_start + timedelta(minutes=900)
            # 确保不超出总结束时间
            request_end_time = min(batch_end_time, end_time)

            klines = self.fetch_klines_rest(
                start_time=current_start,
                end_time=request_end_time,
                limit=1000
            )

            if not klines:
                # 当前时间窗口无数据，直接跳过该窗口
                current_start = request_end_time
                continue

            # 过滤已完成的K线 (close_time < 当前时间)
            now = datetime.now(timezone.utc)
            finished_klines = [
                k for k in klines
                if k['close_time'] < now
            ]

            if not finished_klines:
                # 获取到的都是未完成的（可能是最新的），结束同步
                break

            # 保存到数据库
            synced = self.save_klines_to_db(finished_klines)
            total_synced += synced

            # 更新下一批的开始时间
            last_kline_time = finished_klines[-1]['open_time']
            next_start_time = last_kline_time + timedelta(minutes=1)

            # 如果 API 返回的数据跳跃了，取 max 以确保进度向前
            if next_start_time > current_start:
                current_start = next_start_time
            else:
                # 防止死循环：如果返回的数据都在 current_start 之前（异常情况），强制推进
                current_start = request_end_time

            # 只有当确实到了总结束时间才停止，不能因为单次返回少于1000就停止
            if current_start >= end_time:
                break

            # 避免请求过快
            time.sleep(0.1)

        logger.info(f"历史K线同步完成，共同步 {total_synced} 条")
        logger.info("=" * 50)

        return total_synced

    # ------------------------------------------------------------------
    # 连续性检查与修复
    # ------------------------------------------------------------------

    def find_gaps(self, days: int) -> List[Tuple[datetime, datetime]]:
        """
        检查最近days天内 klines_1m 数据的连续性

        Args:
            days: 检查最近多少天的数据

        Returns:
            断点列表 [(断点前最后一条时间, 断点后第一条时间), ...]，按时间升序
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)
        # open_time 存储为ISO字符串，统一成空格格式再比较，兼容 'T'/空格 两种格式
        since_str = since.strftime('%Y-%m-%d %H:%M:%S')

        logger.info(f"检查范围: {since} (UTC) 至今，共 {days} 天")

        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT open_time
            FROM klines_1m
            WHERE REPLACE(open_time, 'T', ' ') >= ?
            ORDER BY open_time ASC
        """, (since_str,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            logger.warning(f"最近 {days} 天内 klines_1m 没有数据")
            return []

        logger.info(f"加载了 {len(rows)} 条K线时间记录，开始连续性检查...")

        times = []
        for row in rows:
            t = datetime.fromisoformat(row['open_time'])
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            times.append(t)

        gaps = []
        tolerance = timedelta(seconds=GAP_TOLERANCE_SECONDS)
        for prev_t, cur_t in zip(times, times[1:]):
            if cur_t - prev_t > tolerance:
                gaps.append((prev_t, cur_t))

        return gaps

    def _table_exists(self, cursor: sqlite3.Cursor, table: str) -> bool:
        """检查表是否存在"""
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        )
        return cursor.fetchone() is not None

    def delete_after_breakpoint(self, breakpoint_time: datetime, dry_run: bool = False) -> Tuple[int, int]:
        """
        删除断点之后(含断点后第一条)的所有数据

        同时删除:
        - klines_1m 表中 open_time >= breakpoint_time 的记录
        - klines_1m_macd_smooth_ma 表中 open_time >= breakpoint_time 的记录
          (即 sync_macd_indicators.py 写入库的对应时间数据)

        Args:
            breakpoint_time: 断点之后最早一条记录的时间 (UTC)
            dry_run: 为True时只统计不实际删除

        Returns:
            (删除的klines_1m条数, 删除的macd表条数)
        """
        # 统一成空格格式比较，兼容两种存储格式 ('T' / 空格)
        bp_str = breakpoint_time.strftime('%Y-%m-%d %H:%M:%S')

        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            # klines_1m
            cursor.execute(
                "SELECT COUNT(*) FROM klines_1m WHERE REPLACE(open_time, 'T', ' ') >= ?",
                (bp_str,)
            )
            klines_count = cursor.fetchone()[0]

            # klines_1m_macd_smooth_ma
            macd_count = 0
            macd_table_exists = self._table_exists(cursor, 'klines_1m_macd_smooth_ma')
            if macd_table_exists:
                cursor.execute(
                    "SELECT COUNT(*) FROM klines_1m_macd_smooth_ma WHERE REPLACE(open_time, 'T', ' ') >= ?",
                    (bp_str,)
                )
                macd_count = cursor.fetchone()[0]
            else:
                logger.warning("klines_1m_macd_smooth_ma 表不存在，跳过指标数据删除")

            if dry_run:
                logger.info(
                    f"[dry-run] 将删除 klines_1m 中 {klines_count} 条记录 "
                    f"(open_time >= {breakpoint_time})"
                )
                logger.info(
                    f"[dry-run] 将删除 klines_1m_macd_smooth_ma 中 {macd_count} 条记录 "
                    f"(open_time >= {breakpoint_time})"
                )
                return klines_count, macd_count

            # 实际删除
            cursor.execute(
                "DELETE FROM klines_1m WHERE REPLACE(open_time, 'T', ' ') >= ?",
                (bp_str,)
            )
            deleted_klines = cursor.rowcount
            conn.commit()
            logger.warning(
                f"✗ 已删除 klines_1m 中断点之后的数据 {deleted_klines} 条 "
                f"(open_time >= {breakpoint_time})"
            )

            deleted_macd = 0
            if macd_table_exists:
                cursor.execute(
                    "DELETE FROM klines_1m_macd_smooth_ma WHERE REPLACE(open_time, 'T', ' ') >= ?",
                    (bp_str,)
                )
                deleted_macd = cursor.rowcount
                conn.commit()
            logger.warning(
                f"✗ 已删除 klines_1m_macd_smooth_ma 中断点之后的数据 {deleted_macd} 条 "
                f"(open_time >= {breakpoint_time})"
            )

            return deleted_klines, deleted_macd

        except Exception as e:
            logger.error(f"删除断点之后数据失败: {e}")
            raise
        finally:
            conn.close()

    def run_macd_sync(self) -> bool:
        """
        调用 sync_macd_indicators.py 重新计算指标 (单次执行模式)

        Returns:
            是否执行成功
        """
        script_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'sync_macd_indicators.py'
        )

        logger.info("=" * 50)
        logger.info(f"调用 sync_macd_indicators.py 重新计算指标: {script_path}")

        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=7200  # 大数据量重算可能较慢，超时2小时
            )

            if result.stdout:
                for line in result.stdout.strip().splitlines():
                    logger.info(f"[sync_macd] {line}")
            if result.returncode != 0:
                logger.error(f"sync_macd_indicators.py 执行失败 (code={result.returncode})")
                if result.stderr:
                    for line in result.stderr.strip().splitlines():
                        logger.error(f"[sync_macd] {line}")
                return False

            logger.info("✓ sync_macd_indicators.py 指标重算完成")
            return True

        except subprocess.TimeoutExpired:
            logger.error("sync_macd_indicators.py 执行超时(2小时)")
            return False
        except Exception as e:
            logger.error(f"调用 sync_macd_indicators.py 失败: {e}")
            return False

    def repair(self, days: int, dry_run: bool = False) -> bool:
        """
        执行检查与修复主流程

        Args:
            days: 检查最近多少天的数据
            dry_run: 为True时只检查不修复

        Returns:
            数据是否连续(或修复成功)
        """
        logger.info("=" * 60)
        logger.info(f"开始检查 klines_1m 数据连续性 (最近 {days} 天)")
        logger.info("=" * 60)

        gaps = self.find_gaps(days)

        if not gaps:
            logger.info(f"✓ 最近 {days} 天数据连续，无不一致情况，无需修复")
            return True

        # 输出所有断点日志
        logger.warning(f"检测到 {len(gaps)} 处数据不连续 (间隔超过1分钟):")
        max_log = 20
        for i, (prev_t, next_t) in enumerate(gaps[:max_log], 1):
            gap_minutes = (next_t - prev_t).total_seconds() / 60
            logger.warning(
                f"  断点{i}: {prev_t} -> {next_t} "
                f"(缺失约 {int(gap_minutes) - 1} 分钟)"
            )
        if len(gaps) > max_log:
            logger.warning(f"  ... 其余 {len(gaps) - max_log} 处断点省略")

        # 找到最早的不连续记录
        earliest_prev, earliest_next = gaps[0]
        gap_minutes = (earliest_next - earliest_prev).total_seconds() / 60
        logger.warning("-" * 60)
        logger.warning(
            f"最早断点: {earliest_prev} -> {earliest_next}, "
            f"间隔 {gap_minutes:.0f} 分钟"
        )
        logger.warning(
            f"修复策略: 删除断点之后最早数据({earliest_next})起的所有数据, "
            f"重新从币安拉取并重算指标"
        )
        logger.warning("-" * 60)

        if dry_run:
            self.delete_after_breakpoint(earliest_next, dry_run=True)
            logger.info("[dry-run] 检查完成，未执行实际修复")
            return False

        # 1. 删除断点之后的数据 (klines_1m + klines_1m_macd_smooth_ma)
        deleted_klines, deleted_macd = self.delete_after_breakpoint(earliest_next)
        logger.warning(
            f"删除完成: klines_1m {deleted_klines} 条, "
            f"klines_1m_macd_smooth_ma {deleted_macd} 条"
        )

        # 2. 从断点处重新获取数据补齐 (REST，不启用WebSocket)
        #    删除后 klines_1m 最后一条即为断点前的 earliest_prev
        synced = self.sync_historical_klines()
        logger.info(f"补数完成，共同步 {synced} 条K线")

        # 3. 调用 sync_macd_indicators.py 重新计算指标
        macd_ok = self.run_macd_sync()

        # 4. 修复后再次校验连续性
        logger.info("修复后再次校验数据连续性...")
        remaining_gaps = self.find_gaps(days)
        if remaining_gaps:
            logger.error(
                f"修复后仍存在 {len(remaining_gaps)} 处断点，"
                f"最早: {remaining_gaps[0][0]} -> {remaining_gaps[0][1]} "
                f"(可能是币安侧该时段确实无数据)"
            )
            return False

        if macd_ok:
            logger.info("✓ 数据连续性修复完成，两表已重新同步")
        else:
            logger.error("K线已补齐，但指标重算失败，请手动执行: python data/sync_macd_indicators.py")

        return macd_ok


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="K线数据连续性检查与修复工具")
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_CHECK_DAYS,
        help=f"检查最近多少天的数据 (默认: {DEFAULT_CHECK_DAYS} 天，即半年)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅检查并输出日志，不执行删除/补数/重算"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("K线数据连续性检查与修复工具")
    print("=" * 60)
    print(f"交易对: {config.SYMBOL}")
    print(f"数据库: {config.DB_PATH}")
    print(f"检查范围: 最近 {args.days} 天")
    print(f"模式: {'仅检查(dry-run)' if args.dry_run else '检查并修复'}")
    print("=" * 60)

    repair = KlineContinuityRepair()
    ok = repair.repair(days=args.days, dry_run=args.dry_run)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    # 确保logger不向 root 传播，以防第三方库配置了stderr handler
    # 从而导致 debug 日志泄漏到 error.log
    logger.propagate = False
    main()
