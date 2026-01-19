#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于时间窗口的滚动平均值计算器
使用 pandas rolling 实现与 macd_refactor.py 一致的均值计算
"""

from collections import deque
from typing import Dict, Optional

import numpy as np
import pandas as pd

from core.logger import get_logger

logger = get_logger('signal_module.time_rolling_mean')


class TimeRollingMean:
    """
    基于时间窗口的滚动平均值计算器

    维护历史数据，使用 pandas rolling 计算时间窗口内的均值
    """

    def __init__(self):
        # 存储各指标的历史数据
        # 格式: {field_name: {'times': deque, 'values': deque, 'window_minutes': int}}
        self.data: Dict[str, Dict] = {}

        logger.info("时间窗口滚动平均值计算器初始化完成")

    def init_field(self, field_name: str, window_minutes: int):
        """
        初始化一个指标的时间窗口

        Args:
            field_name: 指标名称,如 'macd15m', 'macd1h' 等
            window_minutes: 时间窗口大小(分钟),如 60, 300, 1440 等
        """
        if field_name not in self.data:
            self.data[field_name] = {
                'times': deque(maxlen=10000),  # 时间戳
                'values': deque(maxlen=10000),  # 指标值
                'window_minutes': window_minutes  # 时间窗口(分钟)
            }
            logger.debug(f"初始化指标 {field_name} 的时间窗口, 大小={window_minutes}分钟")

    def update(self, field_name: str, timestamp: pd.Timestamp, value: float) -> Optional[float]:
        """
        更新指标值并返回当前窗口的均值。

        逻辑对齐 macd_refactor.py 中的 precompute_sampled_means:
        - 窗口使用整数大小(分钟数)而非时间偏移字符串
        - 数值强制转为 float/数值型
        - 最少 1 个样本即可返回均值
        """
        if field_name not in self.data:
            self.init_field(field_name, 60)

        data_dict = self.data[field_name]
        data_dict['times'].append(timestamp)
        data_dict['values'].append(value)

        times_list = list(data_dict['times'])
        values_list = list(data_dict['values'])

        if len(times_list) == 0:
            return None

        window_minutes = data_dict['window_minutes']
        if window_minutes is None or window_minutes <= 0:
            return 0.0

        # 构造与 precompute_sampled_means 一致的 DataFrame
        df = pd.DataFrame({
            'close_time': times_list,
            field_name: values_list,
        })

        # close_time 统一转换为 datetime, 与原逻辑一致
        close_time_series = df['close_time']
        if not pd.api.types.is_datetime64_any_dtype(close_time_series):
            df['close_time'] = pd.to_datetime(close_time_series, utc=True, errors='coerce')

        try:
            series = df[field_name].astype(float)
        except Exception:
            series = pd.to_numeric(df[field_name], errors='coerce').fillna(0.0)

        if len(series) == 0:
            return None

        try:
            rolled_count = series.rolling(window=int(window_minutes), min_periods=1).mean()
            return float(rolled_count.iloc[-1]) if len(rolled_count) > 0 else None
        except Exception as e:
            logger.error(f"计算 {field_name} 的滚动均值失败: {e}")
            return None

    def get_mean(self, field_name: str) -> Optional[float]:
        """
        获取指定指标当前的移动平均值（不更新数据）

        Args:
            field_name: 指标名称

        Returns:
            移动平均值,如果窗口为空返回None
        """
        if field_name not in self.data:
            return None

        data_dict = self.data[field_name]
        times_list = list(data_dict['times'])
        values_list = list(data_dict['values'])

        if len(times_list) == 0:
            return None

        # 创建 DataFrame
        df = pd.DataFrame({
            'close_time': times_list,
            'value': values_list
        })

        window_minutes = data_dict['window_minutes']

        try:
            # 使用 pandas rolling time window
            rolled_mean = df['value'].rolling(
                window=f'{window_minutes}min',
                min_periods=1
            ).mean()

            return float(rolled_mean.iloc[-1])

        except Exception as e:
            logger.error(f"获取 {field_name} 的滚动均值失败: {e}")
            return None

    def reset(self):
        """清空所有时间窗口"""
        self.data.clear()
        logger.info("已清空所有时间窗口")

    def get_window_status(self) -> Dict[str, int]:
        """
        获取各窗口的填充状态

        Returns:
            字典: {field_name: current_length}
        """
        return {
            name: len(data['times'])
            for name, data in self.data.items()
        }


# 全局单例
_tracker_instance = None


def get_time_rolling_mean_tracker() -> TimeRollingMean:
    """获取全局单例的时间窗口滚动平均值计算器"""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = TimeRollingMean()
    return _tracker_instance
