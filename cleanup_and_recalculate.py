#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理并重新计算指标数据
- 删除2024-12-20之后的数据
- 从数据库获取历史数据
- 重新计算并保存指标
"""

import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 必须在导入其他模块之前加载环境变量
load_dotenv()

from core.config import config
from core.logger import get_logger
from data_module.db_kline_reader import DbKlineReader
from data_module.indicator_calculator import IndicatorCalculator
import sqlite3

logger = get_logger('cleanup_recalculate')


def cleanup_old_data(cutoff_date='2024-12-20'):
    """
    清理指定日期之后的数据

    Args:
        cutoff_date: 截止日期，格式：YYYY-MM-DD
    """
    try:
        conn = sqlite3.connect(
            config.DB_PATH,
            timeout=30.0,
            isolation_level=None
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        cursor = conn.cursor()

        # 检查要删除的数据量
        check_sql = """
            SELECT COUNT(*)
            FROM klines_1m_macd_smooth_ma
            WHERE date(open_time) > ?
        """
        cursor.execute(check_sql, (cutoff_date,))
        count = cursor.fetchone()[0]

        if count > 0:
            logger.warning(f"即将删除 {count} 条数据（{cutoff_date}之后）")

            # 执行删除
            delete_sql = """
                DELETE FROM klines_1m_macd_smooth_ma
                WHERE date(open_time) > ?
            """
            cursor.execute(delete_sql, (cutoff_date,))
            deleted = cursor.rowcount

            logger.info(f"✓ 已删除 {deleted} 条数据")
        else:
            logger.info(f"没有需要删除的数据（{cutoff_date}之后）")

        conn.close()
        return count

    except Exception as e:
        logger.error(f"清理数据失败: {e}")
        import traceback
        traceback.print_exc()
        return 0


def get_klines_from_db(start_time, end_time):
    """
    从数据库获取K线数据

    Args:
        start_time: 开始时间
        end_time: 结束时间

    Returns:
        list: K线数据列表
    """
    try:
        reader = DbKlineReader(
            db_path=config.DB_PATH,
            table_name='klines_1m'
        )

        klines = reader.get_klines_by_time_range(
            start_time=start_time.strftime('%Y-%m-%d %H:%M:%S'),
            end_time=end_time.strftime('%Y-%m-%d %H:%M:%S')
        )

        logger.info(f"从数据库获取到 {len(klines)} 条K线")
        return klines

    except Exception as e:
        logger.error(f"获取K线失败: {e}")
        return []


def recalculate_indicators(start_date, end_date, warmup_days=200):
    """
    重新计算指定时间范围的指标

    Args:
        start_date: 开始日期
        end_date: 结束日期
        warmup_days: 预热天数
    """
    try:
        import pandas as pd

        logger.info(f"重新计算指标: {start_date} ~ {end_date}")

        # 转换为datetime
        start_datetime = datetime.fromisoformat(start_date)
        end_datetime = datetime.fromisoformat(end_date)

        # 1. 获取预热数据（用于初始化指标计算器）
        warmup_end = start_datetime
        warmup_start = warmup_end - timedelta(days=warmup_days)

        logger.info("")
        logger.info("=" * 80)
        logger.info("步骤 1/3: 获取预热数据")
        logger.info("=" * 80)

        historical_klines = get_klines_from_db(warmup_start, warmup_end)

        if not historical_klines:
            logger.error("未能获取到足够的预热数据！")
            return

        # 转换为字典格式
        warmup_data = []
        for kline in historical_klines:
            warmup_data.append({
                'open_time': kline.get('open_time') or kline.get('close_time'),
                'open': float(kline.get('open', 0)),
                'high': float(kline.get('high', 0)),
                'low': float(kline.get('low', 0)),
                'close': float(kline.get('close', 0)),
                'volume': float(kline.get('volume', 0))
            })

        logger.info(f"获取到 {len(warmup_data)} 条预热数据")

        # 2. 初始化指标计算器
        logger.info("")
        logger.info("=" * 80)
        logger.info("步骤 2/3: 初始化指标计算器")
        logger.info("=" * 80)

        calculator = IndicatorCalculator()
        warm_df = pd.DataFrame(warmup_data)
        calculator.seed_warm_data(warm_df)
        logger.info("✓ 指标计算器初始化完成")

        # 3. 获取需要重新计算的K线数据
        logger.info("")
        logger.info("=" * 80)
        logger.info("步骤 3/3: 重新计算指标")
        logger.info("=" * 80)

        target_klines = get_klines_from_db(start_datetime, end_datetime)

        if not target_klines:
            logger.info("没有需要重新计算的数据")
            return

        logger.info(f"开始处理 {len(target_klines)} 条K线...")

        # 转换为字典格式并排序
        target_data = []
        for kline in target_klines:
            target_data.append({
                'open_time': kline.get('open_time') or kline.get('close_time'),
                'open': float(kline.get('open', 0)),
                'high': float(kline.get('high', 0)),
                'low': float(kline.get('low', 0)),
                'close': float(kline.get('close', 0)),
                'volume': float(kline.get('volume', 0)),
                'close_time': kline.get('close_time'),
            })

        # 排序
        df = pd.DataFrame(target_data)
        df = df.sort_values('open_time').reset_index(drop=True)
        sorted_klines = df.to_dict('records')

        # 逐条计算指标并保存
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
                # 计算指标
                indicators = calculator.update(kline)

                # 合并数据
                result = {**kline, **indicators}

                # 保存到数据库
                columns = []
                placeholders = []
                values = []

                base_columns = [
                    'open_time', 'open', 'high', 'low', 'close', 'volume',
                    'close_time'
                ]

                for col in base_columns:
                    if col in result and col in existing_columns:
                        columns.append(col)
                        placeholders.append('?')
                        value = result[col]
                        if isinstance(value, datetime):
                            value = value.strftime('%Y-%m-%d %H:%M:%S')
                        values.append(value)

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
                    logger.info(f"已处理 {i + 1}/{len(sorted_klines)} 条")

            except Exception as e:
                logger.warning(f"处理第 {i+1} 条K线失败: {e}")
                continue

        conn.commit()
        conn.close()

        logger.info(f"✓ 重新计算完成，共处理 {calculated_count} 条K线")

    except Exception as e:
        logger.error(f"重新计算失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("清理并重新计算指标数据")
    logger.info("=" * 80)
    logger.info("")

    # 1. 清理旧数据
    logger.info("步骤 1/2: 清理旧数据")
    logger.info("=" * 80)
    cleanup_count = cleanup_old_data('2024-12-20')
    logger.info("")

    # 2. 重新计算指标
    logger.info("步骤 2/2: 重新计算指标")
    logger.info("=" * 80)

    # 从2024-12-21重新计算到现在
    start_date = '2024-12-21 00:00:00'
    end_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    recalculate_indicators(start_date, end_date, warmup_days=200)

    logger.info("")
    logger.info("=" * 80)
    logger.info("全部完成")
    logger.info("=" * 80)


if __name__ == '__main__':
    main()
