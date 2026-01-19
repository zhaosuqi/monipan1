#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
信号计算器 - 基于MACD V5.0算法

参考: archive_old/macd_refactor.py 中的 macd_v5_0_signal 函数
集成移动平均值实时计算功能
"""

import pandas as pd
from dataclasses import dataclass
from typing import Optional, Dict, Any

from core.logger import get_logger
from core.config import config
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

    def calculate_open_signal(self, indicators: Dict[str, Any], row_prev=None, state_prices=None) -> Optional[Signal]:
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

        # ========== 价格变化验证 (参考 macd_refactor.py) ==========
        # M_PRICE_CHANGE - 防止跳空开仓
        if row_prev is not None and config.M_PRICE_CHANGE != 0:
            price_change_limit = config.M_PRICE_CHANGE if config.M_PRICE_CHANGE > 1 else row_prev['close'] * config.M_PRICE_CHANGE
            if abs(row['close'] - row_prev['close']) > price_change_limit:
                is_long = False
                reasons.append(f"价格跳空: close={row['close']:.2f}, prev_close={row_prev['close']:.2f}, diff={abs(row['close']-row_prev['close']):.2f}")
                logger.debug(f"DEBUG: 跳过多头开仓 due to price jump at {row.get('close_time')}, close={row['close']}, prev_close={row_prev['close']}, diff={abs(row['close']-row_prev['close'])}")

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
            reasons.append(f"DIF15: {dif15:.2f}")

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
        state_prices=None
    ) -> tuple:
        """
        检查做空信号

        Returns:
            (is_signal: bool, reason: str)
        """
        is_short = True
        reasons = []
        if '2024-01-03 12:01:59' in str(row.get('close_time')):
            self.logger.info(row)
            self.logger.info(row_prev)
            self.logger.info("=" * 80)

        # ========== 价格变化验证 (参考 macd_refactor.py) ==========
        # M_PRICE_CHANGE - 防止跳空开仓
        if row_prev is not None and config.M_PRICE_CHANGE != 0:
            price_change_limit = config.M_PRICE_CHANGE if config.M_PRICE_CHANGE > 1 else row_prev['close'] * config.M_PRICE_CHANGE
            if abs(row['close'] - row_prev['close']) > price_change_limit:
                is_short = False
                reasons.append(f"价格跳空: close={row['close']:.2f}, prev_close={row_prev['close']:.2f}, diff={abs(row['close']-row_prev['close']):.2f}")
                logger.debug(f"DEBUG: 跳过空头开仓 due to price jump at {row.get('close_time')}, close={row['close']}, prev_close={row_prev['close']}, diff={abs(row['close']-row_prev['close'])}")

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
