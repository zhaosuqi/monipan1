#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据模块 - K线数据获取、指标计算、数据入库、通知、回测引擎
"""

# 捕获导入错误,允许在缺少某些依赖时运行
try:
    from .kline_fetcher import KlineFetcher
    _has_binance = True
except ImportError:
    _has_binance = False
    KlineFetcher = None

from .indicator_calculator import IndicatorCalculator
from .data_writer import DataWriter
from .data_notifier import DataNotifier
from .replay_engine import ReplayEngine

__all__ = [
    'KlineFetcher',
    'IndicatorCalculator',
    'DataWriter',
    'DataNotifier',
    'ReplayEngine'
]
