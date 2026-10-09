#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证止盈止损基准价逻辑:

- 程序主动开仓: 基准 = 信号收盘价(benchmark_price), 而非实际成交价 entry_price
- 同步重建持仓: 基准 = 币安持仓均价 remote_entry
- TP_SL_BASE_ON_ORDER_PRICE=false 或 benchmark 为空时回退 entry_price(旧行为)
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import config as config_module
from core.logger import get_logger
from trade_module.trade_engine import Position, TradeEngine


class FakeFeishu:
    def send_tp_hit_notification(self, **kwargs):
        pass

    def send_tp_pullback_notification(self, **kwargs):
        pass


class FakeSyncExchange:
    """返回固定持仓信息的假交易所"""

    def __init__(self, position_amount, entry_price):
        self._info = {
            'position_amount': str(position_amount),
            'entry_price': str(entry_price),
        }

    def get_position(self, symbol):
        return self._info


def make_engine(exchange=None):
    engine = TradeEngine.__new__(TradeEngine)
    engine.logger = get_logger('tests.tp_sl_base_price')
    engine.exchange = exchange
    engine.positions = []
    engine.trades = []
    engine.logs = []
    engine.display_asset = 'BTC'
    engine.realized_pnl = 1.0
    engine.feishu_bot = FakeFeishu()
    return engine


def make_position(side='long', entry_price=99.0, benchmark_price=100.0):
    return Position(
        id='pos-base-1',
        side=side,
        entry_price=entry_price,
        entry_time=pd.Timestamp('2026-10-09 08:00:00'),
        contracts=3,
        entry_contracts=3,
        contract_size_btc=1.0,
        trace_id='trace-base-1',
        benchmark_price=benchmark_price,
    )


@pytest.fixture(autouse=True)
def fixed_config(monkeypatch):
    """固定止盈止损参数, 避免受本地 env 影响"""
    monkeypatch.setattr(config_module.config, 'STOP_LOSS_POINTS', 0.02)
    monkeypatch.setattr(config_module.config, 'TP_LEVELS', [1.006, 1.012])
    monkeypatch.setattr(config_module.config, 'DRAWDOWN_POINTS', 0.0002)
    monkeypatch.setattr(config_module.config, 'TP_SL_BASE_ON_ORDER_PRICE', True)


# ------------------ 止损基准 ------------------

def test_stop_loss_long_uses_benchmark():
    """多头止损价基于信号收盘价(benchmark)而非实际成交价(entry)"""
    engine = make_engine()
    pos = make_position(side='long', entry_price=99.0, benchmark_price=100.0)
    # benchmark: 100 - round(100*0.02,1)=100-2.0=98.0
    # 若用 entry: 99 - round(99*0.02,1)=99-2.0=97.0
    assert engine._calculate_stop_price(pos) == pytest.approx(98.0)


def test_stop_loss_short_uses_benchmark():
    """空头止损价基于信号收盘价(benchmark)"""
    engine = make_engine()
    pos = make_position(side='short', entry_price=101.0, benchmark_price=100.0)
    # benchmark: 100 + 2.0 = 102.0
    assert engine._calculate_stop_price(pos) == pytest.approx(102.0)


def test_stop_loss_switch_off_falls_back_to_entry(monkeypatch):
    """开关关闭时回退实际成交价(旧行为)"""
    monkeypatch.setattr(config_module.config, 'TP_SL_BASE_ON_ORDER_PRICE', False)
    engine = make_engine()
    pos = make_position(side='long', entry_price=99.0, benchmark_price=100.0)
    assert engine._calculate_stop_price(pos) == pytest.approx(97.0)


@pytest.mark.parametrize('bad_benchmark', [None, 0, -1.0])
def test_stop_loss_invalid_benchmark_falls_back_to_entry(bad_benchmark):
    """benchmark 缺失/非法时回退实际成交价"""
    engine = make_engine()
    pos = make_position(side='long', entry_price=99.0, benchmark_price=bad_benchmark)
    assert engine._calculate_stop_price(pos) == pytest.approx(97.0)


# ------------------ 止盈基准 ------------------

def test_take_profit_trigger_uses_benchmark():
    """止盈触发价基于信号收盘价: 介于两个基准之间的最高价不应触发"""
    engine = make_engine()
    pos = make_position(side='long', entry_price=99.0, benchmark_price=100.0)
    engine.positions.append(pos)
    ts = pd.Timestamp('2026-10-09 08:01:00')
    # entry基准L1目标: 99+round(99*0.006,1)=99.6; benchmark基准L1目标: 100+0.6=100.6
    row = {'high': 100.2, 'low': 99.5, 'close': 100.0}
    triggered = engine.apply_take_profit(pos, ts, 100.0, row)
    assert triggered is False
    assert pos.tp_hit == []  # 用 entry 基准(99.6)会触发, 用 benchmark(100.6)不触发


def test_take_profit_hit_records_benchmark_target():
    """止盈触发后记录的目标价基于信号收盘价"""
    engine = make_engine()
    pos = make_position(side='long', entry_price=99.0, benchmark_price=100.0)
    engine.positions.append(pos)
    ts = pd.Timestamp('2026-10-09 08:01:00')
    row = {'high': 100.7, 'low': 99.5, 'close': 100.5}
    engine.apply_take_profit(pos, ts, 100.5, row)
    assert pos.tp_hit == [1.006]
    assert pos.tp_confirmed_price == pytest.approx(100.6)  # 100 + round(100*0.006,1)


def test_take_profit_switch_off_uses_entry():
    """开关关闭时止盈按实际成交价基准触发"""
    config_module.config.TP_SL_BASE_ON_ORDER_PRICE = False
    try:
        engine = make_engine()
        pos = make_position(side='long', entry_price=99.0, benchmark_price=100.0)
        engine.positions.append(pos)
        ts = pd.Timestamp('2026-10-09 08:01:00')
        row = {'high': 100.2, 'low': 99.5, 'close': 100.0}
        engine.apply_take_profit(pos, ts, 100.0, row)
        assert pos.tp_hit == [1.006]
        assert pos.tp_confirmed_price == pytest.approx(99.6)  # 99 + round(99*0.006,1)
    finally:
        config_module.config.TP_SL_BASE_ON_ORDER_PRICE = True


# ------------------ 同步重建基准 ------------------

def test_sync_rebuild_inherits_benchmark_when_matched():
    """方向/数量匹配的旧持仓重建时继承 benchmark_price"""
    old_pos = make_position(side='long', entry_price=98.0, benchmark_price=100.0)
    exchange = FakeSyncExchange(position_amount=3, entry_price=99.6)
    engine = make_engine(exchange)
    engine.positions.append(old_pos)

    changed = engine.sync_positions_from_exchange(
        pd.Timestamp('2026-10-09 08:05:00'), price=99.6
    )
    assert changed is True
    assert len(engine.positions) == 1
    new_pos = engine.positions[0]
    assert new_pos.entry_price == pytest.approx(99.6)   # 记账价 = 币安持仓均价
    assert new_pos.benchmark_price == pytest.approx(100.0)  # 基准价继承旧持仓


def test_sync_rebuild_without_match_uses_remote_entry():
    """重启场景(无旧持仓): 基准 = 币安接口返回的持仓均价, 不依赖本地数据库"""
    exchange = FakeSyncExchange(position_amount=-3, entry_price=99.6)
    engine = make_engine(exchange)

    changed = engine.sync_positions_from_exchange(
        pd.Timestamp('2026-10-09 08:05:00'), price=99.6
    )
    assert changed is True
    assert len(engine.positions) == 1
    new_pos = engine.positions[0]
    assert new_pos.side == 'short'
    assert new_pos.entry_price == pytest.approx(99.6)
    assert new_pos.benchmark_price == pytest.approx(99.6)  # 市价开仓基准
    assert engine._calculate_stop_price(new_pos) == pytest.approx(
        99.6 + round(99.6 * 0.02, 1)
    )
