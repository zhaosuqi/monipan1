#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 timeout_close 触发时走真实下单流程、记录合法 action、并计算正确盈亏"""

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.logger import get_logger
from exchange_layer.models import Order, OrderSide, OrderStatus, OrderType
from trade_module.trade_engine import Position, TradeEngine


class FakeTimeoutExchange:
    connected = True

    def __init__(self):
        self.place_calls = []
        self.cancel_calls = []

    def get_open_orders(self, symbol):
        return []

    def get_position(self, symbol):
        return {'position_amount': '3', 'side': 'BOTH'}

    def cancel_order(self, symbol, order_id):
        self.cancel_calls.append((symbol, order_id))

    def place_order(self, **kwargs):
        self.place_calls.append(kwargs)
        return Order(
            order_id='timeout-close-1',
            client_order_id='timeout-close',
            symbol=kwargs['symbol'],
            side=OrderSide(kwargs['side']),
            type=OrderType(kwargs['order_type']),
            status=OrderStatus.FILLED,
            price=0.0,
            quantity=kwargs['quantity'],
            avg_price=98.0,
        )

    def get_order(self, symbol, order_id):
        return Order(
            order_id=order_id,
            client_order_id='timeout-close',
            symbol=symbol,
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            price=0.0,
            quantity=3.0,
            avg_price=98.0,
        )

    def get_account_info(self, asset):
        class AccountInfo:
            total_wallet_balance = 0.5
        return AccountInfo()


class FakeFeishu:
    def send_close_position_notification(self, **kwargs):
        pass

    def send_position_notification(self, **kwargs):
        pass


class FakeTradeRecorder:
    def record_position_close(self, **kwargs):
        pass

    def record_trade(self, trade):
        pass


def make_position():
    return Position(
        id='pos-timeout-1',
        side='long',
        entry_price=100.0,
        entry_time=pd.Timestamp('2026-08-31 19:00:00'),
        contracts=3,
        entry_contracts=3,
        contract_size_btc=1.0,
        trace_id='trace-timeout-1',
    )


def patch_close_time_minutes(monkeypatch, minutes):
    """设置 CLOSE_TIME_MINUTES 阈值"""
    from core import config as config_module
    monkeypatch.setattr(config_module.config, 'CLOSE_TIME_MINUTES', minutes)


def make_engine(exchange):
    engine = TradeEngine.__new__(TradeEngine)
    engine.logger = get_logger('tests.timeout_close')
    engine.exchange = exchange
    engine.positions = []
    engine.trades = []
    engine.logs = []
    engine.display_asset = 'BTC'
    engine.realized_pnl = 1.0
    engine.cached_total_balance = 1.0
    engine.locked_capital = 0.0
    engine.stoploss_time = None
    engine.stoploss_side = None
    engine.order_sync_interval = 120
    engine.order_sync_log_limit = 5
    engine.last_order_sync = None
    engine.feishu_bot = FakeFeishu()
    engine.trade_recorder = FakeTradeRecorder()
    return engine


def test_timeout_close_places_market_order(monkeypatch):
    """超时平仓应下真实市价单，而不仅是更新内部状态"""
    patch_close_time_minutes(monkeypatch, 240)
    engine = make_engine(FakeTimeoutExchange())
    pos = make_position()
    engine.positions.append(pos)

    ts = pd.Timestamp('2026-08-31 23:30:00')  # 270 分钟后
    closed = engine.check_timeout(pos, ts, price=98.0)

    assert closed is True
    assert len(engine.exchange.place_calls) == 1

    call = engine.exchange.place_calls[0]
    assert call['side'] == 'SELL'
    assert call['order_type'] == 'MARKET'
    assert call['quantity'] == 3.0
    assert call.get('reduceOnly') is True
    assert pos not in engine.positions


def test_timeout_close_uses_correct_pnl_formula(monkeypatch):
    """验证 long 仓位的 PnL 计算: notional * (1/entry - 1/close)"""
    patch_close_time_minutes(monkeypatch, 240)
    engine = make_engine(FakeTimeoutExchange())
    pos = make_position()
    engine.positions.append(pos)

    ts = pd.Timestamp('2026-08-31 23:30:00')
    engine.check_timeout(pos, ts, price=98.0)

    # 检查 EOD_CLOSE 日志中的 PnL 公式
    eod_logs = [log for log in engine.logs if log[1] == 'EOD_CLOSE']
    assert len(eod_logs) == 1, "应记录 EOD_CLOSE 日志"

    notional = 3 * 100  # CONTRACT_NOTIONAL=100
    expected_gross = notional * (1 / 100.0 - 1 / 98.0)
    actual_gross = eod_logs[0][5]
    assert abs(actual_gross - expected_gross) < 1e-9, (
        f"gross_pnl 公式错误: 实际 {actual_gross}, 期望 {expected_gross}"
    )


def test_timeout_close_maps_to_eod_close_action(monkeypatch):
    """验证 timeout_close 在数据库中映射为 EOD_CLOSE (合法 action)"""
    patch_close_time_minutes(monkeypatch, 240)
    engine = make_engine(FakeTimeoutExchange())
    pos = make_position()
    engine.positions.append(pos)

    captured_trades = []

    class CaptureRecorder(FakeTradeRecorder):
        def record_trade(self, trade):
            captured_trades.append(trade)

    engine.trade_recorder = CaptureRecorder()

    ts = pd.Timestamp('2026-08-31 23:30:00')
    engine.check_timeout(pos, ts, price=98.0)

    assert len(captured_trades) == 1, "应记录 1 条 trade"
    assert captured_trades[0].action == 'EOD_CLOSE', (
        f"action 应为 'EOD_CLOSE', 实际: {captured_trades[0].action}"
    )


def test_timeout_close_not_triggered_before_threshold():
    """持仓时间未达到阈值时不触发"""
    engine = make_engine(FakeTimeoutExchange())
    pos = make_position()
    engine.positions.append(pos)

    ts = pd.Timestamp('2026-08-31 20:00:00')  # 仅 60 分钟
    closed = engine.check_timeout(pos, ts, price=98.0)

    assert closed is False
    assert len(engine.exchange.place_calls) == 0
    assert pos in engine.positions


def test_drawdown_close_maps_to_close_retreat_action():
    """drawdown_close 应映射为 CLOSE_RETREAT"""
    engine = make_engine(FakeTimeoutExchange())
    pos = make_position()
    engine.positions.append(pos)

    captured_trades = []

    class CaptureRecorder(FakeTradeRecorder):
        def record_trade(self, trade):
            captured_trades.append(trade)

    engine.trade_recorder = CaptureRecorder()

    # 直接调用 close_position 测试映射
    engine.close_position(
        pos,
        pd.Timestamp('2026-08-31 23:30:00'),
        98.0,
        'drawdown_close',
        net_btc=0.001,
        pnl_already_applied=True,
        close_order_id='dd-1',
    )

    assert len(captured_trades) == 1
    assert captured_trades[0].action == 'CLOSE_RETREAT'


def test_take_profit_final_maps_to_tp_action():
    """take_profit_final 应映射为 TP"""
    engine = make_engine(FakeTimeoutExchange())
    pos = make_position()
    engine.positions.append(pos)

    captured_trades = []

    class CaptureRecorder(FakeTradeRecorder):
        def record_trade(self, trade):
            captured_trades.append(trade)

    engine.trade_recorder = CaptureRecorder()

    engine.close_position(
        pos,
        pd.Timestamp('2026-08-31 23:30:00'),
        102.0,
        'take_profit_final',
        net_btc=0.005,
        pnl_already_applied=True,
        close_order_id='tp-1',
    )

    assert len(captured_trades) == 1
    assert captured_trades[0].action == 'TP'


def test_stop_loss_maps_to_sl_action():
    """stop_loss 应映射为 SL"""
    engine = make_engine(FakeTimeoutExchange())
    pos = make_position()
    engine.positions.append(pos)

    captured_trades = []

    class CaptureRecorder(FakeTradeRecorder):
        def record_trade(self, trade):
            captured_trades.append(trade)

    engine.trade_recorder = CaptureRecorder()

    engine.close_position(
        pos,
        pd.Timestamp('2026-08-31 23:30:00'),
        98.0,
        'stop_loss',
        net_btc=-0.002,
        pnl_already_applied=True,
        close_order_id='sl-1',
    )

    assert len(captured_trades) == 1
    assert captured_trades[0].action == 'SL'


class FakeExchangeWithOpenOrder:
    """模拟有挂单(保护止损)的交易所, 追踪调用顺序"""
    connected = True

    def __init__(self):
        self.call_sequence = []

    def get_open_orders(self, symbol):
        self.call_sequence.append('get_open_orders')
        return [
            Order(
                order_id='sl-stop-1',
                client_order_id='sl-stop',
                symbol=symbol,
                side=OrderSide.SELL,
                type=OrderType.STOP_MARKET,
                status=OrderStatus.NEW,
                price=0.0,
                quantity=0.0,
                stop_price=95.0,
            )
        ]

    def get_position(self, symbol):
        self.call_sequence.append('get_position')
        return {'position_amount': '3', 'side': 'BOTH'}

    def cancel_order(self, symbol, order_id):
        self.call_sequence.append(f'cancel_order:{order_id}')

    def place_order(self, **kwargs):
        self.call_sequence.append('place_order')
        return Order(
            order_id='close-mkt-1',
            client_order_id='close-mkt',
            symbol=kwargs['symbol'],
            side=OrderSide(kwargs['side']),
            type=OrderType(kwargs['order_type']),
            status=OrderStatus.FILLED,
            price=0.0,
            quantity=kwargs['quantity'],
            avg_price=98.0,
        )

    def get_order(self, symbol, order_id):
        return Order(
            order_id=order_id,
            client_order_id='close-mkt',
            symbol=symbol,
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            price=0.0,
            quantity=3.0,
            avg_price=98.0,
        )

    def get_account_info(self, asset):
        class AccountInfo:
            total_wallet_balance = 0.5
        return AccountInfo()


def test_protective_stop_cancelled_after_close_not_before(monkeypatch):
    """保护止损单应在市价平仓成交后再取消, 而不是平仓前

    安全考虑: 若先取消保护止损再下单, 下单失败时仓位会裸露;
    改为成交后再取消, 即使下单失败保护止损仍可兜底。
    """
    patch_close_time_minutes(monkeypatch, 240)
    exchange = FakeExchangeWithOpenOrder()
    engine = make_engine(exchange)
    pos = make_position()
    engine.positions.append(pos)

    ts = pd.Timestamp('2026-08-31 23:30:00')
    closed = engine.check_timeout(pos, ts, price=98.0)

    assert closed is True

    # 验证调用顺序: place_order 必须在 cancel_order 之前
    place_idx = exchange.call_sequence.index('place_order')
    cancel_indices = [i for i, c in enumerate(exchange.call_sequence)
                      if c.startswith('cancel_order')]
    assert len(cancel_indices) > 0, "应有取消挂单调用"
    for ci in cancel_indices:
        assert place_idx < ci, (
            f"顺序错误: place_order(idx={place_idx}) 应在 cancel_order(idx={ci}) 之前."
            f" 实际调用序列: {exchange.call_sequence}"
        )


def test_close_failure_keeps_protective_stop(monkeypatch):
    """平仓失败时保护止损单应保留, 不应被取消"""

    class FailingCloseExchange(FakeExchangeWithOpenOrder):
        def place_order(self, **kwargs):
            self.call_sequence.append('place_order')
            return Order(
                order_id='close-mkt-fail',
                client_order_id='close-mkt-fail',
                symbol=kwargs['symbol'],
                side=OrderSide(kwargs['side']),
                type=OrderType(kwargs['order_type']),
                status=OrderStatus.REJECTED,  # 下单被拒
                price=0.0,
                quantity=kwargs['quantity'],
                avg_price=0.0,
            )

    patch_close_time_minutes(monkeypatch, 240)
    exchange = FailingCloseExchange()
    engine = make_engine(exchange)
    pos = make_position()
    engine.positions.append(pos)

    ts = pd.Timestamp('2026-08-31 23:30:00')
    closed = engine.check_timeout(pos, ts, price=98.0)

    # 平仓失败
    assert closed is False
    # 保护止损单不应被取消
    cancel_calls = [c for c in exchange.call_sequence if c.startswith('cancel_order')]
    assert len(cancel_calls) == 0, (
        f"平仓失败时不应取消保护止损单, 实际取消了: {cancel_calls}"
    )
    # 本地仓位应保留(未平仓成功)
    assert pos in engine.positions
