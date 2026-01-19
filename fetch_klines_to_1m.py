#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K线数据补充程序 - 只补充 klines_1m 表
- 从币安API获取已完结的分钟K线
- 保存到 klines_1m 表（原始数据）
- 每10秒查询一次，在01, 11, 21, 31, 41, 51秒执行
"""

import time
import sqlite3
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

# 必须在导入其他模块之前加载环境变量
load_dotenv()

from core.config import config
from core.logger import get_logger
from exchange_layer.binance_exchange import BinanceExchange

logger = get_logger('fetch_klines_1m')


def get_last_kline_time():
    """获取klines_1m表中最后一条K线的open_time"""
    try:
        conn = sqlite3.connect(
            config.DB_PATH,
            timeout=30.0,
            isolation_level=None
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 获取最后一条K线的open_time
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
            # 转换为datetime对象
            last_time = datetime.fromisoformat(last_time_str)
            # 如果没有时区信息，添加UTC时区
            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=timezone.utc)
            logger.info(f"数据库最后K线open_time: {last_time}")
            return last_time
        else:
            logger.warning("klines_1m表为空，返回1天前作为起始时间")
            return datetime.now(timezone.utc) - timedelta(days=1)

    except Exception as e:
        logger.error(f"获取最后K线时间失败: {e}")
        # 默认返回1天前
        return datetime.now(timezone.utc) - timedelta(days=1)


def fetch_klines_range(exchange, start_time, end_time):
    """
    从币安API获取K线数据（同时使用startTime和endTime）

    参考脚本：binance_klines_append_mysql.py
    关键：同时使用startTime和endTime，这样startTime不会被忽略

    Args:
        exchange: BinanceExchange实例
        start_time: 开始时间
        end_time: 结束时间

    Returns:
        list: K线数据列表，按时间升序排列
    """
    try:
        symbol = config.SYMBOL
        interval = '1m'

        logger.info(f"从币安API获取K线: {symbol} {interval}")
        logger.debug(f"时间范围: {start_time} ~ {end_time}")

        # 使用startTime和endTime参数
        klines = exchange.get_klines(
            symbol=symbol,
            interval=interval,
            limit=1000,
            start_time=start_time,
            end_time=end_time
        )

        # 过滤：只保留已完结的K线
        now = datetime.now(timezone.utc)
        finished_klines = []

        for kline in klines:
            if kline.close_time < now:
                finished_klines.append(kline)

        # 按时间升序排列
        finished_klines.sort(key=lambda x: x.close_time)

        logger.info(
            f"获取到 {len(klines)} 条K线，"
            f"其中 {len(finished_klines)} 条已完结"
        )
        return finished_klines

    except Exception as e:
        logger.error(f"获取K线数据失败: {e}")
        return []


def save_to_klines_1m(klines):
    """
    保存K线数据到 klines_1m 表（原始数据）

    Args:
        klines: K线对象列表

    Returns:
        int: 成功插入的数量
    """
    if not klines:
        return 0

    try:
        conn = sqlite3.connect(
            config.DB_PATH,
            timeout=30.0,
            isolation_level=None
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        cursor = conn.cursor()

        inserted_count = 0
        skipped_count = 0

        for kline in klines:
            try:
                # 准备插入数据（使用正确的列名）
                sql = """
                    INSERT OR REPLACE INTO klines_1m
                    (symbol, interval, open_time, open, high, low, close, volume,
                     close_time, quote_asset_volume, number_of_trades,
                     taker_buy_base, taker_buy_quote)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """

                # 格式化时间：去掉时区信息
                # open_time: 2025-12-19T21:13:00 (精确到秒)
                # close_time: 2025-12-19T21:13:59.999000 (精确到毫秒)
                open_time_str = kline.open_time.strftime('%Y-%m-%dT%H:%M:%S')
                close_time_str = kline.close_time.strftime('%Y-%m-%dT%H:%M:%S.%f')

                cursor.execute(sql, (
                    config.SYMBOL,
                    '1m',
                    open_time_str,
                    float(kline.open),
                    float(kline.high),
                    float(kline.low),
                    float(kline.close),
                    float(kline.volume),
                    close_time_str,
                    float(kline.quote_volume) if hasattr(kline, 'quote_volume') else 0,
                    int(kline.trades) if hasattr(kline, 'trades') else 0,
                    float(kline.taker_buy_base) if hasattr(kline, 'taker_buy_base') else 0,
                    float(kline.taker_buy_quote) if hasattr(kline, 'taker_buy_quote') else 0
                ))
                inserted_count += 1

            except sqlite3.IntegrityError:
                # 主键冲突，跳过
                skipped_count += 1
                continue
            except Exception as e:
                logger.warning(f"插入单条K线失败: {e}")
                continue

        conn.commit()
        conn.close()

        logger.info(
            f"保存完成: 插入 {inserted_count} 条，跳过 {skipped_count} 条"
        )
        return inserted_count

    except Exception as e:
        logger.error(f"保存到 klines_1m 失败: {e}")
        import traceback
        traceback.print_exc()
        return 0


def wait_for_next_query_time():
    """
    等待到下一个查询时间点
    查询时间：每分钟的01, 11, 21, 31, 41, 51秒
    """
    now = datetime.now()
    current_second = now.second

    # 计算下一个查询时间点
    if current_second < 1:
        next_second = 1
    elif current_second < 11:
        next_second = 11
    elif current_second < 21:
        next_second = 21
    elif current_second < 31:
        next_second = 31
    elif current_second < 41:
        next_second = 41
    elif current_second < 51:
        next_second = 51
    else:
        # 下一分钟的01秒
        next_second = 1
        now = now + timedelta(minutes=1)

    # 计算等待时间
    next_time = now.replace(second=next_second, microsecond=0)
    wait_seconds = (next_time - datetime.now()).total_seconds()

    if wait_seconds > 0:
        logger.debug(f"等待 {wait_seconds:.1f} 秒到 {next_time}")
        time.sleep(wait_seconds)
    else:
        # 如果已经过了，等待1秒后重新计算
        time.sleep(1)


def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("启动K线数据补充 - 只补充 klines_1m 表")
    logger.info("=" * 80)

    # 检查配置
    # K线数据从实盘获取，需要实盘API密钥
    api_key = config.BINANCE_LIVE_API_KEY
    if not api_key or api_key == 'your_live_api_key_here':
        logger.error("未配置币安实盘API密钥！")
        logger.error("请在 .env 文件中配置 BINANCE_LIVE_API_KEY")
        logger.error("和 BINANCE_LIVE_API_SECRET")
        return

    logger.info(f"交易对: {config.SYMBOL}")
    logger.info("交易所: 币安实盘（K线数据总是从实盘获取）")
    logger.info("查询间隔: 每10秒（在01, 11, 21, 31, 41, 51秒执行）")
    logger.info("目标表: klines_1m（原始K线数据）")
    logger.info("=" * 80)

    # 创建交易所连接
    # 注意：K线数据总是从实盘接口获取（真实市场数据）
    try:
        exchange = BinanceExchange(
            api_key=config.BINANCE_LIVE_API_KEY,
            api_secret=config.BINANCE_LIVE_API_SECRET,
            testnet=False  # 强制使用实盘获取K线数据
        )

        if not exchange.connect():
            logger.error("连接币安交易所失败！")
            return

        logger.info("已连接到币安交易所")

    except Exception as e:
        logger.error(f"连接交易所失败: {e}")
        return

   

    # 主循环
    query_count = 0
    total_fetched = 0

    try:
        while True:
            try:
                query_count += 1
                logger.info("")
                logger.info("=" * 80)
                logger.info(f"第 {query_count} 次查询")
                logger.info("=" * 80)
                 # 获取最后一条K线时间作为起点
                last_time = get_last_kline_time()
                # 从最后一条的下一条开始获取（+1分钟）
                start_time = last_time + timedelta(minutes=1)
                # 当前时间（不包含当前未完结的K线）
                now = datetime.now(timezone.utc)

                # 计算本次查询的结束时间
                # （上一分钟，确保K线已完结）
                # 例如：现在是10:00:45，则查询到10:00:00的K线
                end_time = now.replace(
                    second=0, microsecond=0
                ) - timedelta(minutes=1)

                # 检查是否有新数据需要获取
                if start_time >= end_time:
                    logger.info(
                        f"数据库已是最新 "
                        f"(最后时间: {last_time}, "
                        f"当前已完结: {end_time})"
                    )
                else:
                    logger.info(f"需要获取数据: {start_time} ~ {end_time}")

                    # 计算需要补充的总分钟数
                    total_minutes = int(
                        (end_time - start_time).total_seconds() / 60
                    )
                    logger.info(
                        f"需要补充约 {total_minutes} 条K线"
                    )

                    # 直接按1000条分批获取，每次最多获取1000条（1000分钟）
                    # 每次只请求1000分钟的数据：endTime = startTime + 1000分钟
                    current_start = start_time
                    batch_count = 0

                    while current_start < end_time:
                        batch_count += 1
                        logger.info("")
                        logger.info("=" * 60)
                        logger.info(
                            f"→ 批次 {batch_count}: 从 {current_start} 开始获取"
                        )

                        # 计算当前批次的结束时间：最多1000分钟后
                        # 但不能超过总的结束时间
                        current_end = min(
                            current_start + timedelta(minutes=1000),
                            end_time
                        )

                        logger.debug(
                            f"本次请求范围: {current_start} ~ {current_end}"
                        )

                        # 获取K线：每次只请求1000分钟的数据
                        new_klines = fetch_klines_range(
                            exchange, current_start, current_end
                        )

                        if not new_klines:
                            logger.info("未获取到新K线，获取完成")
                            break

                        # 保存到 klines_1m 表
                        saved_count = save_to_klines_1m(new_klines)

                        if saved_count > 0:
                            total_fetched += saved_count
                            logger.info(
                                f"✓ 批次 {batch_count} 完成，"
                                f"本批获取 {saved_count} 条，"
                                f"累计获取 {total_fetched} 条K线"
                            )

                            # 关键：使用当前批次的 current_end 作为下一批的起点
                            # 因为API返回的是 [startTime, endTime) 范围
                            # 最后一条的 close_time < endTime
                            # 所以下一批直接从 current_end 开始
                            current_start = current_end

                            logger.debug(
                                f"下一批从 {current_start} 开始"
                            )

                            # 如果获取数量少于1000，说明已到endTime
                            if saved_count < 1000:
                                logger.info(
                                    f"本批获取数量 {saved_count} < 1000，"
                                    f"数据获取完成"
                                )
                                break
                        else:
                            logger.warning("没有保存新的K线数据")
                            break

                        # 避免请求过快
                        time.sleep(0.12)

                # 等待下一个查询时间点
                logger.info("等待下次查询...")
                wait_for_next_query_time()

            except KeyboardInterrupt:
                logger.info("\n收到退出信号")
                break
            except Exception as e:
                logger.error(f"查询过程出错: {e}")
                import traceback
                traceback.print_exc()
                # 等待一段时间后继续
                time.sleep(10)

    finally:
        logger.info("=" * 80)
        logger.info(f"程序结束")
        logger.info(f"总查询次数: {query_count}")
        logger.info(f"总获取K线: {total_fetched} 条")
        logger.info("=" * 80)


if __name__ == '__main__':
    main()
