#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时K线数据补充脚本
- 从币安API获取已完结的分钟K线
- 先保存到 klines_1m 表（原始数据）
- 然后计算指标保存到 klines_1m_macd_smooth_ma 表
- 每10秒查询一次，在01, 11, 21, 31, 41, 51秒执行
"""

import time
import sqlite3
from datetime import datetime, timedelta

from dotenv import load_dotenv

# 必须在导入其他模块之前加载环境变量
load_dotenv()

from core.config import config
from core.logger import get_logger
from data_module.indicator_calculator import IndicatorCalculator
from exchange_layer.binance_exchange import BinanceExchange

logger = get_logger('fetch_realtime')


def get_last_kline_time():
    """获取klines_1m表中最后一条K线的时间"""
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

        # 获取最后一条K线的时间
        cursor.execute("""
            SELECT close_time
            FROM klines_1m
            ORDER BY close_time DESC
            LIMIT 1
        """)

        row = cursor.fetchone()
        conn.close()

        if row:
            last_time_str = row['close_time']
            # 转换为datetime对象
            last_time = datetime.fromisoformat(last_time_str)
            logger.info(f"数据库最后K线时间: {last_time}")
            return last_time
        else:
            logger.warning("klines_1m表为空，返回1天前作为起始时间")
            return datetime.now() - timedelta(days=1)

    except Exception as e:
        logger.error(f"获取最后K线时间失败: {e}")
        # 默认返回1天前
        return datetime.now() - timedelta(days=1)


def fetch_new_klines(exchange, start_time, end_time=None):
    """
    从币安API获取K线数据

    Args:
        exchange: BinanceExchange实例
        start_time: 开始时间
        end_time: 结束时间（None表示到当前）

    Returns:
        list: K线数据列表
    """
    try:
        symbol = config.SYMBOL
        interval = '1m'

        logger.info(f"从币安API获取K线: {symbol} {interval}")
        logger.info(f"时间范围: {start_time} ~ {end_time or '现在'}")

        # 计算需要获取的K线数量
        if end_time:
            duration_minutes = int(
                (end_time - start_time).total_seconds() / 60
            )
        else:
            duration_minutes = int(
                (datetime.now() - start_time).total_seconds() / 60
            )

        # 限制每次最多获取1000条
        limit = min(duration_minutes + 1, 1000)

        # 获取K线数据
        klines = exchange.get_klines(
            symbol=symbol,
            interval=interval,
            limit=limit
        )

        # 过滤：只保留已完结的K线（close_time在当前时间之前）
        now = datetime.now()
        finished_klines = []

        for kline in klines:
            # 检查K线是否已完结
            if kline.close_time < now:
                # 检查是否在指定时间范围内
                if kline.close_time >= start_time:
                    if end_time is None or kline.close_time <= end_time:
                        finished_klines.append(kline)

        logger.info(
            f"获取到 {len(klines)} 条K线，"
            f"其中 {len(finished_klines)} 条已完结且符合条件"
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

                cursor.execute(sql, (
                    config.SYMBOL,
                    '1m',
                    kline.open_time.isoformat(timespec='seconds'),
                    float(kline.open),
                    float(kline.high),
                    float(kline.low),
                    float(kline.close),
                    float(kline.volume),
                    kline.close_time.isoformat(),
                    float(kline.quote_volume) if hasattr(kline, 'quote_volume') else 0,
                    int(kline.trades) if hasattr(kline, 'trades') else 0,
                    float(kline.taker_buy_base) if hasattr(kline, 'taker_buy_base') else 0,
                    float(kline.taker_buy_quote) if hasattr(kline, 'taker_buy_quote') else 0
                ))
                inserted_count += 1

            except sqlite3.IntegrityError:
                # 主键冲突，跳过
                continue
            except Exception as e:
                logger.warning(f"插入单条K线失败: {e}")
                continue

        conn.commit()
        conn.close()

        logger.info(f"✓ 已保存 {inserted_count} 条K线到 klines_1m 表")
        return inserted_count

    except Exception as e:
        logger.error(f"保存到 klines_1m 失败: {e}")
        import traceback
        traceback.print_exc()
        return 0


def load_klines_from_db(start_time=None, end_time=None, limit=None):
    """
    从 klines_1m 表加载K线数据

    Args:
        start_time: 开始时间
        end_time: 结束时间
        limit: 限制数量

    Returns:
        list: K线数据字典列表
    """
    try:
        from data_module.db_kline_reader import DbKlineReader

        reader = DbKlineReader(
            db_path=config.DB_PATH,
            table_name='klines_1m'
        )

        # 根据参数获取数据
        if start_time and end_time:
            klines = reader.get_klines_by_time_range(
                start_time=start_time.strftime('%Y-%m-%d %H:%M:%S'),
                end_time=end_time.strftime('%Y-%m-%d %H:%M:%S')
            )
        elif limit:
            klines = reader.get_klines(limit=limit)
        else:
            klines = reader.get_klines(limit=1000)

        logger.info(f"从 klines_1m 表加载了 {len(klines)} 条K线")

        # 转换为字典格式（兼容 IndicatorCalculator）
        result = []
        for kline in klines:
            result.append({
                'open_time': kline.get('open_time') or kline.get('close_time'),
                'open': float(kline.get('open', 0)),
                'high': float(kline.get('high', 0)),
                'low': float(kline.get('low', 0)),
                'close': float(kline.get('close', 0)),
                'volume': float(kline.get('volume', 0))
            })

        return result

    except Exception as e:
        logger.error(f"从数据库加载K线失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def calculate_and_save_indicators(start_time, end_time):
    """
    计算指定时间范围的指标并保存

    Args:
        start_time: 开始时间
        end_time: 结束时间

    Returns:
        int: 成功计算的K线数量
    """
    try:
        import pandas as pd

        logger.info(f"计算指标: {start_time} ~ {end_time}")

        # 1. 获取预热数据（向前200天）
        warmup_start = start_time - timedelta(days=200)
        logger.info(f"加载预热数据: {warmup_start} ~ {start_time}")

        warmup_data = load_klines_from_db(
            start_time=warmup_start,
            end_time=start_time
        )

        if not warmup_data:
            logger.error("未能获取到足够的预热数据！")
            return 0

        logger.info(f"获取到 {len(warmup_data)} 条预热数据")

        # 2. 初始化指标计算器
        calculator = IndicatorCalculator()
        warm_df = pd.DataFrame(warmup_data)
        calculator.seed_warm_data(warm_df)
        logger.info("✓ 指标计算器初始化完成")

        # 3. 获取需要计算的数据
        target_data = load_klines_from_db(
            start_time=start_time,
            end_time=end_time
        )

        if not target_data:
            logger.info("没有需要计算的数据")
            return 0

        logger.info(f"开始计算 {len(target_data)} 条K线的指标...")

        # 4. 逐条计算指标
        df = pd.DataFrame(target_data)
        df = df.sort_values('open_time').reset_index(drop=True)
        sorted_klines = df.to_dict('records')

        # 准备数据库连接
        conn = sqlite3.connect(
            config.DB_PATH,
            timeout=30.0,
            isolation_level=None
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        cursor = conn.cursor()

        # 获取表结构
        cursor.execute("PRAGMA table_info(klines_1m_macd_smooth_ma)")
        columns_info = cursor.fetchall()
        existing_columns = [col[1] for col in columns_info]

        calculated_count = 0
        for i, kline in enumerate(sorted_klines):
            try:
                # 计算指标（使用 IndicatorCalculator 的 update 方法）
                indicators = calculator.update(kline)

                # 合并数据
                result = {**kline, **indicators}

                # 保存到数据库
                columns = []
                placeholders = []
                values = []

                base_columns = [
                    'open_time', 'open', 'high', 'low', 'close', 'volume'
                ]

                for col in base_columns:
                    if col in result and col in existing_columns:
                        columns.append(col)
                        placeholders.append('?')
                        value = result[col]
                        if isinstance(value, datetime):
                            value = value.strftime('%Y-%m-%d %H:%M:%S')
                        values.append(value)

                # 添加指标列
                for col, value in result.items():
                    if col not in base_columns and col in existing_columns:
                        columns.append(col)
                        placeholders.append('?')
                        if isinstance(value, float) and value != value:
                            value = None
                        values.append(value)

                if columns:
                    columns_str = ', '.join(columns)
                    placeholders_str = ', '.join(placeholders)
                    sql = (
                        f"INSERT OR REPLACE INTO klines_1m_macd_smooth_ma "
                        f"({columns_str}) VALUES ({placeholders_str})"
                    )
                    cursor.execute(sql, values)
                    calculated_count += 1

                # 每100条输出一次进度
                if (i + 1) % 100 == 0:
                    logger.info(f"已计算 {i + 1}/{len(sorted_klines)} 条")

            except Exception as e:
                logger.warning(f"计算第 {i+1} 条K线失败: {e}")
                continue

        conn.commit()
        conn.close()

        logger.info(f"✓ 指标计算完成，共处理 {calculated_count} 条K线")
        return calculated_count

    except Exception as e:
        logger.error(f"计算指标失败: {e}")
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
    logger.info("启动实时K线数据补充")
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

    # 获取最后一条K线时间作为起点
    last_time = get_last_kline_time()

    # 主循环
    query_count = 0
    total_fetched = 0
    total_calculated = 0

    try:
        while True:
            try:
                query_count += 1
                logger.info("")
                logger.info("=" * 80)
                logger.info(f"第 {query_count} 次查询")
                logger.info("=" * 80)

                # 当前时间（不包含当前未完结的K线）
                now = datetime.now()

                # 计算本次查询的结束时间
                # （上一分钟，确保K线已完结）
                # 例如：现在是10:00:45，则查询到10:00:00的K线
                end_time = now.replace(
                    second=0, microsecond=0
                ) - timedelta(minutes=1)

                # 检查是否有新数据需要获取
                if last_time >= end_time:
                    logger.info(
                        f"数据库已是最新 "
                        f"(最后时间: {last_time}, "
                        f"当前已完结: {end_time})"
                    )
                else:
                    logger.info(f"需要获取数据: {last_time} ~ {end_time}")

                    # 步骤1: 获取新K线
                    new_klines = fetch_new_klines(
                        exchange, last_time, end_time
                    )

                    if new_klines:
                        # 步骤2: 保存到 klines_1m 表（原始数据）
                        logger.info("")
                        logger.info("步骤 1/2: 保存原始K线数据到 klines_1m 表")
                        saved_count = save_to_klines_1m(new_klines)

                        if saved_count > 0:
                            total_fetched += saved_count

                            # 步骤3: 计算指标并保存到 klines_1m_macd_smooth_ma 表
                            logger.info("")
                            logger.info("步骤 2/2: 计算指标并保存到 klines_1m_macd_smooth_ma 表")

                            # 计算本次新增数据的指标
                            calculated_count = calculate_and_save_indicators(
                                start_time=new_klines[0].open_time,
                                end_time=new_klines[-1].close_time
                            )

                            if calculated_count > 0:
                                total_calculated += calculated_count
                                logger.info(
                                    f"✓ 本批处理完成，"
                                    f"获取 {saved_count} 条，"
                                    f"计算 {calculated_count} 条"
                                )
                            else:
                                logger.warning("指标计算失败")

                            # 更新最后时间
                            last_time = new_klines[-1].close_time
                        else:
                            logger.warning("没有保存新的K线数据")
                    else:
                        logger.info("未获取到新K线")

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
        logger.info(f"总计算指标: {total_calculated} 条")
        logger.info("=" * 80)


if __name__ == '__main__':
    main()
