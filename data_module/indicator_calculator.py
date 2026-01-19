#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技术指标计算器 - 支持回测预热和增量更新
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

from core.logger import get_logger
from core.config import config


class IndicatorCalculator:
    """技术指标计算器"""

    def __init__(self):
        self.logger = get_logger('data_module.indicator')
        self.history_df: Optional[pd.DataFrame] = None
        self.max_history = 1000  # 保留最近1000条数据

    def seed_warm_data(self, warm_df: pd.DataFrame):
        """
        使用预热数据初始化指标计算器

        Args:
            warm_df: 预热数据DataFrame (必须包含: open_time, open, high, low, close, volume)
        """
        self.logger.info(f"初始化指标引擎,预热数据量: {len(warm_df)}")

        # 确保数据按时间排序
        warm_df = warm_df.sort_values('open_time').reset_index(drop=True)

        # 保留最近的历史数据
        self.history_df = warm_df.tail(self.max_history).copy()

        self.logger.info(f"指标引擎初始化完成,保留历史数据: {len(self.history_df)}条")

    def update(self, bar: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用新的K线数据更新指标

        Args:
            bar: K线数据字典

        Returns:
            指标字典
        """
        # 优化：使用字典列表而非DataFrame concat
        new_row = {
            'open_time': bar.get('open_time'),
            'open': bar.get('open'),
            'high': bar.get('high'),
            'low': bar.get('low'),
            'close': bar.get('close'),
            'volume': bar.get('volume', 0)
        }

        if self.history_df is None:
            # 第一次：初始化为DataFrame
            self.history_df = pd.DataFrame([new_row])
        else:
            # 优化：使用append并定期重建，避免频繁concat
            # 当数据量达到2倍max_history时，重建DataFrame
            if len(self.history_df) >= self.max_history * 2:
                self.history_df = self.history_df.tail(self.max_history).reset_index(drop=True)

            # 使用loc追加（比concat快）
            self.history_df.loc[len(self.history_df)] = new_row

        # 计算所有指标
        return self._calculate_all_indicators()

    def calculate_all(self, klines: list) -> Dict[str, Any]:
        """
        计算所有指标 (批量计算)

        Args:
            klines: K线数据列表

        Returns:
            最新指标的字典
        """
        if not klines:
            return {}

        df = pd.DataFrame(klines)

        # MACD
        macd = self._calculate_macd(df['close'])

        # KDJ
        kdj = self._calculate_kdj(df)

        result = {
            'open_time': df['open_time'].iloc[-1],
            'close': df['close'].iloc[-1],
            **macd,
            **kdj
        }

        return result

    def _calculate_all_indicators(self) -> Dict[str, Any]:
        """基于当前历史数据计算所有指标"""
        if self.history_df is None or len(self.history_df) < 30:
            return {}

        df = self.history_df

        # 计算各类指标
        indicators = {}

        # 1分钟MACD
        macd_1m = self._calculate_macd(df['close'])
        indicators.update({
            'macd15m': macd_1m['macd15m'],
            'dif15m': macd_1m['dif15m'],
            'dea15m': macd_1m['dea15m']
        })

        # 1分钟KDJ
        kdj_1m = self._calculate_kdj(df)
        indicators.update({
            'j_15': kdj_1m['j_15'],
            'k_15': kdj_1m['k_15'],
            'd_15': kdj_1m['d_15']
        })

        # 1小时MACD (使用15分钟数据抽取)
        if len(df) >= 60:
            macd_1h = self._calculate_strided_macd(df, interval=15)
            indicators.update({
                'macd1h': macd_1h['macd'],
                'dif1h': macd_1h['dif'],
                'dea1h': macd_1h['dea']
            })

        # 4小时MACD
        if len(df) >= 240:
            macd_4h = self._calculate_strided_macd(df, interval=60)
            indicators.update({
                'macd4h': macd_4h['macd'],
                'dif4h': macd_4h['dif'],
                'dea4h': macd_4h['dea']
            })

        return indicators

    def _calculate_macd(self, close: pd.Series) -> Dict[str, float]:
        """
        计算MACD指标

        Args:
            close: 收盘价序列

        Returns:
            MACD指标字典
        """
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        macd = dif - dea

        return {
            'macd15m': macd.iloc[-1],
            'dif15m': dif.iloc[-1],
            'dea15m': dea.iloc[-1]
        }

    def _calculate_strided_macd(self, df: pd.DataFrame, interval: int) -> Dict[str, float]:
        """
        计算跨周期的MACD (例如从1分钟数据计算1小时MACD)

        Args:
            df: K线数据
            interval: 采样间隔 (1分钟K线数量)

        Returns:
            MACD指标字典
        """
        n = len(df)

        # 从末尾向前每隔interval取一个数据点
        indices = sorted(range(n - 1, -1, -interval))

        if len(indices) < 30:
            # 数据不足,返回NaN
            return {'macd': np.nan, 'dif': np.nan, 'dea': np.nan}

        # 提取收盘价子序列
        close_sub = df['close'].iloc[indices]

        # 计算MACD
        ema12 = close_sub.ewm(span=12, adjust=False).mean()
        ema26 = close_sub.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        macd = dif - dea

        return {
            'macd': macd.iloc[-1],
            'dif': dif.iloc[-1],
            'dea': dea.iloc[-1]
        }

    def _calculate_kdj(self, df: pd.DataFrame) -> Dict[str, float]:
        """
        计算KDJ指标

        Args:
            df: K线数据

        Returns:
            KDJ指标字典
        """
        low = df['low']
        high = df['high']
        close = df['close']

        period = 9
        k_period = 3
        d_period = 3

        low_min = low.rolling(window=period).min()
        high_max = high.rolling(window=period).max()

        rsv = (close - low_min) / (high_max - low_min) * 100

        k = rsv.ewm(com=k_period-1, adjust=False).mean()
        d = k.ewm(com=d_period-1, adjust=False).mean()
        j = 3 * k - 2 * d

        return {
            'k_15': k.iloc[-1],
            'd_15': d.iloc[-1],
            'j_15': j.iloc[-1]
        }
