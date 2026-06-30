#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trade_module.trade_engine import TradeEngine


class FakeExchange:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get_user_trades(self, symbol, limit=500, end_time=None, raise_on_error=False):
        self.calls.append({
            'symbol': symbol,
            'limit': limit,
            'end_time': end_time,
            'raise_on_error': raise_on_error,
        })
        if not self.pages:
            return []
        return self.pages.pop(0)


def make_trade(order_id, trade_id, ts, side, price, qty, realized_pnl):
    return {
        'id': trade_id,
        'orderId': order_id,
        'time': int(ts.timestamp() * 1000),
        'side': side,
        'price': str(price),
        'qty': str(qty),
        'commission': '0.0001',
        'realizedPnl': str(realized_pnl),
    }


def make_closed_long(index, close_time):
    open_time = close_time - timedelta(minutes=5)
    return [
        make_trade(1000 + index * 2, 2000 + index * 2, open_time, 'BUY', 65000 + index, 1, 0),
        make_trade(1001 + index * 2, 2001 + index * 2, close_time, 'SELL', 65100 + index, 1, '0.0002'),
    ]


def make_open_long(index, open_time):
    return make_trade(1000 + index * 2, 2000 + index * 2, open_time, 'BUY', 65000 + index, 1, 0)


def make_close_long(index, close_time):
    return make_trade(1001 + index * 2, 2001 + index * 2, close_time, 'SELL', 65100 + index, 1, '0.0002')


def test_fetch_trade_history_report_trades_pages_until_ten_complete_trades(monkeypatch):
    base = datetime(2026, 6, 30, 12, 0, 0)
    newest_six = []
    older_four = []

    for idx in range(4):
        older_four.extend(make_closed_long(idx, base - timedelta(hours=2, minutes=idx * 10)))
    for idx in range(4, 10):
        newest_six.extend(make_closed_long(idx, base - timedelta(minutes=idx * 10)))

    exchange = FakeExchange([newest_six, older_four])
    engine = TradeEngine.__new__(TradeEngine)
    engine.exchange = exchange
    engine.logger = type('Logger', (), {
        'info': lambda *args, **kwargs: None,
        'warning': lambda *args, **kwargs: None,
    })()

    monkeypatch.setattr('trade_module.trade_engine.config.SYMBOL', 'BTCUSD_PERP')

    trades = engine._fetch_trade_history_report_trades(target_count=10)

    assert len(trades) == 10
    assert all(t['entry_price'] > 0 for t in trades)
    assert all(t['exit_price'] > 0 for t in trades)
    assert len(exchange.calls) == 2
    assert exchange.calls[0]['limit'] == 100
    assert exchange.calls[0]['raise_on_error'] is True
    assert exchange.calls[1]['end_time'] < base


def test_fetch_trade_history_report_trades_keeps_paging_until_entries_are_available(monkeypatch):
    base = datetime(2026, 6, 30, 12, 0, 0)
    close_page = []
    open_page = []

    for idx in range(10):
        close_page.append(make_close_long(idx, base - timedelta(minutes=idx * 10)))
        open_page.append(make_open_long(idx, base - timedelta(hours=3, minutes=idx * 10)))

    exchange = FakeExchange([close_page, open_page])
    engine = TradeEngine.__new__(TradeEngine)
    engine.exchange = exchange
    engine.logger = type('Logger', (), {
        'info': lambda *args, **kwargs: None,
        'warning': lambda *args, **kwargs: None,
    })()

    monkeypatch.setattr('trade_module.trade_engine.config.SYMBOL', 'BTCUSD_PERP')

    trades = engine._fetch_trade_history_report_trades(target_count=10)

    assert len(trades) == 10
    assert all(t['entry_price'] > 0 for t in trades)
    assert len(exchange.calls) == 2
