#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
指标计算程序 - 从 klines_1m 表读取数据，计算指标后保存到 klines_1m_macd_smooth_ma 表
- 检查 klines_1m 表是否有新数据
- 加载200天历史数据预热
- 计算技术指标
- 保存到 klines_1m_macd_smooth_ma 表
- 每10秒检查一次
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

logger = get_logger('calculate_indicators')


def get_last_calculated_time():
    """获取 klines_1m_macd_smooth_ma 表中最后一条K线的时间"""
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
            FROM klines_1m_macd_smooth_ma
            ORDER BY close_time DESC
            LIMIT 1
        """)

        row = cursor.fetchone()
        conn.close()

        if row:
            last_time_str = row['close_time']
            # 转换为datetime对象
            last_time = datetime.fromisoformat(last_time_str)
            logger.info(f"最后计算时间: {last_time}")
            return last_time
        else:
            logger.warning("klines_1m_macd_smooth_ma表为空")
            return None

    except Exception as e:
        logger.error(f"获取最后计算时间失败: {e}")
        return None


def get_last_kline_time_from_1m():
    """获取 klines_1m 表中最后一条K线的时间"""
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
            logger.info(f"klines_1m表最后时间: {last_time}")
            return last_time
        else:
            logger.warning("klines_1m表为空")
            return None

    except Exception as e:
        logger.error(f"获取klines_1m最后时间失败: {e}")
        return None


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


def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("启动指标计算程序")
    logger.info("数据源: klines_1m 表")
    logger.info("目标表: klines_1m_macd_smooth_ma 表")
    logger.info("预热周期: 200天历史数据")
    logger.info("=" * 80)

    # 主循环
    check_count = 0
    total_calculated = 0

    try:
        while True:
            try:
                check_count += 1
                logger.info("")
                logger.info("=" * 80)
                logger.info(f"第 {check_count} 次检查")
                logger.info("=" * 80)

                # 获取 klines_1m 表最后时间
                last_kline_1m_time = get_last_kline_time_from_1m()

                if not last_kline_1m_time:
                    logger.info("klines_1m 表为空，等待数据...")
                    time.sleep(10)
                    continue

                # 获取已计算的最后时间
                last_calculated_time = get_last_calculated_time()

                if not last_calculated_time:
                    # 首次运行，计算所有数据
                    logger.info("首次运行，将计算所有历史数据")
                    start_time = last_kline_1m_time - timedelta(days=1)  # 从1天前开始
                else:
                    # 检查是否有新数据
                    if last_calculated_time >= last_kline_1m_time:
                        logger.info(
                            f"没有新数据需要计算 "
                            f"(最后计算: {last_calculated_time}, "
                            f"klines_1m最后: {last_kline_1m_time})"
                        )
                        time.sleep(10)
                        continue
                    else:
                        # 从上次计算的下一条开始
                        start_time = last_calculated_time + timedelta(minutes=1)

                # 计算到最新的K线
                end_time = last_kline_1m_time

                logger.info(f"需要计算指标: {start_time} ~ {end_time}")

                # 计算指标
                calculated_count = calculate_and_save_indicators(
                    start_time=start_time,
                    end_time=end_time
                )

                if calculated_count > 0:
                    total_calculated += calculated_count
                    logger.info(
                        f"✓ 本批计算完成，累计计算 {total_calculated} 条K线"
                    )
                else:
                    logger.warning("指标计算失败")

                # 等待10秒后再次检查
                logger.info("等待下次检查...")
                time.sleep(10)

            except KeyboardInterrupt:
                logger.info("\n收到退出信号")
                break
            except Exception as e:
                logger.error(f"检查过程出错: {e}")
                import traceback
                traceback.print_exc()
                # 等待一段时间后继续
                time.sleep(10)

    finally:
        logger.info("=" * 80)
        logger.info(f"程序结束")
        logger.info(f"总检查次数: {check_count}")
        logger.info(f"总计算指标: {total_calculated} 条")
        logger.info("=" * 80)


if __name__ == '__main__':
    main()
