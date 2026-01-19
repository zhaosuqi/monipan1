#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
移动平均值追踪器
用于实时计算和维护各时间周期指标的移动平均值
"""

import pandas as pd
from typing import Dict, List, Optional
from collections import deque
from core.logger import get_logger

logger = get_logger('signal_module.rolling_mean')


class RollingMeanTracker:
    """
    移动平均值追踪器

    维护各指标的滑动窗口,实时计算移动平均值
    """

    def __init__(self):
        # 存储各指标的滑动窗口
        # 格式: {field_name: deque(maxlen=window_size)}
        self.windows: Dict[str, deque] = {}

        # 存储各指标的窗口大小配置
        # 格式: {field_name: window_size}
        self.window_sizes: Dict[str, int] = {}

        logger.info("移动平均值追踪器初始化完成")

    def init_field(self, field_name: str, window_size: int):
        """
        初始化一个指标的滑动窗口

        Args:
            field_name: 指标名称,如 'macd15m', 'dif15m' 等
            window_size: 窗口大小,如 60, 120 等
        """
        if field_name not in self.windows:
            self.windows[field_name] = deque(maxlen=window_size)
            self.window_sizes[field_name] = window_size
            logger.debug(f"初始化指标 {field_name} 的滑动窗口, 大小={window_size}")

    def update(self, field_name: str, value: float) -> Optional[float]:
        """
        更新指标值并返回当前的移动平均值

        Args:
            field_name: 指标名称
            value: 新的指标值

        Returns:
            当前的移动平均值,如果数据不足返回None
        """
        # 如果窗口未初始化,自动初始化(默认大小60)
        if field_name not in self.windows:
            self.init_field(field_name, 60)

        # 添加新值
        self.windows[field_name].append(value)

        # 计算移动平均值
        window = self.windows[field_name]
        if len(window) > 0:
            mean = sum(window) / len(window)
            return mean

        return None

    def get_mean(self, field_name: str) -> Optional[float]:
        """
        获取指定指标当前的移动平均值

        Args:
            field_name: 指标名称

        Returns:
            移动平均值,如果窗口为空返回None
        """
        if field_name not in self.windows:
            return None

        window = self.windows[field_name]
        if len(window) == 0:
            return None

        return sum(window) / len(window)

    def update_from_row(self, row: Dict[str, float], field_mappings: Dict[str, str]):
        """
        从一行K线数据批量更新多个指标

        Args:
            row: K线数据字典
            field_mappings: 字段映射,格式:
                {
                    'macd15m': 'macd15m_mean',  # 源字段 -> 目标平均值字段
                    'dif15m': 'dif15m_mean',
                    ...
                }
        """
        results = {}

        for source_field, mean_field in field_mappings.items():
            value = row.get(source_field)
            if value is not None:
                mean_value = self.update(source_field, float(value))
                if mean_value is not None:
                    results[mean_field] = mean_value

        return results

    def get_all_means(self) -> Dict[str, float]:
        """
        获取所有指标当前的移动平均值

        Returns:
            字典: {field_name: mean_value}
        """
        results = {}
        for field_name, window in self.windows.items():
            if len(window) > 0:
                mean = sum(window) / len(window)
                results[field_name] = mean
        return results

    def reset(self):
        """清空所有滑动窗口"""
        self.windows.clear()
        self.window_sizes.clear()
        logger.info("已清空所有移动平均值窗口")

    def get_window_status(self) -> Dict[str, int]:
        """
        获取各窗口的填充状态

        Returns:
            字典: {field_name: current_length}
        """
        return {name: len(window) for name, window in self.windows.items()}


# 全局单例
_tracker_instance = None

def get_rolling_mean_tracker() -> RollingMeanTracker:
    """获取全局单例的移动平均值追踪器"""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = RollingMeanTracker()
    return _tracker_instance
