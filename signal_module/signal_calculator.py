#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
信号计算器 - 基于MACD V5.0算法

参考: archive_old/macd_refactor.py 中的 macd_v5_0_signal 函数
集成移动平均值实时计算功能
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from core.config import config
from core.logger import get_logger
from signal_module.rolling_mean_tracker import get_rolling_mean_tracker
from signal_module.time_rolling_mean import get_time_rolling_mean_tracker

logger = get_logger('signal_module.calculator')


@dataclass
class Signal:
    """交易信号"""
    action: str  # 'open' or 'close'
    side: str    # 'long' or 'short'
    reason: str
    confidence: float = 1.0
    details: Optional[Dict[str, Any]] = None


class SignalCalculator:
    """信号计算器 - 实现MACD V5.0策略"""


    def __init__(self):
        self.logger = logger
        self.debug_count = 0  # 调试计数器

        # 使用基于时间窗口的滚动平均值计算器
        self.time_rolling_tracker = get_time_rolling_mean_tracker()

        # 初始化各个指标的时间窗口
        # Config 参数本身就是分钟数，直接传递即可
        # 参考：cg.precompute_sampled_means(df15, 'dea1d', Config.MEANS_DEA1D_COUNT_2)

        # 15分钟指标窗口（参数就是分钟数）
        if config.MEANS_HIST15_COUNT > 0:
            self.time_rolling_tracker.init_field('macd15m', config.MEANS_HIST15_COUNT)
        if config.MEANS_DIF15_COUNT > 0:
            self.time_rolling_tracker.init_field('dif15m', config.MEANS_DIF15_COUNT)
        if config.MEANS_DEA15_COUNT > 0:
            self.time_rolling_tracker.init_field('dea15m', config.MEANS_DEA15_COUNT)

        # 15分钟指标第二组窗口
        if config.MEANS_HIST15_COUNT_2 > 0:
            self.time_rolling_tracker.init_field('macd15m_2', config.MEANS_HIST15_COUNT_2)
        if config.MEANS_DIF15_COUNT_2 > 0:
            self.time_rolling_tracker.init_field('dif15m_2', config.MEANS_DIF15_COUNT_2)
        if config.MEANS_DEA15_COUNT_2 > 0:
            self.time_rolling_tracker.init_field('dea15m_2', config.MEANS_DEA15_COUNT_2)

        # 1小时指标窗口（参数就是分钟数）
        if config.MEANS_HIST1H_COUNT > 0:
            self.time_rolling_tracker.init_field('macd1h', config.MEANS_HIST1H_COUNT)
        if config.MEANS_DIF1H_COUNT > 0:
            self.time_rolling_tracker.init_field('dif1h', config.MEANS_DIF1H_COUNT)
        if config.MEANS_DEA1H_COUNT > 0:
            self.time_rolling_tracker.init_field('dea1h', config.MEANS_DEA1H_COUNT)

        # 1小时指标第二组窗口
        if config.MEANS_HIST1H_COUNT_2 > 0:
            self.time_rolling_tracker.init_field('macd1h_2', config.MEANS_HIST1H_COUNT_2)
        if config.MEANS_DIF1H_COUNT_2 > 0:
            self.time_rolling_tracker.init_field('dif1h_2', config.MEANS_DIF1H_COUNT_2)
        if config.MEANS_DEA1H_COUNT_2 > 0:
            self.time_rolling_tracker.init_field('dea1h_2', config.MEANS_DEA1H_COUNT_2)

        # 4小时指标窗口（参数就是分钟数）
        if config.MEANS_HIST4_COUNT > 0:
            self.time_rolling_tracker.init_field('macd4h', config.MEANS_HIST4_COUNT)
        if config.MEANS_DIF4_COUNT > 0:
            self.time_rolling_tracker.init_field('dif4h', config.MEANS_DIF4_COUNT)
        if config.MEANS_DEA4_COUNT > 0:
            self.time_rolling_tracker.init_field('dea4h', config.MEANS_DEA4_COUNT)

        # 4小时指标第二组窗口
        if config.MEANS_HIST4_COUNT_2 > 0:
            self.time_rolling_tracker.init_field('macd4h_2', config.MEANS_HIST4_COUNT_2)
        if config.MEANS_DIF4_COUNT_2 > 0:
            self.time_rolling_tracker.init_field('dif4h_2', config.MEANS_DIF4_COUNT_2)
        if config.MEANS_DEA4_COUNT_2 > 0:
            self.time_rolling_tracker.init_field('dea4h_2', config.MEANS_DEA4_COUNT_2)

        # 1天指标窗口（参数就是分钟数）
        if config.MEANS_HIST1D_COUNT > 0:
            self.time_rolling_tracker.init_field('macd1d', config.MEANS_HIST1D_COUNT)
        if config.MEANS_DIF1D_COUNT > 0:
            self.time_rolling_tracker.init_field('dif1d', config.MEANS_DIF1D_COUNT)
        if config.MEANS_DEA1D_COUNT > 0:
            self.time_rolling_tracker.init_field('dea1d', config.MEANS_DEA1D_COUNT)

        # 1天指标第二组窗口
        if config.MEANS_HIST1D_COUNT_2 > 0:
            self.time_rolling_tracker.init_field('macd1d_2', config.MEANS_HIST1D_COUNT_2)
        if config.MEANS_DIF1D_COUNT_2 > 0:
            self.time_rolling_tracker.init_field('dif1d_2', config.MEANS_DIF1D_COUNT_2)
        if config.MEANS_DEA1D_COUNT_2 > 0:
            self.time_rolling_tracker.init_field('dea1d_2', config.MEANS_DEA1D_COUNT_2)

        self.logger.info("信号计算器初始化完成,已配置时间窗口移动平均值")

    def calculate_open_signal(self, indicators: Dict[str, Any], row_prev=None, row_list=None, state_prices=None) -> Optional[Signal]:
        """
        计算开仓信号 - 基于MACD V5.0算法

        Args:
            indicators: 包含所有技术指标的字典
            row_prev: 前一行数据（用于价格跳空检查）
            state_prices: 价格历史数据（用于价格变化限制检查）

        Returns:
            Signal or None
        """
        # 提取指标
        row = indicators
        # self.logger.info(f"计算开仓信号,指标数据: {row}")

        # 获取当前时间戳
        ts = pd.to_datetime(row.get('open_time'))

        # ========== 第一步: 更新移动平均值 ==========
        # 使用基于时间窗口的滚动平均，每次都更新
        # pandas rolling 会自动处理时间窗口内的数据

        # 15分钟指标
        hist15_mean = self.time_rolling_tracker.update('macd15m', ts, row.get('macd15m', 0))
        dif15_mean = self.time_rolling_tracker.update('dif15m', ts, row.get('dif15m', 0))
        dea15_mean = self.time_rolling_tracker.update('dea15m', ts, row.get('dea15m', 0))

        # 15分钟指标第二组
        hist15_mean_2 = self.time_rolling_tracker.update('macd15m_2', ts, row.get('macd15m', 0))
        dif15_mean_2 = self.time_rolling_tracker.update('dif15m_2', ts, row.get('dif15m', 0))
        dea15_mean_2 = self.time_rolling_tracker.update('dea15m_2', ts, row.get('dea15m', 0))

        # 1小时指标
        hist1h_mean = self.time_rolling_tracker.update('macd1h', ts, row.get('macd1h', 0))
        dif1h_mean = self.time_rolling_tracker.update('dif1h', ts, row.get('dif1h', 0))
        dea1h_mean = self.time_rolling_tracker.update('dea1h', ts, row.get('dea1h', 0))

        # 1小时指标第二组
        hist1h_mean_2 = self.time_rolling_tracker.update('macd1h_2', ts, row.get('macd1h', 0))
        dif1h_mean_2 = self.time_rolling_tracker.update('dif1h_2', ts, row.get('dif1h', 0))
        dea1h_mean_2 = self.time_rolling_tracker.update('dea1h_2', ts, row.get('dea1h', 0))

        # 4小时指标
        hist4_mean = self.time_rolling_tracker.update('macd4h', ts, row.get('macd4h', 0))
        dif4_mean = self.time_rolling_tracker.update('dif4h', ts, row.get('dif4h', 0))
        dea4_mean = self.time_rolling_tracker.update('dea4h', ts, row.get('dea4h', 0))

        # 4小时指标第二组
        hist4_mean_2 = self.time_rolling_tracker.update('macd4h_2', ts, row.get('macd4h', 0))
        dif4_mean_2 = self.time_rolling_tracker.update('dif4h_2', ts, row.get('dif4h', 0))
        dea4_mean_2 = self.time_rolling_tracker.update('dea4h_2', ts, row.get('dea4h', 0))

        # 1天指标（只在启用时计算）
        hist1d_mean = self.time_rolling_tracker.update('macd1d', ts, row.get('macd1d', 0))
        dif1d_mean = self.time_rolling_tracker.update('dif1d', ts, row.get('dif1d', 0)) 
        dea1d_mean = self.time_rolling_tracker.update('dea1d', ts, row.get('dea1d', 0)) 

        # 1天指标第二组（只在启用时计算）
        hist1d_mean_2 = self.time_rolling_tracker.update('macd1d_2', ts, row.get('macd1d', 0)) 
        dif1d_mean_2 = self.time_rolling_tracker.update('dif1d_2', ts, row.get('dif1d', 0)) 
        dea1d_mean_2 = self.time_rolling_tracker.update('dea1d_2', ts, row.get('dea1d', 0))


        # 将移动平均值添加到row中,供后续检查使用
        row['hist15_mean'] = hist15_mean
        row['dif15_mean'] = dif15_mean
        row['dea15_mean'] = dea15_mean
        row['hist15_mean_2'] = hist15_mean_2
        row['dif15_mean_2'] = dif15_mean_2
        row['dea15_mean_2'] = dea15_mean_2
        row['hist1h_mean'] = hist1h_mean
        row['dif1h_mean'] = dif1h_mean
        row['dea1h_mean'] = dea1h_mean
        row['hist1h_mean_2'] = hist1h_mean_2
        row['dif1h_mean_2'] = dif1h_mean_2
        row['dea1h_mean_2'] = dea1h_mean_2
        row['hist4_mean'] = hist4_mean
        row['dif4_mean'] = dif4_mean
        row['dea4_mean'] = dea4_mean
        row['hist4_mean_2'] = hist4_mean_2
        row['dif4_mean_2'] = dif4_mean_2
        row['dea4_mean_2'] = dea4_mean_2
        row['hist1d_mean'] = hist1d_mean
        row['dif1d_mean'] = dif1d_mean
        row['dea1d_mean'] = dea1d_mean
        row['hist1d_mean_2'] = hist1d_mean_2
        row['dif1d_mean_2'] = dif1d_mean_2
        row['dea1d_mean_2'] = dea1d_mean_2
        close_time = row.get('close_time', '')
        if '2024-01-02 20:01:59' in str(close_time):
            self.logger.info(row)
            self.logger.info("=" * 80)

        # ========== 第二步: 提取原始指标 ==========
        # 15分钟指标
        hist15 = row.get('macd15m', 0)
        dif15 = row.get('dif15m', 0)
        dea15 = row.get('dea15m', 0)
        j_15m = row.get('j_15', 0)

        # 1小时指标
        hist1h = row.get('macd1h', 0)
        dif1h = row.get('dif1h', 0)
        dea1h = row.get('dea1h', 0)
        j_1h = row.get('j_1h', 0)

        # 4小时指标
        hist4 = row.get('macd4h', 0)
        dif4 = row.get('dif4h', 0)
        dea4 = row.get('dea4h', 0)
        j_4h = row.get('j_4h', 0)

        # 1天指标
        hist1d = row.get('macd1d', 0)
        dif1d = row.get('dif1d', 0)
        dea1d = row.get('dea1d', 0)

        # 📊 调试：输出特定时刻的信号计算数据
        ts_str = str(row.get('close_time', ''))
        logger.info(
            f"🔍 [信号计算] {ts_str} | "
            f"H15={hist15:.2f} H1H={hist1h:.2f} H4={hist4:.2f} H1D={hist1d:.2f} | "
            f"J15={j_15m:.2f} J1H={j_1h:.2f} J4H={j_4h:.2f}"
        )

        # 检查做多信号
        long_signal, long_reason = self._check_long_signal(
            hist15, dif15, dea15, j_15m,
            hist1h, dif1h, dea1h, j_1h,
            hist4, dif4, dea4, j_4h,
            hist1d, dif1d, dea1d,
            row,
            row_prev,  # 传递前一行数据
            row_list,
            state_prices,  # 传递价格历史
            ts_str  # 传递时间戳用于日志
        )



        if long_signal:
            self.debug_count += 1
            # 🔍 调试：记录返回的 Signal 对象
            ts_str = str(row.get('open_time', ''))
            if '19:44' in ts_str or '19:39' in ts_str:
                self.logger.info(f"🔍 [signal_calculator] 返回多头 Signal 对象")
                self.logger.info(f"🔍 [signal_calculator] 时间={ts_str}")
                self.logger.info(f"🔍 [signal_calculator] action=open, side=long")
                self.logger.info(f"🔍 [signal_calculator] reason={long_reason}")

            return Signal(
                action='open',
                side='long',
                reason='V5多头信号',
                confidence=0.8,
                details={'reason_detail': long_reason}
            )

        # 检查做空信号
        short_signal, short_reason = self._check_short_signal(
            hist15, dif15, dea15, j_15m,
            hist1h, dif1h, dea1h, j_1h,
            hist4, dif4, dea4, j_4h,
            hist1d, dif1d, dea1d,
            row,
            row_prev,  # 传递前一行数据
            row_list,  # 传递历史K线
            state_prices  # 传递价格历史
        )

        # 📊 调试：输出特定时刻的空头信号检查结果
    
        if short_signal:
            self.debug_count += 1
            # 🔍 调试：记录返回的 Signal 对象
            ts_str = str(row.get('open_time', ''))
            if '19:44' in ts_str or '19:39' in ts_str:
                self.logger.info(f"🔍 [signal_calculator] 返回空头 Signal 对象")
                self.logger.info(f"🔍 [signal_calculator] 时间={ts_str}")
                self.logger.info(f"🔍 [signal_calculator] action=open, side=short")
                self.logger.info(f"🔍 [signal_calculator] reason={short_reason}")

            return Signal(
                action='open',
                side='short',
                reason='V5空头信号',
                confidence=0.8,
                details={'reason_detail': short_reason}
            )

        # 🔍 调试：记录没有信号的情况
        ts_str = str(row.get('open_time', ''))
        if '19:44' in ts_str or '19:39' in ts_str:
            self.logger.info(f"🔍 [signal_calculator] 返回 None - 无信号")
            self.logger.info(f"🔍 [signal_calculator] 时间={ts_str}")
            self.logger.info(f"🔍 [signal_calculator] long_signal={long_signal}, short_signal={short_signal}")

        return None

    def _check_long_signal(
        self,
        hist15, dif15, dea15, j_15m,
        hist1h, dif1h, dea1h, j_1h,
        hist4, dif4, dea4, j_4h,
        hist1d, dif1d, dea1d,
        row,
        row_prev=None,
        row_list=None,
        state_prices=None,
        ts_str=''
    ) -> tuple:
        """
        检查做多信号

        Returns:
            (is_signal: bool, reason: str)
        """
        is_long = True
        reasons = []
        history_rows = row_list or []

        # ========== 价格变化验证 (参考 macd_refactor.py) ==========
        # M_PRICE_CHANGE - 防止跳空开仓
        if config.M_PRICE_CHANGE != 0 and config.M_PRICE_CHANGE_MINUTES > 0 and len(history_rows) >= config.M_PRICE_CHANGE_MINUTES:
            r = history_rows[-1 * config.M_PRICE_CHANGE_MINUTES]
            price_change_limit = config.M_PRICE_CHANGE if config.M_PRICE_CHANGE > 1 else r['close'] * config.M_PRICE_CHANGE
            if abs(row['close'] - r['close']) > price_change_limit:
                is_long = False
                reasons.append(f"价格跳空: close={row['close']:.2f}, prev_close={r['close']:.2f}, diff={abs(row['close']-r['close']):.2f}")
                logger.debug(f"DEBUG: 跳过多头开仓 due to price jump at {row.get('close_time')}, close={row['close']}, prev_close={r['close']}, diff={abs(row['close']-r['close'])}")
        if is_long and config.M_PRICE_CHANGE_B != 0 and config.M_PRICE_CHANGE_MINUTES_B > 0 and len(history_rows) >= config.M_PRICE_CHANGE_MINUTES_B:
            r = history_rows[-1 * config.M_PRICE_CHANGE_MINUTES_B]
            price_change_limit = config.M_PRICE_CHANGE_B if config.M_PRICE_CHANGE_B > 1 else r['close'] * config.M_PRICE_CHANGE_B
            if abs(row['close'] - r['close']) > price_change_limit:
                is_long = False
                reasons.append(f"价格跳空: close={row['close']:.2f}, prev_close={r['close']:.2f}, diff={abs(row['close']-r['close']):.2f}")
                logger.debug(f"DEBUG: 跳过多头开仓 due to price jump at {row.get('close_time')}, close={row['close']}, prev_close={r['close']}, diff={abs(row['close']-r['close'])}")
        if is_long and config.M_PRICE_CHANGE_C != 0 and config.M_PRICE_CHANGE_MINUTES_C > 0 and len(history_rows) >= config.M_PRICE_CHANGE_MINUTES_C:
            r = history_rows[-1 * config.M_PRICE_CHANGE_MINUTES_C]
            price_change_limit = config.M_PRICE_CHANGE_C if config.M_PRICE_CHANGE_C > 1 else r['close'] * config.M_PRICE_CHANGE_C
            if abs(row['close'] - r['close']) > price_change_limit:
                is_long = False
                reasons.append(f"价格跳空: close={row['close']:.2f}, prev_close={r['close']:.2f}, diff={abs(row['close']-r['close']):.2f}")
                logger.debug(f"DEBUG: 跳过多头开仓 due to price jump at {row.get('close_time')}, close={row['close']}, prev_close={r['close']}, diff={abs(row['close']-r['close'])}")
        # if row_prev is not None and config.M_PRICE_CHANGE != 0:
        #     price_change_limit = config.M_PRICE_CHANGE if config.M_PRICE_CHANGE > 1 else row_prev['close'] * config.M_PRICE_CHANGE
        #     if abs(row['close'] - row_prev['close']) > price_change_limit:
        #         is_long = False
        #         reasons.append(f"价格跳空: close={row['close']:.2f}, prev_close={row_prev['close']:.2f}, diff={abs(row['close']-row_prev['close']):.2f}")
        #         logger.debug(f"DEBUG: 跳过多头开仓 due to price jump at {row.get('close_time')}, close={row['close']}, prev_close={row_prev['close']}, diff={abs(row['close']-row_prev['close'])}")

        # PRICE_CHANGE_COUNT
        if state_prices is not None and config.PRICE_CHANGE_COUNT > 0:
            max_price = state_prices.iloc[-1*config.PRICE_CHANGE_COUNT:].max()
            min_price = state_prices.iloc[-1*config.PRICE_CHANGE_COUNT:].min()
            if max_price > row['close'] + row['close'] * config.PRICE_CHANGE_LIMIT and min_price < row['close'] - row['close'] * config.PRICE_CHANGE_LIMIT:
                is_long = False
                reasons.append(f"价格变化限制_COUNT: min={min_price:.2f}, max={max_price:.2f}")
                logger.debug(f"DEBUG: 跳过多头开仓 due to price change limit at {row.get('close_time')}, min_price={min_price}, max_price={max_price}, close={row['close']}, limit={config.PRICE_CHANGE_LIMIT}")

        # PRICE_CHANGE_COUNT_B
        if state_prices is not None and config.PRICE_CHANGE_COUNT_B > 0:
            max_price_b = state_prices.iloc[-1*config.PRICE_CHANGE_COUNT_B:].max()
            min_price_b = state_prices.iloc[-1*config.PRICE_CHANGE_COUNT_B:].min()
            if max_price_b > row['close'] + row['close'] * config.PRICE_CHANGE_LIMIT_B and min_price_b < row['close'] - row['close'] * config.PRICE_CHANGE_LIMIT_B:
                is_long = False
                reasons.append(f"价格变化限制_COUNT_B: min={min_price_b:.2f}, max={max_price_b:.2f}")
                logger.debug(f"DEBUG: 跳过多头开仓 due to price change limit at {row.get('close_time')}, min_price_b={min_price_b}, max_price_b={max_price_b}, close={row['close']}, limit={config.PRICE_CHANGE_LIMIT_B}")

        # PRICE_CHANGE_COUNT_C
        if state_prices is not None and config.PRICE_CHANGE_COUNT_C > 0:
            max_price_c = state_prices.iloc[-1*config.PRICE_CHANGE_COUNT_C:].max()
            min_price_c = state_prices.iloc[-1*config.PRICE_CHANGE_COUNT_C:].min()
            if max_price_c > row['close'] + row['close'] * config.PRICE_CHANGE_LIMIT_C and min_price_c < row['close'] - row['close'] * config.PRICE_CHANGE_LIMIT_C:
                is_long = False
                reasons.append(f"价格变化限制_COUNT_C: min={min_price_c:.2f}, max={max_price_c:.2f}")
                logger.debug(f"DEBUG: 跳过多头开仓 due to price change limit at {row.get('close_time')}, min_price_c={min_price_c}, max_price_c={max_price_c}, close={row['close']}, limit={config.PRICE_CHANGE_LIMIT_C}")

        # ENABLE_MA5_MA10 - 成交量检查 (多头要求 vol_ma5 > vol_ma10)
        if config.ENABLE_MA5_MA10 and row.get('vol_ma5') is not None and row.get('vol_ma10') is not None:
            if row.get('vol_ma5') < row.get('vol_ma10'):
                is_long = False
                reasons.append(f"成交量MA: vol_ma5={row.get('vol_ma5'):.2f} < vol_ma10={row.get('vol_ma10'):.2f}")
                logger.debug(f"DEBUG: 跳过多头开仓 due to vol_ma5 < vol_ma10 at {row.get('close_time')}, vol_ma5={row.get('vol_ma5')}, vol_ma10={row.get('vol_ma10')}")

        # 如果价格验证失败，直接返回
        if not is_long:
            return False, "; ".join(reasons)

        # 📊 调试：记录特定时刻的检查开始
        debug_mode = True

        # ========== 15分钟指标检查 ==========
        # HIST15限制
        if hist15 > config.T0_HIST15_LIMIT or hist15 < config.T0_HIST15_LIMIT_MIN:
            is_long = False
            reasons.append(f"HIST15: {hist15:.2f} config.T0_HIST15_LIMIT:{config.T0_HIST15_LIMIT} config.T0_HIST15_LIMIT_MIN:{config.T0_HIST15_LIMIT_MIN}")
            if debug_mode:
                logger.warning(f"❌ [{ts_str}] HIST15限制: {hist15:.2f} 超出范围 [{config.T0_HIST15_LIMIT_MIN}, {config.T0_HIST15_LIMIT}]")
        elif debug_mode:
            logger.info(f"✅ [{ts_str}] HIST15限制: {hist15:.2f} 在范围内")

        # DIF15限制
        if is_long and (dif15 > config.T0_DIF15_LIMIT or dif15 < config.T0_DIF15_LIMIT_MIN):
            is_long = False
            reasons.append(f"DIF15: {dif15:.2f} config.T0_DIF15_LIMIT:{config.T0_DIF15_LIMIT} config.T0_DIF15_LIMIT_MIN:{config.T0_DIF15_LIMIT_MIN}")
            if debug_mode:
                logger.warning(f"❌ [{ts_str}] DIF15限制: {dif15:.2f} 超出范围 [{config.T0_DIF15_LIMIT_MIN}, {config.T0_DIF15_LIMIT}]")
        # HIST15均值检查 (第一组)
        if is_long and config.MEANS_HIST15_COUNT != 0:
            hist15_mean = row.get('hist15_mean', 0)
            if hist15 - config.HIST15_MEANS_LIMIT < hist15_mean:
                is_long = False
                reasons.append(f"HIST15均值1: {hist15:.2f} - {config.HIST15_MEANS_LIMIT:.2f} < {hist15_mean:.2f}")

        # HIST15均值检查 (第二组)
        if is_long and config.MEANS_HIST15_COUNT_2 != 0:
            hist15_mean_2 = row.get('hist15_mean_2', 0)
            if hist15 - config.HIST15_MEANS_LIMIT_2 < hist15_mean_2:
                is_long = False
                reasons.append(f"HIST15均值2: {hist15:.2f} - {config.HIST15_MEANS_LIMIT_2:.2f} < {hist15_mean_2:.2f}")

        # DIF15均值检查 (第一组)
        if is_long and config.MEANS_DIF15_COUNT != 0:
            dif15_mean = row.get('dif15_mean', 0)
            if dif15 - config.DIF15_MEANS_LIMIT < dif15_mean:
                is_long = False
                reasons.append(f"DIF15均值1: {dif15:.2f} - {config.DIF15_MEANS_LIMIT:.2f} < {dif15_mean:.2f}")

        # DIF15均值检查 (第二组)
        if is_long and config.MEANS_DIF15_COUNT_2 != 0:
            dif15_mean_2 = row.get('dif15_mean_2', 0)
            if dif15 - config.DIF15_MEANS_LIMIT_2 < dif15_mean_2:
                is_long = False
                reasons.append(f"DIF15均值2: {dif15:.2f} - {config.DIF15_MEANS_LIMIT_2:.2f} < {dif15_mean_2:.2f}")

        # DEA15均值检查 (第一组)
        if is_long and config.MEANS_DEA15_COUNT != 0:
            dea15_mean = row.get('dea15_mean', 0)
            if dea15 - config.DEA15_MEANS_LIMIT < dea15_mean:
                is_long = False
                reasons.append(f"DEA15均值1: {dea15:.2f} - {config.DEA15_MEANS_LIMIT:.2f} < {dea15_mean:.2f}")

        # DEA15均值检查 (第二组)
        if is_long and config.MEANS_DEA15_COUNT_2 != 0:
            dea15_mean_2 = row.get('dea15_mean_2', 0)
            if dea15 - config.DEA15_MEANS_LIMIT_2 < dea15_mean_2:
                is_long = False
                reasons.append(f"DEA15均值2: {dea15:.2f} < {dea15_mean_2:.2f}")

        # ========== 1小时指标检查 ==========
        # HIST1H限制
        if is_long and (hist1h > config.T0_HIST1H_LIMIT or hist1h < config.T0_HIST1H_LIMIT_MIN):
            is_long = False
            reasons.append(f"HIST1H: {hist1h:.2f} config.T0_HIST1H_LIMIT:{config.T0_HIST1H_LIMIT} config.T0_HIST1H_LIMIT_MIN:{config.T0_HIST1H_LIMIT_MIN}")

        # DIF1H限制
        if is_long and (dif1h > config.T0_DIF1H_LIMIT or dif1h < config.T0_DIF1H_LIMIT_MIN):
            is_long = False
            reasons.append(f"DIF1H: {dif1h:.2f} config.T0_DIF1H_LIMIT:{config.T0_DIF1H_LIMIT} config.T0_DIF1H_LIMIT_MIN:{config.T0_DIF1H_LIMIT_MIN}")

        # HIST1H均值检查 (第一组)
        if is_long and config.MEANS_HIST1H_COUNT != 0:
            hist1h_mean = row.get('hist1h_mean', 0)
            if hist1h - config.HIST1H_MEANS_LIMIT < hist1h_mean:
                is_long = False
                reasons.append(f"HIST1H均值1: {hist1h:.2f} - {config.HIST1H_MEANS_LIMIT:.2f} < {hist1h_mean:.2f}")

        # HIST1H均值检查 (第二组)
        if is_long and config.MEANS_HIST1H_COUNT_2 != 0:
            hist1h_mean_2 = row.get('hist1h_mean_2', 0)
            if hist1h - config.HIST1H_MEANS_LIMIT_2 < hist1h_mean_2:
                is_long = False
                reasons.append(f"HIST1H均值2: {hist1h:.2f} - {config.HIST1H_MEANS_LIMIT_2:.2f} < {hist1h_mean_2:.2f}")

        # DIF1H均值检查 (第一组)
        if is_long and config.MEANS_DIF1H_COUNT != 0:
            dif1h_mean = row.get('dif1h_mean', 0)
            if dif1h - config.DIF1H_MEANS_LIMIT < dif1h_mean:
                is_long = False
                reasons.append(f"DIF1H均值1: {dif1h:.2f} - {config.DIF1H_MEANS_LIMIT:.2f} < {dif1h_mean:.2f}")

        # DIF1H均值检查 (第二组)
        if is_long and config.MEANS_DIF1H_COUNT_2 != 0:
            dif1h_mean_2 = row.get('dif1h_mean_2', 0)
            if dif1h - config.DIF1H_MEANS_LIMIT_2 < dif1h_mean_2:
                is_long = False
                reasons.append(f"DIF1H均值2: {dif1h:.2f} - {config.DIF1H_MEANS_LIMIT_2:.2f} < {dif1h_mean_2:.2f}")

        # DEA1H均值检查 (第一组)
        if is_long and config.MEANS_DEA1H_COUNT != 0:
            dea1h_mean = row.get('dea1h_mean', 0)
            if dea1h - config.DEA1H_MEANS_LIMIT < dea1h_mean:
                is_long = False
                reasons.append(f"DEA1H均值1: {dea1h:.2f} - {config.DEA1H_MEANS_LIMIT:.2f} < {dea1h_mean:.2f}")

        # DEA1H均值检查 (第二组)
        if is_long and config.MEANS_DEA1H_COUNT_2 != 0:
            dea1h_mean_2 = row.get('dea1h_mean_2', 0)
            if dea1h - config.DEA1H_MEANS_LIMIT_2 < dea1h_mean_2:
                is_long = False
                reasons.append(f"DEA1H均值2: {dea1h:.2f} - {config.DEA1H_MEANS_LIMIT_2:.2f} < {dea1h_mean_2:.2f}")

        # ========== 1天指标检查 ==========
        # HIST1D限制
        if is_long and (hist1d > config.T0_HIST1D_LIMIT or hist1d < config.T0_HIST1D_LIMIT_MIN):
            is_long = False
            reasons.append(f"HIST1D: {hist1d:.2f} config.T0_HIST1D_LIMIT:{config.T0_HIST1D_LIMIT} config.T0_HIST1D_LIMIT_MIN:{config.T0_HIST1D_LIMIT_MIN}")

        # DIF1D限制
        if is_long and (dif1d > config.T0_DIF1D_LIMIT or dif1d < config.T0_DIF1D_LIMIT_MIN):
            is_long = False
            reasons.append(f"DIF1D: {dif1d:.2f}")

        # HIST1D均值检查 (第一组)
        if is_long and config.MEANS_HIST1D_COUNT != 0:
            hist1d_mean = row.get('hist1d_mean', 0)
            if hist1d - config.HIST1D_MEANS_LIMIT < hist1d_mean:
                is_long = False
                reasons.append(f"HIST1D均值1: {hist1d:.2f} - {config.HIST1D_MEANS_LIMIT:.2f} < {hist1d_mean:.2f}")
                if debug_mode:
                    logger.warning(
                        f"❌ [{ts_str}] HIST1D均值1拒绝: {hist1d:.2f} - {config.HIST1D_MEANS_LIMIT} < {hist1d_mean:.2f}"
                    )
            elif debug_mode:
                logger.info(
                    f"✅ [{ts_str}] HIST1D均值1通过: {hist1d:.2f} - {config.HIST1D_MEANS_LIMIT} >= {hist1d_mean:.2f}"
                )

        # HIST1D均值检查 (第二组)
        if is_long and config.MEANS_HIST1D_COUNT_2 != 0:
            hist1d_mean_2 = row.get('hist1d_mean_2', 0)
            if hist1d - config.HIST1D_MEANS_LIMIT_2 < hist1d_mean_2:
                is_long = False
                reasons.append(f"HIST1D均值2: {hist1d:.2f} - {config.HIST1D_MEANS_LIMIT_2:.2f} < {hist1d_mean_2:.2f}")
                if debug_mode:
                    logger.warning(
                        f"❌ [{ts_str}] HIST1D均值2拒绝: {hist1d:.2f} - {config.HIST1D_MEANS_LIMIT_2} < {hist1d_mean_2:.2f}"
                    )
            elif debug_mode:
                logger.info(
                    f"✅ [{ts_str}] HIST1D均值2通过: {hist1d:.2f} - {config.HIST1D_MEANS_LIMIT_2} >= {hist1d_mean_2:.2f}"
                )

        # DIF1D均值检查 (第一组)
        if is_long and config.MEANS_DIF1D_COUNT != 0:
            dif1d_mean = row.get('dif1d_mean', 0)
            if dif1d - config.DIF1D_MEANS_LIMIT < dif1d_mean:
                is_long = False
                reasons.append(f"DIF1D均值1: {dif1d:.2f} - {config.DIF1D_MEANS_LIMIT:.2f} < {dif1d_mean:.2f}")

        # DIF1D均值检查 (第二组)
        if is_long and config.MEANS_DIF1D_COUNT_2 != 0:
            dif1d_mean_2 = row.get('dif1d_mean_2', 0)
            if dif1d - config.DIF1D_MEANS_LIMIT_2 < dif1d_mean_2:
                is_long = False
                reasons.append(f"DIF1D均值2: {dif1d:.2f} - {config.DIF1D_MEANS_LIMIT_2:.2f} < {dif1d_mean_2:.2f}")

        # DEA1D均值检查 (第一组)
        if is_long and config.MEANS_DEA1D_COUNT != 0:
            dea1d_mean = row.get('dea1d_mean', 0)
            if dea1d - config.DEA1D_MEANS_LIMIT < dea1d_mean:
                is_long = False
                reasons.append(f"DEA1D均值1: {dea1d:.2f} - {config.DEA1D_MEANS_LIMIT:.2f} < {dea1d_mean:.2f}")

        # DEA1D均值检查 (第二组)
        if is_long and config.MEANS_DEA1D_COUNT_2 != 0:
            dea1d_mean_2 = row.get('dea1d_mean_2', 0)
            if dea1d - config.DEA1D_MEANS_LIMIT_2 < dea1d_mean_2:
                is_long = False
                reasons.append(f"DEA1D均值2: {dea1d:.2f} - {config.DEA1D_MEANS_LIMIT_2:.2f} < {dea1d_mean_2:.2f}")

        # ========== 4小时指标检查 ==========
        # HIST4限制
        if is_long and (hist4 > config.T0_HIST4_LIMIT or hist4 < config.T0_HIST4_LIMIT_MIN):
            is_long = False
            reasons.append(f"HIST4: {hist4:.2f} config.T0_HIST4_LIMIT:{config.T0_HIST4_LIMIT} config.T0_HIST4_LIMIT_MIN:{config.T0_HIST4_LIMIT_MIN}")

        # DIF4限制
        if is_long and (dif4 > config.T0_DIF4_LIMIT or dif4 < config.T0_DIF4_LIMIT_MIN):
            is_long = False
            reasons.append(f"DIF4: {dif4:.2f} config.T0_DIF4_LIMIT:{config.T0_DIF4_LIMIT} config.T0_DIF4_LIMIT_MIN:{config.T0_DIF4_LIMIT_MIN}")

        # HIST4均值检查 (第一组)
        if is_long and config.MEANS_HIST4_COUNT != 0:
            hist4_mean = row.get('hist4_mean', 0)
            if hist4 - config.HIST4_MEANS_LIMIT < hist4_mean:
                is_long = False
                reasons.append(f"HIST4均值1: {hist4:.2f} - {config.HIST4_MEANS_LIMIT:.2f} < {hist4_mean:.2f}")

        # HIST4均值检查 (第二组)
        if is_long and config.MEANS_HIST4_COUNT_2 != 0:
            hist4_mean_2 = row.get('hist4_mean_2', 0)
            if hist4 - config.HIST4_MEANS_LIMIT_2 < hist4_mean_2:
                is_long = False
                reasons.append(f"HIST4均值2: {hist4:.2f} - {config.HIST4_MEANS_LIMIT_2:.2f} < {hist4_mean_2:.2f}")

        # DIF4均值检查 (第一组)
        if is_long and config.MEANS_DIF4_COUNT != 0:
            dif4_mean = row.get('dif4_mean', 0)
            if dif4 - config.DIF4_MEANS_LIMIT < dif4_mean:
                is_long = False
                reasons.append(f"DIF4均值1: {dif4:.2f} - {config.DIF4_MEANS_LIMIT:.2f} < {dif4_mean:.2f}")

        # DIF4均值检查 (第二组)
        if is_long and config.MEANS_DIF4_COUNT_2 != 0:
            dif4_mean_2 = row.get('dif4_mean_2', 0)
            if dif4 - config.DIF4_MEANS_LIMIT_2 < dif4_mean_2:
                is_long = False
                reasons.append(f"DIF4均值2: {dif4:.2f} - {config.DIF4_MEANS_LIMIT_2:.2f} < {dif4_mean_2:.2f}")

        # DEA4均值检查 (第一组)
        if is_long and config.MEANS_DEA4_COUNT != 0:
            dea4_mean = row.get('dea4_mean', 0)
            if dea4 - config.DEA4_MEANS_LIMIT < dea4_mean:
                is_long = False
                reasons.append(f"DEA4均值1: {dea4:.2f} - {config.DEA4_MEANS_LIMIT:.2f} < {dea4_mean:.2f}")

        # DEA4均值检查 (第二组)
        if is_long and config.MEANS_DEA4_COUNT_2 != 0:
            dea4_mean_2 = row.get('dea4_mean_2', 0)
            if dea4 - config.DEA4_MEANS_LIMIT_2 < dea4_mean_2:
                is_long = False
                reasons.append(f"DEA4均值2: {dea4:.2f} - {config.DEA4_MEANS_LIMIT_2:.2f} < {dea4_mean_2:.2f}")

        # ========== J指标检查 ==========
        if is_long and j_15m > config.T0_J15M_LIMIT:
            is_long = False
            reasons.append(f"J15: {j_15m:.2f}")
            if debug_mode:
                logger.warning(f"❌ [{ts_str}] J15超限: {j_15m:.2f} > {config.T0_J15M_LIMIT}")

        if is_long and j_1h > config.T0_J1H_LIMIT:
            is_long = False
            reasons.append(f"J1H: {j_1h:.2f}")
            if debug_mode:
                logger.warning(f"❌ [{ts_str}] J1H超限: {j_1h:.2f} > {config.T0_J1H_LIMIT}")

        if is_long and j_4h > config.T0_J4H_LIMIT:
            is_long = False
            reasons.append(f"J4H: {j_4h:.2f}")
            if debug_mode:
                logger.warning(f"❌ [{ts_str}] J4H超限: {j_4h:.2f} > {config.T0_J4H_LIMIT}")
        elif debug_mode and is_long:
            logger.info(f"✅ [{ts_str}] J4H检查: {j_4h:.2f} <= {config.T0_J4H_LIMIT}")

        # 通过所有检查
        if is_long:
            reason = f"多头开仓信号 H15={hist15:.2f} H1H={hist1h:.2f} H4={hist4:.2f}"
            if debug_mode:
                logger.info(f"🎉 [{ts_str}] ✅✅✅ 信号通过所有检查！ ✅✅✅")
                logger.info(f"🎉 [{ts_str}] {reason}")
            logger.debug(f"✓ 多头信号: {reason}")
            return True, reason
        else:
            logger.warning(f"❌ [{ts_str}] 多头信号被拒绝，原因: {'; '.join(reasons)}")
            # if debug_mode or self.debug_count % 100 == 0:  # 调试模式或每100次输出一次详细日志
            #     logger.warning(f"❌ [{ts_str}] 信号被拒绝，原因: {'; '.join(reasons)}")
            # elif not debug_mode:
            #     logger.debug(f"❌ [{ts_str}]  多头被过滤: {'; '.join(reasons)}")
            return False, "; ".join(reasons)

    def _check_short_signal(
        self,
        hist15, dif15, dea15, j_15m,
        hist1h, dif1h, dea1h, j_1h,
        hist4, dif4, dea4, j_4h,
        hist1d, dif1d, dea1d,
        row,
        row_prev=None,
        row_list=None,
        state_prices=None
    ) -> tuple:
        """
        检查做空信号

        Returns:
            (is_signal: bool, reason: str)
        """
        is_short = True
        reasons = []
        history_rows = row_list or []
        if '2024-01-03 12:01:59' in str(row.get('close_time')):
            self.logger.info(row)
            self.logger.info(row_prev)
            self.logger.info("=" * 80)

        # ========== 价格变化验证 (参考 macd_refactor.py) ==========
        if config.M_PRICE_CHANGE != 0 and config.M_PRICE_CHANGE_MINUTES > 0 and len(history_rows) >= config.M_PRICE_CHANGE_MINUTES:
            r = history_rows[-1 * config.M_PRICE_CHANGE_MINUTES:]
            r_high_max = max(item['high'] for item in r)
            r_low_min = min(item['low'] for item in r)
            r_range = r_high_max - r_low_min
            price_change_limit = config.M_PRICE_CHANGE if config.M_PRICE_CHANGE > 1 else row['close'] * config.M_PRICE_CHANGE
            if r_range > price_change_limit:
                is_short = False
                reasons.append(f"价格跳空: high_max={r_high_max:.2f}, low_min={r_low_min:.2f}, range={r_range:.2f}, limit={price_change_limit:.2f}")
                logger.debug(f"DEBUG: 跳过空头开仓 due to price range at {row.get('close_time')}, high_max={r_high_max}, low_min={r_low_min}, range={r_range}")
        if is_short and config.M_PRICE_CHANGE_B != 0 and config.M_PRICE_CHANGE_MINUTES_B > 0 and len(history_rows) >= config.M_PRICE_CHANGE_MINUTES_B:
            r = history_rows[-1 * config.M_PRICE_CHANGE_MINUTES_B:]
            r_high_max = max(item['high'] for item in r)
            r_low_min = min(item['low'] for item in r)
            r_range = r_high_max - r_low_min
            price_change_limit = config.M_PRICE_CHANGE_B if config.M_PRICE_CHANGE_B > 1 else row['close'] * config.M_PRICE_CHANGE_B
            if r_range > price_change_limit:
                is_short = False
                reasons.append(f"价格跳空: high_max={r_high_max:.2f}, low_min={r_low_min:.2f}, range={r_range:.2f}, limit={price_change_limit:.2f}")
                logger.debug(f"DEBUG: 跳过空头开仓 due to price range at {row.get('close_time')}, high_max={r_high_max}, low_min={r_low_min}, range={r_range}")

        if is_short and config.M_PRICE_CHANGE_C != 0 and config.M_PRICE_CHANGE_MINUTES_C > 0 and len(history_rows) >= config.M_PRICE_CHANGE_MINUTES_C:
            r = history_rows[-1 * config.M_PRICE_CHANGE_MINUTES_C:]
            r_high_max = max(item['high'] for item in r)
            r_low_min = min(item['low'] for item in r)
            r_range = r_high_max - r_low_min
            price_change_limit = config.M_PRICE_CHANGE_C if config.M_PRICE_CHANGE_C > 1 else row['close'] * config.M_PRICE_CHANGE_C
            if r_range > price_change_limit:
                is_short = False
                reasons.append(f"价格跳空: high_max={r_high_max:.2f}, low_min={r_low_min:.2f}, range={r_range:.2f}, limit={price_change_limit:.2f}")
                logger.debug(f"DEBUG: 跳过空头开仓 due to price range at {row.get('close_time')}, high_max={r_high_max}, low_min={r_low_min}, range={r_range}")

        # M_PRICE_CHANGE - 防止跳空开仓
        # if row_prev is not None and config.M_PRICE_CHANGE != 0:
        #     price_change_limit = config.M_PRICE_CHANGE if config.M_PRICE_CHANGE > 1 else row_prev['close'] * config.M_PRICE_CHANGE
        #     if abs(row['close'] - row_prev['close']) > price_change_limit:
        #         is_short = False
        #         reasons.append(f"价格跳空: close={row['close']:.2f}, prev_close={row_prev['close']:.2f}, diff={abs(row['close']-row_prev['close']):.2f}")
        #         logger.debug(f"DEBUG: 跳过空头开仓 due to price jump at {row.get('close_time')}, close={row['close']}, prev_close={row_prev['close']}, diff={abs(row['close']-row_prev['close'])}")

        # PRICE_CHANGE_COUNT
        if state_prices is not None and config.PRICE_CHANGE_COUNT > 0:
            max_price = state_prices.iloc[-1*config.PRICE_CHANGE_COUNT:].max()
            min_price = state_prices.iloc[-1*config.PRICE_CHANGE_COUNT:].min()
            if max_price > row['close'] + row['close'] * config.PRICE_CHANGE_LIMIT and min_price < row['close'] - row['close'] * config.PRICE_CHANGE_LIMIT:
                is_short = False
                reasons.append(f"价格变化限制_COUNT: min={min_price:.2f}, max={max_price:.2f}")
                logger.debug(f"DEBUG: 跳过空头开仓 due to price change limit at {row.get('close_time')}, min_price={min_price}, max_price={max_price}, close={row['close']}, limit={config.PRICE_CHANGE_LIMIT}")

        # PRICE_CHANGE_COUNT_B
        if state_prices is not None and config.PRICE_CHANGE_COUNT_B > 0:
            max_price_b = state_prices.iloc[-1*config.PRICE_CHANGE_COUNT_B:].max()
            min_price_b = state_prices.iloc[-1*config.PRICE_CHANGE_COUNT_B:].min()
            if max_price_b > row['close'] + row['close'] * config.PRICE_CHANGE_LIMIT_B and min_price_b < row['close'] - row['close'] * config.PRICE_CHANGE_LIMIT_B:
                is_short = False
                reasons.append(f"价格变化限制_COUNT_B: min={min_price_b:.2f}, max={max_price_b:.2f}")
                logger.debug(f"DEBUG: 跳过空头开仓 due to price change limit at {row.get('close_time')}, min_price_b={min_price_b}, max_price_b={max_price_b}, close={row['close']}, limit={config.PRICE_CHANGE_LIMIT_B}")

        # PRICE_CHANGE_COUNT_C
        if state_prices is not None and config.PRICE_CHANGE_COUNT_C > 0:
            max_price_c = state_prices.iloc[-1*config.PRICE_CHANGE_COUNT_C:].max()
            min_price_c = state_prices.iloc[-1*config.PRICE_CHANGE_COUNT_C:].min()
            if max_price_c > row['close'] + row['close'] * config.PRICE_CHANGE_LIMIT_C and min_price_c < row['close'] - row['close'] * config.PRICE_CHANGE_LIMIT_C:
                is_short = False
                reasons.append(f"价格变化限制_COUNT_C: min={min_price_c:.2f}, max={max_price_c:.2f}")
                logger.debug(f"DEBUG: 跳过空头开仓 due to price change limit at {row.get('close_time')}, min_price_c={min_price_c}, max_price_c={max_price_c}, close={row['close']}, limit={config.PRICE_CHANGE_LIMIT_C}")

        # ENABLE_MA5_MA10 - 成交量检查 (空头要求 vol_ma5 < vol_ma10)
        if config.ENABLE_MA5_MA10 and row.get('vol_ma5') is not None and row.get('vol_ma10') is not None:
            if row.get('vol_ma5') < row.get('vol_ma10'):
                is_short = False
                reasons.append(f"成交量MA: vol_ma5={row.get('vol_ma5'):.2f} < vol_ma10={row.get('vol_ma10'):.2f}")
                logger.debug(f"DEBUG: 跳过空头开仓 due to vol_ma5 < vol_ma10 at {row.get('close_time')}, vol_ma5={row.get('vol_ma5')}, vol_ma10={row.get('vol_ma10')}")

        # 如果价格验证失败，直接返回
        if not is_short:
            return False, "; ".join(reasons)

        # ========== 15分钟指标检查 ==========
        # HIST15限制 (空头符号相反)
        if hist15 < -1 * config.T0_HIST15_LIMIT or hist15 > -1 * config.T0_HIST15_LIMIT_MIN:
            is_short = False
            reasons.append(f"HIST15: {hist15:.2f}，T0_HIST15_LIMIT={config.T0_HIST15_LIMIT}, T0_HIST15_LIMIT_MIN={config.T0_HIST15_LIMIT_MIN}")
            return False, "; ".join(reasons)

        # DIF15限制 (空头符号相反)
        if is_short and (dif15 < -1 * config.T0_DIF15_LIMIT or dif15 > -1 * config.T0_DIF15_LIMIT_MIN):
            is_short = False
            reasons.append(f"DIF15: {dif15:.2f}，T0_DIF15_LIMIT={config.T0_DIF15_LIMIT}, T0_DIF15_LIMIT_MIN={config.T0_DIF15_LIMIT_MIN}")

        # DIF15均值检查 (第一组，空头符号相反)
        if is_short and config.MEANS_DIF15_COUNT != 0:
            dif15_mean = row.get('dif15_mean', 0)
            if dif15 + config.DIF15_MEANS_LIMIT > dif15_mean:
                is_short = False
                reasons.append(f"DIF15均值1: {dif15:.2f} > {dif15_mean:.2f}")

        # DIF15均值检查 (第二组，空头符号相反)
        if is_short and config.MEANS_DIF15_COUNT_2 != 0:
            dif15_mean_2 = row.get('dif15_mean_2', 0)
            if dif15 + config.DIF15_MEANS_LIMIT_2 > dif15_mean_2:
                is_short = False
                reasons.append(f"DIF15均值2: {dif15:.2f} > {dif15_mean_2:.2f}")

        # HIST15均值检查 (第一组，空头符号相反)
        if is_short and config.MEANS_HIST15_COUNT != 0:
            hist15_mean = row.get('hist15_mean', 0)
            if hist15 + config.HIST15_MEANS_LIMIT > hist15_mean:
                is_short = False
                reasons.append(f"HIST15均值1: {hist15:.2f} > {hist15_mean:.2f}")

        # HIST15均值检查 (第二组，空头符号相反)
        if is_short and config.MEANS_HIST15_COUNT_2 != 0:
            hist15_mean_2 = row.get('hist15_mean_2', 0)
            if hist15 + config.HIST15_MEANS_LIMIT_2 > hist15_mean_2:
                is_short = False
                reasons.append(f"HIST15均值2: {hist15:.2f} > {hist15_mean_2:.2f}")

        # DEA15均值检查 (第一组，空头符号相反)
        if is_short and config.MEANS_DEA15_COUNT != 0:
            dea15_mean = row.get('dea15_mean', 0)
            if dea15 + config.DEA15_MEANS_LIMIT > dea15_mean:
                is_short = False
                reasons.append(f"DEA15均值1: {dea15:.2f} > {dea15_mean:.2f}")

        # DEA15均值检查 (第二组，空头符号相反)
        if is_short and config.MEANS_DEA15_COUNT_2 != 0:
            dea15_mean_2 = row.get('dea15_mean_2', 0)
            if dea15 + config.DEA15_MEANS_LIMIT_2 > dea15_mean_2:
                is_short = False
                reasons.append(f"DEA15均值2: {dea15:.2f} > {dea15_mean_2:.2f}")

        # ========== 1小时指标检查 ==========
        # HIST1H限制 (空头符号相反)
        if is_short and (hist1h < -1 * config.T0_HIST1H_LIMIT or hist1h > -1 * config.T0_HIST1H_LIMIT_MIN):
            is_short = False
            reasons.append(f"HIST1H: {hist1h:.2f}，T0_HIST1H_LIMIT={config.T0_HIST1H_LIMIT}, T0_HIST1H_LIMIT_MIN={config.T0_HIST1H_LIMIT_MIN}")

        # DIF1H限制 (空头符号相反)
        if is_short and (dif1h < -1 * config.T0_DIF1H_LIMIT or dif1h > -1 * config.T0_DIF1H_LIMIT_MIN):
            is_short = False
            reasons.append(f"DIF1H: {dif1h:.2f}，T0_DIF1H_LIMIT={config.T0_DIF1H_LIMIT}, T0_DIF1H_LIMIT_MIN={config.T0_DIF1H_LIMIT_MIN}")

        # HIST1H均值检查 (第一组，空头符号相反)
        if is_short and config.MEANS_HIST1H_COUNT != 0:
            hist1h_mean = row.get('hist1h_mean', 0)
            if hist1h + config.HIST1H_MEANS_LIMIT > hist1h_mean:
                is_short = False
                reasons.append(f"HIST1H均值1: {hist1h:.2f} > {hist1h_mean:.2f}")

        # HIST1H均值检查 (第二组，空头符号相反)
        if is_short and config.MEANS_HIST1H_COUNT_2 != 0:
            hist1h_mean_2 = row.get('hist1h_mean_2', 0)
            if hist1h + config.HIST1H_MEANS_LIMIT_2 > hist1h_mean_2:
                is_short = False
                reasons.append(f"HIST1H均值2: {hist1h:.2f} > {hist1h_mean_2:.2f}")

        # DIF1H均值检查 (第一组，空头符号相反)
        if is_short and config.MEANS_DIF1H_COUNT != 0:
            dif1h_mean = row.get('dif1h_mean', 0)
            if dif1h + config.DIF1H_MEANS_LIMIT > dif1h_mean:
                is_short = False
                reasons.append(f"DIF1H均值1: {dif1h:.2f} > {dif1h_mean:.2f}")

        # DIF1H均值检查 (第二组，空头符号相反)
        if is_short and config.MEANS_DIF1H_COUNT_2 != 0:
            dif1h_mean_2 = row.get('dif1h_mean_2', 0)
            if dif1h + config.DIF1H_MEANS_LIMIT_2 > dif1h_mean_2:
                is_short = False
                reasons.append(f"DIF1H均值2: {dif1h:.2f} > {dif1h_mean_2:.2f}")

        # DEA1H均值检查 (第一组，空头符号相反)
        if is_short and config.MEANS_DEA1H_COUNT != 0:
            dea1h_mean = row.get('dea1h_mean', 0)
            if dea1h + config.DEA1H_MEANS_LIMIT > dea1h_mean:
                is_short = False
                reasons.append(f"DEA1H均值1: {dea1h:.2f} > {dea1h_mean:.2f}")

        # DEA1H均值检查 (第二组，空头符号相反)
        if is_short and config.MEANS_DEA1H_COUNT_2 != 0:
            dea1h_mean_2 = row.get('dea1h_mean_2', 0)
            if dea1h + config.DEA1H_MEANS_LIMIT_2 > dea1h_mean_2:
                is_short = False
                reasons.append(f"DEA1H均值2: {dea1h:.2f} > {dea1h_mean_2:.2f}")

        # ========== 1天指标检查 ==========
        # HIST1D限制 (空头符号相反)
        if is_short and (hist1d < -1 * config.T0_HIST1D_LIMIT or hist1d > -1 * config.T0_HIST1D_LIMIT_MIN):
            is_short = False
            reasons.append(f"HIST1D: {hist1d:.2f}，T0_HIST1D_LIMIT={config.T0_HIST1D_LIMIT}, T0_HIST1D_LIMIT_MIN={config.T0_HIST1D_LIMIT_MIN}")

        # DIF1D限制 (空头符号相反)
        if is_short and (dif1d < -1 * config.T0_DIF1D_LIMIT or dif1d > -1 * config.T0_DIF1D_LIMIT_MIN):
            is_short = False
            reasons.append(f"DIF1D: {dif1d:.2f}，T0_DIF1D_LIMIT={config.T0_DIF1D_LIMIT}, T0_DIF1D_LIMIT_MIN={config.T0_DIF1D_LIMIT_MIN}")

        # HIST1D均值检查 (第一组，空头符号相反)
        if is_short and config.MEANS_HIST1D_COUNT != 0:
            hist1d_mean = row.get('hist1d_mean', 0)
            if hist1d + config.HIST1D_MEANS_LIMIT > hist1d_mean:
                is_short = False
                reasons.append(f"HIST1D均值1: {hist1d:.2f} > {hist1d_mean:.2f}")

        # HIST1D均值检查 (第二组，空头符号相反)
        if is_short and config.MEANS_HIST1D_COUNT_2 != 0:
            hist1d_mean_2 = row.get('hist1d_mean_2', 0)
            if hist1d + config.HIST1D_MEANS_LIMIT_2 > hist1d_mean_2:
                is_short = False
                reasons.append(f"HIST1D均值2: {hist1d:.2f} > {hist1d_mean_2:.2f}")

        # DIF1D均值检查 (第一组，空头符号相反)
        if is_short and config.MEANS_DIF1D_COUNT != 0:
            dif1d_mean = row.get('dif1d_mean', 0)
            if dif1d + config.DIF1D_MEANS_LIMIT > dif1d_mean:
                is_short = False
                reasons.append(f"DIF1D均值1: {dif1d:.2f} > {dif1d_mean:.2f}")

        # DIF1D均值检查 (第二组，空头符号相反)
        if is_short and config.MEANS_DIF1D_COUNT_2 != 0:
            dif1d_mean_2 = row.get('dif1d_mean_2', 0)
            if dif1d + config.DIF1D_MEANS_LIMIT_2 > dif1d_mean_2:
                is_short = False
                reasons.append(f"DIF1D均值2: {dif1d:.2f} > {dif1d_mean_2:.2f}")

        # DEA1D均值检查 (第一组，空头符号相反)
        if is_short and config.MEANS_DEA1D_COUNT != 0:
            dea1d_mean = row.get('dea1d_mean', 0)
            if dea1d + config.DEA1D_MEANS_LIMIT > dea1d_mean:
                is_short = False
                reasons.append(f"DEA1D均值1: {dea1d:.2f} > {dea1d_mean:.2f}")

        # DEA1D均值检查 (第二组，空头符号相反)
        if is_short and config.MEANS_DEA1D_COUNT_2 != 0:
            dea1d_mean_2 = row.get('dea1d_mean_2', 0)
            if dea1d + config.DEA1D_MEANS_LIMIT_2 > dea1d_mean_2:
                is_short = False
                reasons.append(f"DEA1D均值2: {dea1d:.2f} > {dea1d_mean_2:.2f}")

        # ========== 4小时指标检查 ==========
        # HIST4限制 (空头符号相反)
        if is_short and (hist4 < -1 * config.T0_HIST4_LIMIT or hist4 > -1 * config.T0_HIST4_LIMIT_MIN):
            is_short = False
            reasons.append(f"HIST4: {hist4:.2f}，T0_HIST4_LIMIT={config.T0_HIST4_LIMIT}, T0_HIST4_LIMIT_MIN={config.T0_HIST4_LIMIT_MIN}")

        # DIF4限制 (空头符号相反)
        if is_short and (dif4 < -1 * config.T0_DIF4_LIMIT or dif4 > -1 * config.T0_DIF4_LIMIT_MIN):
            is_short = False
            reasons.append(f"DIF4: {dif4:.2f}，T0_DIF4_LIMIT={config.T0_DIF4_LIMIT}, T0_DIF4_LIMIT_MIN={config.T0_DIF4_LIMIT_MIN}")

        # HIST4均值检查 (第一组，空头符号相反)
        if is_short and config.MEANS_HIST4_COUNT != 0:
            hist4_mean = row.get('hist4_mean', 0)
            if hist4 + config.HIST4_MEANS_LIMIT > hist4_mean:
                is_short = False
                reasons.append(f"HIST4均值1: {hist4:.2f} > {hist4_mean:.2f}")

        # HIST4均值检查 (第二组，空头符号相反)
        if is_short and config.MEANS_HIST4_COUNT_2 != 0:
            hist4_mean_2 = row.get('hist4_mean_2', 0)
            if hist4 + config.HIST4_MEANS_LIMIT_2 > hist4_mean_2:
                is_short = False
                reasons.append(f"HIST4均值2: {hist4:.2f} > {hist4_mean_2:.2f}")

        # DIF4均值检查 (第一组，空头符号相反)
        if is_short and config.MEANS_DIF4_COUNT != 0:
            dif4_mean = row.get('dif4_mean', 0)
            if dif4 + config.DIF4_MEANS_LIMIT > dif4_mean:
                is_short = False
                reasons.append(f"DIF4均值1: {dif4:.2f} > {dif4_mean:.2f}")

        # DIF4均值检查 (第二组，空头符号相反)
        if is_short and config.MEANS_DIF4_COUNT_2 != 0:
            dif4_mean_2 = row.get('dif4_mean_2', 0)
            if dif4 + config.DIF4_MEANS_LIMIT_2 > dif4_mean_2:
                is_short = False
                reasons.append(f"DIF4均值2: {dif4:.2f} > {dif4_mean_2:.2f}")

        # DEA4均值检查 (第一组，空头符号相反)
        if is_short and config.MEANS_DEA4_COUNT != 0:
            dea4_mean = row.get('dea4_mean', 0)
            if dea4 + config.DEA4_MEANS_LIMIT > dea4_mean:
                is_short = False
                reasons.append(f"DEA4均值1: {dea4:.2f} > {dea4_mean:.2f}")

        # DEA4均值检查 (第二组，空头符号相反)
        if is_short and config.MEANS_DEA4_COUNT_2 != 0:
            dea4_mean_2 = row.get('dea4_mean_2', 0)
            if dea4 + config.DEA4_MEANS_LIMIT_2 > dea4_mean_2:
                is_short = False
                reasons.append(f"DEA4均值2: {dea4:.2f} > {dea4_mean_2:.2f}")

        # ========== J指标检查 (空头符号相反) ==========
        if is_short and j_15m < config.T0_J15M_LIMIT_KONG:
            is_short = False
            reasons.append(f"J15: {j_15m:.2f}，T0_J15M_LIMIT_KONG={config.T0_J15M_LIMIT_KONG}")

        if is_short and j_1h < config.T0_J1H_LIMIT_KONG:
            is_short = False
            reasons.append(f"J1H: {j_1h:.2f}，T0_J1H_LIMIT_KONG={config.T0_J1H_LIMIT_KONG}")
        if is_short and j_4h < config.T0_J4H_LIMIT_KONG:
            is_short = False
            reasons.append(f"J4H: {j_4h:.2f}，T0_J4H_LIMIT_KONG={config.T0_J4H_LIMIT_KONG}")

        # 通过所有检查
        if is_short:
            reason = f"空头开仓信号 H15={hist15:.2f} H1H={hist1h:.2f} H4={hist4:.2f}"
            logger.debug(f"✓ 空头信号: {reason}")
            return True, reason
        else:
            ts_str = str(row.get('open_time', ''))
            logger.warning(f"❌ [{ts_str}] 空头信号被拒绝，原因: {'; '.join(reasons)}")
            # if self.debug_count % 100 == 0:  # 每100次输出一次详细日志
            #     logger.debug(f"✗ 空头被过滤: {'; '.join(reasons)}")
            return False, "; ".join(reasons)
            return False, "; ".join(reasons)

    # ==================== 参数导出接口 ====================

    @staticmethod
    def get_signal_params() -> Dict[str, Any]:
        """
        返回信号计算和交易引擎实际使用的全部运行时参数。

        直接从 config 单例读取当前值，保证与运行时一致。
        key 使用 config 属性名的小写形式。
        """
        return {
            # ===== 基础配置 =====
            'symbol': config.SYMBOL,
            'version': getattr(config, 'VERSION', 'V5.0'),
            'kline_interval': config.KLINE_INTERVAL,

            # ===== 仓位配置 =====
            'position_btc': config.POSITION_BTC,
            'contract_notional': config.CONTRACT_NOTIONAL,
            'leverage': config.LEVERAGE,
            'position_nominal': config.POSITION_NOMINAL,
            'no_limit_pos': config.NO_LIMIT_POS,

            # ===== MACD指标参数 =====
            'macd_fast': config.MACD_FAST,
            'macd_slow': config.MACD_SLOW,
            'macd_signal': config.MACD_SIGNAL,

            # ===== T0参数-15分钟 =====
            't0_hist15_limit': config.T0_HIST15_LIMIT,
            't0_hist15_limit_min': config.T0_HIST15_LIMIT_MIN,
            't0_hist15_limit_max': config.T0_HIST15_LIMIT_MAX,
            't0_hist15_count': config.T0_HIST15_COUNT,
            't0_dif15_limit': config.T0_DIF15_LIMIT,
            't0_dif15_limit_min': config.T0_DIF15_LIMIT_MIN,
            't0_j15m_limit': config.T0_J15M_LIMIT,
            't0_j15m_limit_kong': config.T0_J15M_LIMIT_KONG,

            # ===== T0参数-1小时 =====
            't0_hist1h_limit': config.T0_HIST1H_LIMIT,
            't0_hist1h_limit_min': config.T0_HIST1H_LIMIT_MIN,
            't0_dif1h_limit': config.T0_DIF1H_LIMIT,
            't0_dif1h_limit_min': config.T0_DIF1H_LIMIT_MIN,
            't0_j1h_limit': config.T0_J1H_LIMIT,
            't0_j1h_limit_kong': config.T0_J1H_LIMIT_KONG,

            # ===== T0参数-4小时 =====
            't0_hist4_limit': config.T0_HIST4_LIMIT,
            't0_hist4_limit_min': config.T0_HIST4_LIMIT_MIN,
            't0_dif4_limit': config.T0_DIF4_LIMIT,
            't0_dif4_limit_min': config.T0_DIF4_LIMIT_MIN,
            't0_j4h_limit': config.T0_J4H_LIMIT,
            't0_j4h_limit_kong': config.T0_J4H_LIMIT_KONG,
            't0_dea4_limit': config.T0_DEA4_LIMIT,

            # ===== T0参数-1天 =====
            't0_hist1d_limit': config.T0_HIST1D_LIMIT,
            't0_hist1d_limit_min': config.T0_HIST1D_LIMIT_MIN,
            't0_dif1d_limit': config.T0_DIF1D_LIMIT,
            't0_dif1d_limit_min': config.T0_DIF1D_LIMIT_MIN,
            't0_hist_1d_limit': config.T0_HIST_1D_LIMIT,

            # ===== 均值参数-第一组(15m) =====
            'means_hist15_count': config.MEANS_HIST15_COUNT,
            'hist15_means_limit': config.HIST15_MEANS_LIMIT,
            'means_dif15_count': config.MEANS_DIF15_COUNT,
            'dif15_means_limit': config.DIF15_MEANS_LIMIT,
            'means_dea15_count': config.MEANS_DEA15_COUNT,
            'dea15_means_limit': config.DEA15_MEANS_LIMIT,

            # ===== 均值参数-第一组(1h) =====
            'means_hist1h_count': config.MEANS_HIST1H_COUNT,
            'hist1h_means_limit': config.HIST1H_MEANS_LIMIT,
            'means_dif1h_count': config.MEANS_DIF1H_COUNT,
            'dif1h_means_limit': config.DIF1H_MEANS_LIMIT,
            'means_dea1h_count': config.MEANS_DEA1H_COUNT,
            'dea1h_means_limit': config.DEA1H_MEANS_LIMIT,

            # ===== 均值参数-第一组(4h) =====
            'means_hist4_count': config.MEANS_HIST4_COUNT,
            'hist4_means_limit': config.HIST4_MEANS_LIMIT,
            'means_dif4_count': config.MEANS_DIF4_COUNT,
            'dif4_means_limit': config.DIF4_MEANS_LIMIT,
            'means_dea4_count': config.MEANS_DEA4_COUNT,
            'dea4_means_limit': config.DEA4_MEANS_LIMIT,

            # ===== 均值参数-第一组(1d) =====
            'means_hist1d_count': config.MEANS_HIST1D_COUNT,
            'hist1d_means_limit': config.HIST1D_MEANS_LIMIT,
            'means_dif1d_count': config.MEANS_DIF1D_COUNT,
            'dif1d_means_limit': config.DIF1D_MEANS_LIMIT,
            'means_dea1d_count': config.MEANS_DEA1D_COUNT,
            'dea1d_means_limit': config.DEA1D_MEANS_LIMIT,

            # ===== 均值参数-第二组(15m) =====
            'means_hist15_count_2': config.MEANS_HIST15_COUNT_2,
            'hist15_means_limit_2': config.HIST15_MEANS_LIMIT_2,
            'means_dif15_count_2': config.MEANS_DIF15_COUNT_2,
            'dif15_means_limit_2': config.DIF15_MEANS_LIMIT_2,
            'means_dea15_count_2': config.MEANS_DEA15_COUNT_2,
            'dea15_means_limit_2': config.DEA15_MEANS_LIMIT_2,

            # ===== 均值参数-第二组(1h) =====
            'means_hist1h_count_2': config.MEANS_HIST1H_COUNT_2,
            'hist1h_means_limit_2': config.HIST1H_MEANS_LIMIT_2,
            'means_dif1h_count_2': config.MEANS_DIF1H_COUNT_2,
            'dif1h_means_limit_2': config.DIF1H_MEANS_LIMIT_2,
            'means_dea1h_count_2': config.MEANS_DEA1H_COUNT_2,
            'dea1h_means_limit_2': config.DEA1H_MEANS_LIMIT_2,

            # ===== 均值参数-第二组(4h) =====
            'means_hist4_count_2': config.MEANS_HIST4_COUNT_2,
            'hist4_means_limit_2': config.HIST4_MEANS_LIMIT_2,
            'means_dif4_count_2': config.MEANS_DIF4_COUNT_2,
            'dif4_means_limit_2': config.DIF4_MEANS_LIMIT_2,
            'means_dea4_count_2': config.MEANS_DEA4_COUNT_2,
            'dea4_means_limit_2': config.DEA4_MEANS_LIMIT_2,

            # ===== 均值参数-第二组(1d) =====
            'means_hist1d_count_2': config.MEANS_HIST1D_COUNT_2,
            'hist1d_means_limit_2': config.HIST1D_MEANS_LIMIT_2,
            'means_dif1d_count_2': config.MEANS_DIF1D_COUNT_2,
            'dif1d_means_limit_2': config.DIF1D_MEANS_LIMIT_2,
            'means_dea1d_count_2': config.MEANS_DEA1D_COUNT_2,
            'dea1d_means_limit_2': config.DEA1D_MEANS_LIMIT_2,

            # ===== 价格变化参数 =====
            'price_change_limit': config.PRICE_CHANGE_LIMIT,
            'price_change_count': config.PRICE_CHANGE_COUNT,
            'price_change_limit_b': config.PRICE_CHANGE_LIMIT_B,
            'price_change_count_b': config.PRICE_CHANGE_COUNT_B,
            'price_change_limit_c': config.PRICE_CHANGE_LIMIT_C,
            'price_change_count_c': config.PRICE_CHANGE_COUNT_C,
            'price_change_limit_d': config.PRICE_CHANGE_LIMIT_D,
            'price_change_count_d': config.PRICE_CHANGE_COUNT_D,
            'price_change_limit_e': config.PRICE_CHANGE_LIMIT_E,
            'price_change_count_e': config.PRICE_CHANGE_COUNT_E,
            'm_price_change': config.M_PRICE_CHANGE,
            'm_price_change_minutes': config.M_PRICE_CHANGE_MINUTES,
            'm_price_change_b': config.M_PRICE_CHANGE_B,
            'm_price_change_minutes_b': config.M_PRICE_CHANGE_MINUTES_B,
            'm_price_change_c': config.M_PRICE_CHANGE_C,
            'm_price_change_minutes_c': config.M_PRICE_CHANGE_MINUTES_C,
            'm_price_change_d': config.M_PRICE_CHANGE_D,
            'm_price_change_minutes_d': config.M_PRICE_CHANGE_MINUTES_D,
            'm_price_change_e': config.M_PRICE_CHANGE_E,
            'm_price_change_minutes_e': config.M_PRICE_CHANGE_MINUTES_E,

            # ===== 止盈止损 =====
            'stop_loss_points': config.STOP_LOSS_POINTS,
            'tp_levels': list(config.TP_LEVELS) if config.TP_LEVELS else [],
            'tp_ratio_per_level': config.TP_RATIO_PER_LEVEL,
            'drawdown_points': config.DRAWDOWN_POINTS,
            'stop_loss_hold_time': config.STOP_LOSS_HOLD_TIME,
            'close_time_minutes': config.CLOSE_TIME_MINUTES,
            'close_decay_points': config.CLOSE_DECAY_POINTS,
            'timeout_close_ratio': config.TIMEOUT_CLOSE_RATIO,

            # ===== T1参数 =====
            't1_t0_hist_change': config.T1_T0_HIST_CHANGE,
            't1_t0_dif_change': config.T1_T0_DIF_CHANGE,
            't1_t0_dea_change': config.T1_T0_DEA_CHANGE,
            't1_t0_hist_limit': config.T1_T0_HIST_LIMIT,
            't1_hist15_limit': config.T1_HIST15_LIMIT,
            't1_hist15_max': config.T1_HIST15_MAX,
            't1_dif4_limit': config.T1_DIF4_LIMIT,

            # ===== 特殊参数 =====
            'hist4_extreme_limit': config.HIST4_EXTREME_LIMIT,
            'hist4_neutral_band': config.HIST4_NEUTRAL_BAND,
            'dif4_t0_min_change': config.DIF4_T0_MIN_CHANGE,
            'enable_ma5_ma10': config.ENABLE_MA5_MA10,
            't0_lock_enabled': config.T0_LOCK_ENABLED,

            # ===== 手续费 =====
            'maker_fee_rate': config.MAKER_FEE_RATE,
            'taker_fee_rate': config.TAKER_FEE_RATE,
            'fee_rate': config.FEE_RATE,
            'open_taker_or_maker': config.OPEN_TAKER_OR_MAKER,
            'open_maker_price_ratio': config.OPEN_MAKER_PRICE_RATIO,
            'open_maker_duration_minutes': config.OPEN_MAKER_DURATION_MINUTES,
        }

    @staticmethod
    def export_signal_params(filepath: str = None):
        """
        将当前运行时参数导出为 JSON 文件，供 Web 等外部模块读取。

        Args:
            filepath: 导出路径，默认 data/running_signal_params.json
        """
        if filepath is None:
            filepath = str(
                Path(__file__).parent.parent / 'data' / 'running_signal_params.json'
            )

        params = SignalCalculator.get_signal_params()
        tz_east8 = timezone(timedelta(hours=8))
        params['_exported_at'] = datetime.now(tz_east8).strftime('%Y-%m-%d %H:%M:%S')

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(params, f, indent=2, ensure_ascii=False)
            # logger.debug(f"运行时参数已导出: {filepath}")
        except Exception as e:
            logger.error(f"导出运行时参数失败: {e}")
