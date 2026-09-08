#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V5.0 新增过滤逻辑测试（对齐 bigtree/macd_refactor.py）：
- F/G 组防插针（M_PRICE_CHANGE）与价格变化窗口（PRICE_CHANGE）
- M_PRICE_CHANGE 上下界判定（窗口含当前K线）
- PRICE_CHANGE 窗口极差判定
- SAFE_RANGE 安全范围锚点检查
- ENABLE_MA5_MA10 已停用
"""

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import config
from signal_module.signal_calculator import (
    SignalCalculator,
    _find_safe_range_anchor,
    _pass_safe_range,
)


def _permissive_config(monkeypatch):
    """把所有信号阈值设为宽松值，只保留被测的过滤组。"""
    for name in ("HIST15", "DIF15", "HIST1H", "DIF1H", "HIST4", "DIF4", "HIST1D", "DIF1D"):
        monkeypatch.setattr(config, f"T0_{name}_LIMIT", 9999.0)
        monkeypatch.setattr(config, f"T0_{name}_LIMIT_MIN", -9999.0)
    monkeypatch.setattr(config, "T0_J15M_LIMIT", 999.0)
    monkeypatch.setattr(config, "T0_J1H_LIMIT", 999.0)
    monkeypatch.setattr(config, "T0_J4H_LIMIT", 999.0)
    monkeypatch.setattr(config, "T0_J15M_LIMIT_KONG", -999.0)
    monkeypatch.setattr(config, "T0_J1H_LIMIT_KONG", -999.0)
    monkeypatch.setattr(config, "T0_J4H_LIMIT_KONG", -999.0)
    # 关闭所有均值组
    for prefix in ("MEANS_HIST15", "MEANS_DIF15", "MEANS_DEA15",
                   "MEANS_HIST1H", "MEANS_DIF1H", "MEANS_DEA1H",
                   "MEANS_HIST4", "MEANS_DIF4", "MEANS_DEA4",
                   "MEANS_HIST1D", "MEANS_DIF1D", "MEANS_DEA1D"):
        monkeypatch.setattr(config, f"{prefix}_COUNT", 0)
        monkeypatch.setattr(config, f"{prefix}_COUNT_2", 0)
    # 关闭全部防插针/价格窗口/安全范围组，由各用例按需打开
    for suffix in ("", "_B", "_C", "_D", "_E", "_F", "_G"):
        monkeypatch.setattr(config, f"M_PRICE_CHANGE{suffix}", 0.0)
        monkeypatch.setattr(config, f"M_PRICE_CHANGE_MINUTES{suffix}", 0)
        monkeypatch.setattr(config, f"PRICE_CHANGE_COUNT{suffix}", 0)
        monkeypatch.setattr(config, f"PRICE_CHANGE_LIMIT{suffix}", 0.0)
    for suffix in ("", "_B", "_C"):
        monkeypatch.setattr(config, f"SAFE_RANGE_WINDOW_HOURS{suffix}", 0.0)
        monkeypatch.setattr(config, f"SAFE_RANGE_SWING_RATIO{suffix}", 0.0)
        monkeypatch.setattr(config, f"SAFE_RANGE_NEAR_RATIO{suffix}", 0.0)


def _make_calc():
    return SignalCalculator()


def _long_args(row, history, state_prices=None):
    return (
        0.0, 0.0, 0.0, 0.0,      # hist15, dif15, dea15, j_15m
        0.0, 0.0, 0.0, 0.0,      # hist1h, dif1h, dea1h, j_1h
        0.0, 0.0, 0.0, 0.0,      # hist4, dif4, dea4, j_4h
        0.0, 0.0, 0.0,           # hist1d, dif1d, dea1d
        row, None, history, state_prices, "",
    )


def _row(close, high, low):
    return {"close": close, "high": high, "low": low, "close_time": "2026-09-08 10:00:59"}


def _short_args(row, history, state_prices=None):
    # _check_short_signal 没有 ts_str 参数
    return _long_args(row, history, state_prices)[:-1]


# ==================== _find_safe_range_anchor ====================

def test_safe_range_anchor_long_found():
    # 多头：最近低点 L=99（<=130*0.98），L 之前最高收盘价 150 为锚点
    result = _find_safe_range_anchor([150, 100, 130, 99], 130.0, 0.02, 'long')
    assert result is not None
    assert result.anchor == 150.0
    assert result.leg_price == 99.0


def test_safe_range_anchor_long_no_leg_returns_none():
    # 窗口内没有任何 close <= s*(1-swing)，视为安全
    assert _find_safe_range_anchor([129, 130, 131], 130.0, 0.02, 'long') is None


def test_safe_range_anchor_long_leg_at_window_start_returns_none():
    # L 位于窗口起点，之前没有 K 线可取极值
    assert _find_safe_range_anchor([99, 150, 130], 130.0, 0.02, 'long') is None


def test_safe_range_anchor_short_mirror():
    # 空头镜像：最近高点 A=105（>=95*1.02），A 之前最低收盘价 80 为锚点
    result = _find_safe_range_anchor([90, 110, 80, 105], 95.0, 0.02, 'short')
    assert result is not None
    assert result.anchor == 80.0
    assert result.leg_price == 105.0


def test_safe_range_anchor_invalid_inputs():
    assert _find_safe_range_anchor([], 100.0, 0.02, 'long') is None
    assert _find_safe_range_anchor([100, 99], 0.0, 0.02, 'long') is None
    assert _find_safe_range_anchor([100, 99], 100.0, 0.0, 'long') is None


# ==================== _pass_safe_range ====================

def test_safe_range_disabled_by_default(monkeypatch):
    _permissive_config(monkeypatch)
    history = [{"close": c} for c in [150, 100, 130, 99]]
    assert _pass_safe_range(history, _row(150.05, 151, 149), "多头") is True


def test_safe_range_blocks_long_near_anchor(monkeypatch):
    _permissive_config(monkeypatch)
    monkeypatch.setattr(config, "SAFE_RANGE_WINDOW_HOURS", 1.0)
    monkeypatch.setattr(config, "SAFE_RANGE_SWING_RATIO", 0.02)
    monkeypatch.setattr(config, "SAFE_RANGE_NEAR_RATIO", 0.001)
    history = [{"close": c} for c in [150, 100, 130, 99]]
    # 当前价 150.05 在锚点 150 的 ±0.1% 内 → 放弃追多
    assert _pass_safe_range(history, _row(150.05, 151, 149), "多头") is False


def test_safe_range_passes_long_far_from_anchor(monkeypatch):
    _permissive_config(monkeypatch)
    monkeypatch.setattr(config, "SAFE_RANGE_WINDOW_HOURS", 1.0)
    monkeypatch.setattr(config, "SAFE_RANGE_SWING_RATIO", 0.02)
    monkeypatch.setattr(config, "SAFE_RANGE_NEAR_RATIO", 0.001)
    history = [{"close": c} for c in [150, 100, 130, 99]]
    # 当前价 160 距锚点 150 超过 0.1% → 放行
    assert _pass_safe_range(history, _row(160.0, 161, 159), "多头") is True


def test_safe_range_blocks_short_near_anchor(monkeypatch):
    _permissive_config(monkeypatch)
    monkeypatch.setattr(config, "SAFE_RANGE_WINDOW_HOURS_B", 1.0)
    monkeypatch.setattr(config, "SAFE_RANGE_SWING_RATIO_B", 0.02)
    monkeypatch.setattr(config, "SAFE_RANGE_NEAR_RATIO_B", 0.001)
    history = [{"close": c} for c in [90, 110, 80, 105]]
    # 当前价 80.05 在锚点 80 的 ±0.1% 内 → 放弃追空（B组也生效）
    assert _pass_safe_range(history, _row(80.05, 81, 79), "空头") is False


# ==================== M_PRICE_CHANGE 新判定逻辑 ====================

def test_m_price_change_blocks_when_history_high_exceeds_upper(monkeypatch):
    _permissive_config(monkeypatch)
    monkeypatch.setattr(config, "M_PRICE_CHANGE", 2.0)        # 绝对点数
    monkeypatch.setattr(config, "M_PRICE_CHANGE_MINUTES", 1)
    calc = _make_calc()
    # close=100 → 上界102 下界98；历史 high=103 超上界 → 拒绝
    history = [{"close": 100.0, "high": 103.0, "low": 99.8}]
    ok, _ = calc._check_long_signal(*_long_args(_row(100.0, 100.5, 99.5), history))
    assert ok is False


def test_m_price_change_window_includes_current_bar(monkeypatch):
    _permissive_config(monkeypatch)
    monkeypatch.setattr(config, "M_PRICE_CHANGE", 2.0)
    monkeypatch.setattr(config, "M_PRICE_CHANGE_MINUTES", 1)
    calc = _make_calc()
    # 历史K线完全平稳，但当前K线 high=105 超过上界102 → 拒绝（证明窗口含当前K线）
    history = [{"close": 100.0, "high": 100.2, "low": 99.8}]
    ok, _ = calc._check_long_signal(*_long_args(_row(100.0, 105.0, 99.9), history))
    assert ok is False


def test_m_price_change_passes_within_bounds(monkeypatch):
    _permissive_config(monkeypatch)
    monkeypatch.setattr(config, "M_PRICE_CHANGE", 2.0)
    monkeypatch.setattr(config, "M_PRICE_CHANGE_MINUTES", 1)
    calc = _make_calc()
    history = [{"close": 100.0, "high": 101.0, "low": 99.0}]
    ok, _ = calc._check_long_signal(*_long_args(_row(100.0, 100.5, 99.5), history))
    assert ok is True


def test_m_price_change_group_f_is_wired(monkeypatch):
    _permissive_config(monkeypatch)
    # 只打开 F 组，验证新增组生效
    monkeypatch.setattr(config, "M_PRICE_CHANGE_F", 2.0)
    monkeypatch.setattr(config, "M_PRICE_CHANGE_MINUTES_F", 6)
    calc = _make_calc()
    history = [{"close": 100.0, "high": 100.1, "low": 99.9}] * 5 + [
        {"close": 100.0, "high": 103.0, "low": 99.9}
    ]
    ok, _ = calc._check_long_signal(*_long_args(_row(100.0, 100.5, 99.5), history))
    assert ok is False


def test_m_price_change_short_blocks_when_low_breaks_lower(monkeypatch):
    _permissive_config(monkeypatch)
    monkeypatch.setattr(config, "M_PRICE_CHANGE", 2.0)
    monkeypatch.setattr(config, "M_PRICE_CHANGE_MINUTES", 1)
    calc = _make_calc()
    # close=100 → 下界98；历史 low=97 破下界 → 空头也拒绝
    history = [{"close": 100.0, "high": 100.3, "low": 97.0}]
    ok, _ = calc._check_short_signal(*_short_args(_row(100.0, 100.5, 99.5), history))
    assert ok is False


# ==================== PRICE_CHANGE 窗口极差判定 ====================

def test_price_change_window_diff_logic(monkeypatch):
    _permissive_config(monkeypatch)
    monkeypatch.setattr(config, "PRICE_CHANGE_COUNT", 5)
    monkeypatch.setattr(config, "PRICE_CHANGE_LIMIT", 0.01)
    calc = _make_calc()
    # close=100 → 允许波动1.0；窗口收盘极差 101.2-99.0=2.2 > 1.0 → 拒绝
    # 旧逻辑（max>上界 且 min<下界）会放行：min=99 未跌破 99
    state_prices = pd.Series([101.2, 99.0, 100.3, 100.1, 100.0])
    ok, _ = calc._check_long_signal(*_long_args(_row(100.0, 100.5, 99.5), [], state_prices))
    assert ok is False


def test_price_change_window_passes_small_diff(monkeypatch):
    _permissive_config(monkeypatch)
    monkeypatch.setattr(config, "PRICE_CHANGE_COUNT", 5)
    monkeypatch.setattr(config, "PRICE_CHANGE_LIMIT", 0.01)
    calc = _make_calc()
    state_prices = pd.Series([100.4, 99.7, 100.2, 100.1, 100.0])
    ok, _ = calc._check_long_signal(*_long_args(_row(100.0, 100.5, 99.5), [], state_prices))
    assert ok is True


def test_price_change_window_group_g_is_wired(monkeypatch):
    _permissive_config(monkeypatch)
    # 只打开 G 组
    monkeypatch.setattr(config, "PRICE_CHANGE_COUNT_G", 5)
    monkeypatch.setattr(config, "PRICE_CHANGE_LIMIT_G", 0.01)
    calc = _make_calc()
    state_prices = pd.Series([101.2, 99.0, 100.3, 100.1, 100.0])
    ok, _ = calc._check_short_signal(*_short_args(_row(100.0, 100.5, 99.5), [], state_prices))
    assert ok is False


# ==================== ENABLE_MA5_MA10 已停用 ====================

def test_enable_ma5_ma10_no_longer_blocks(monkeypatch):
    _permissive_config(monkeypatch)
    monkeypatch.setattr(config, "ENABLE_MA5_MA10", True)
    calc = _make_calc()
    row = _row(100.0, 100.5, 99.5)
    row["vol_ma5"] = 10.0
    row["vol_ma10"] = 20.0  # vol_ma5 < vol_ma10，旧逻辑会拒绝
    ok, _ = calc._check_long_signal(*_long_args(row, []))
    assert ok is True


# ==================== 参数导出 ====================

def test_get_signal_params_exports_new_keys():
    params = SignalCalculator.get_signal_params()
    for key in (
        "m_price_change_f", "m_price_change_minutes_f",
        "m_price_change_g", "m_price_change_minutes_g",
        "price_change_count_f", "price_change_limit_f",
        "price_change_count_g", "price_change_limit_g",
        "safe_range_window_hours", "safe_range_swing_ratio", "safe_range_near_ratio",
        "safe_range_window_hours_b", "safe_range_swing_ratio_b", "safe_range_near_ratio_b",
        "safe_range_window_hours_c", "safe_range_swing_ratio_c", "safe_range_near_ratio_c",
    ):
        assert key in params, f"缺少导出参数: {key}"
