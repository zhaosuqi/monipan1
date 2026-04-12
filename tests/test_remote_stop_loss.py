#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.logger import get_logger
from exchange_layer.binance_exchange import BinanceExchange
from exchange_layer.models import Order, OrderSide, OrderStatus, OrderType
from trade_module.trade_engine import Position, TradeEngine


class FakeLocalOrderManager:
    def create_order(self, order):
        return True

    def update_order_status(self, order_id, status, **kwargs):
        return True


class FakeBinanceClient:
    def __init__(self):
        self.base_url = 'https://testnet.binancefuture.com'
        self.last_params = None

    def new_order(self, **params):
        self.last_params = params
        return {
            'orderId': 4321,
            'clientOrderId': 'sl-close-all',
            'symbol': params['symbol'],
            'side': params['side'],
            'type': params['type'],
            'status': 'NEW',
            'price': '0',
            'origQty': '0',
            'executedQty': '0',
            'avgPrice': '0',
            'stopPrice': str(params.get('stopPrice', 0)),
            'time': int(datetime(2026, 4, 11, 8, 0, 0).timestamp() * 1000),
        }


class FakeRemoteStopExchange:
    connected = True

    def __init__(self):
        self.calls = []

    def place_order(self, **kwargs):
        self.calls.append(kwargs)
        return Order(
            order_id='sl-remote-1',
            client_order_id='stop-order',
            symbol=kwargs['symbol'],
            side=OrderSide(kwargs['side']),
            type=OrderType(kwargs['order_type']),
            status=OrderStatus.NEW,
            price=0.0,
            quantity=0.0,
            stop_price=kwargs['stop_price'],
        )


class FakeSyncExchange:
    connected = True

    def get_position(self, symbol):
        return None

    def get_order(self, symbol, order_id):
        return Order(
            order_id=order_id,
            client_order_id='sl-close-all',
            symbol=symbol,
            side=OrderSide.SELL,
            type=OrderType.STOP_MARKET,
            status=OrderStatus.FILLED,
            price=0.0,
            quantity=0.0,
            avg_price=95.5,
            stop_price=98.0,
        )


def make_position():
    return Position(
        id='pos-1',
        side='long',
        entry_price=100.0,
        entry_time=pd.Timestamp('2026-04-11 08:00:00'),
        contracts=3,
        entry_contracts=3,
        contract_size_btc=1.0,
        trace_id='trace-1',
    )


def make_engine(exchange):
    engine = TradeEngine.__new__(TradeEngine)
    engine.logger = get_logger('tests.remote_stop_loss')
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
    return engine


def test_place_initial_stop_loss_order_uses_mark_price_close_position():
    engine = make_engine(FakeRemoteStopExchange())
    pos = make_position()
    ts = pd.Timestamp('2026-04-11 08:01:00')

    placed = TradeEngine._place_initial_stop_loss_order(engine, pos, ts)

    assert placed is True
    assert len(engine.exchange.calls) == 1

    call = engine.exchange.calls[0]
    assert call['side'] == 'SELL'
    assert call['order_type'] == 'STOP_MARKET'
    assert call['stop_price'] == 98.0
    assert call['workingType'] == 'MARK_PRICE'
    assert call['closePosition'] is True
    assert pos.sl_order_id == 'sl-remote-1'
    assert pos.sl_order_attempts == 1
    assert pos.sl_order_last_time == ts


def test_binance_stop_market_close_position_uses_expected_params():
    exchange = BinanceExchange(api_key='key', api_secret='secret', testnet=True)
    exchange.client = FakeBinanceClient()
    exchange.local_order_manager = FakeLocalOrderManager()
    exchange.hedge_mode = True

    order = exchange.place_order(
        symbol='BTCUSD_PERP',
        side='SELL',
        order_type='STOP_MARKET',
        quantity=3.0,
        stop_price=98.0,
        business_order_type='SL',
        closePosition=True,
        workingType='MARK_PRICE',
    )

    params = exchange.client.last_params

    assert order.status == OrderStatus.NEW
    assert params['type'] == 'STOP_MARKET'
    assert params['closePosition'] is True
    assert params['workingType'] == 'MARK_PRICE'
    assert params['positionSide'] == 'LONG'
    assert params['stopPrice'] == 98.0
    assert 'quantity' not in params
    assert 'timeInForce' not in params
    assert 'reduceOnly' not in params


def test_sync_positions_reconciles_filled_remote_stop_loss():
    engine = make_engine(FakeSyncExchange())
    pos = make_position()
    pos.sl_order_id = 'sl-remote-1'
    engine.positions = [pos]

    captured = {}

    def fake_poll(order_id, fallback_price):
        captured['poll'] = (order_id, fallback_price)
        return 95.5

    def fake_close_position_after_sl(found_pos, ts, price, reason, order_id=None):
        captured['close'] = (found_pos, ts, price, reason, order_id)

    engine._poll_close_order_price = fake_poll
    engine._close_position_after_sl = fake_close_position_after_sl

    changed = TradeEngine.sync_positions_from_exchange(
        engine,
        pd.Timestamp('2026-04-11 08:02:00'),
        100.0,
    )

    assert changed is True
    assert captured['poll'] == ('sl-remote-1', 98.0)
    assert captured['close'][0] is pos
    assert captured['close'][2] == 95.5
    assert captured['close'][3] == 'stop_loss_remote'
    assert captured['close'][4] == 'sl-remote-1'
