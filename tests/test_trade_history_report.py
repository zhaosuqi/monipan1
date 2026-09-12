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

    def get_user_trades(self, symbol, limit=500, start_time=None, end_time=None, raise_on_error=False):
        self.calls.append({
            'symbol': symbol,
            'limit': limit,
            'start_time': start_time,
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


def make_engine(exchange):
    engine = TradeEngine.__new__(TradeEngine)
    engine.exchange = exchange
    engine.logger = type('Logger', (), {
        'info': lambda *args, **kwargs: None,
        'warning': lambda *args, **kwargs: None,
    })()
    return engine


def assert_forward_segmented_calls(exchange):
    """新分页约定：每页都显式传 start_time/end_time（≤7天一段），从回看窗口起点推进到现在。"""
    assert exchange.calls, "应当至少有一次查询"
    for call in exchange.calls:
        assert call['limit'] == 100
        assert call['raise_on_error'] is True
        assert call['start_time'] is not None
        assert call['end_time'] is not None
        assert call['end_time'] - call['start_time'] <= timedelta(days=7, seconds=1)
    starts = [c['start_time'] for c in exchange.calls]
    assert starts == sorted(starts), "分段应当单调向现在推进"
    assert exchange.calls[0]['start_time'] <= datetime.now() - timedelta(days=29)
    assert exchange.calls[-1]['end_time'] >= datetime.now() - timedelta(minutes=1)


def test_fetch_trade_history_report_trades_pages_until_ten_complete_trades(monkeypatch):
    base = datetime.now() - timedelta(days=1)
    newest_six = []
    older_four = []

    for idx in range(4):
        older_four.extend(make_closed_long(idx, base - timedelta(hours=2, minutes=idx * 10)))
    for idx in range(4, 10):
        newest_six.extend(make_closed_long(idx, base - timedelta(minutes=idx * 10)))

    exchange = FakeExchange([newest_six, older_four])
    engine = make_engine(exchange)
    monkeypatch.setattr('trade_module.trade_engine.config.SYMBOL', 'BTCUSD_PERP')

    trades = engine._fetch_trade_history_report_trades(target_count=10)

    assert len(trades) == 10
    assert all(t['entry_price'] > 0 for t in trades)
    assert all(t['exit_price'] > 0 for t in trades)
    # 30天/7天 = 5段，前两段各返回一页，后三段为空
    assert len(exchange.calls) == 5
    assert_forward_segmented_calls(exchange)


def test_fetch_trade_history_report_trades_keeps_paging_until_entries_are_available(monkeypatch):
    base = datetime.now() - timedelta(days=1)
    close_page = []
    open_page = []

    for idx in range(10):
        close_page.append(make_close_long(idx, base - timedelta(minutes=idx * 10)))
        open_page.append(make_open_long(idx, base - timedelta(hours=3, minutes=idx * 10)))

    exchange = FakeExchange([close_page, open_page])
    engine = make_engine(exchange)
    monkeypatch.setattr('trade_module.trade_engine.config.SYMBOL', 'BTCUSD_PERP')

    trades = engine._fetch_trade_history_report_trades(target_count=10)

    assert len(trades) == 10
    assert all(t['entry_price'] > 0 for t in trades)
    assert_forward_segmented_calls(exchange)


def test_fetch_trade_history_report_trades_skips_empty_segments(monkeypatch):
    """靠前的段无成交时跳过空段，仍能拉到较晚段里的成交。"""
    base = datetime.now() - timedelta(days=10)
    old_page = []
    for idx in range(10):
        old_page.extend(make_closed_long(idx, base - timedelta(minutes=idx * 10)))

    exchange = FakeExchange([[], old_page])
    engine = make_engine(exchange)
    monkeypatch.setattr('trade_module.trade_engine.config.SYMBOL', 'BTCUSD_PERP')

    trades = engine._fetch_trade_history_report_trades(target_count=10)

    assert len(trades) == 10
    assert len(exchange.calls) == 5
    assert_forward_segmented_calls(exchange)


def test_fetch_trade_history_report_trades_stops_at_now_when_all_empty(monkeypatch):
    """一直查不到成交时，逐段推进到现在即停止，不会无限翻页。"""
    exchange = FakeExchange([])
    engine = make_engine(exchange)
    monkeypatch.setattr('trade_module.trade_engine.config.SYMBOL', 'BTCUSD_PERP')

    trades = engine._fetch_trade_history_report_trades(target_count=10)

    assert trades == []
    # 30天/7天 = 5段，每段一页空结果
    assert len(exchange.calls) == 5
    assert_forward_segmented_calls(exchange)


def test_fetch_trade_history_report_trades_returns_most_recent_trades(monkeypatch):
    """回归：成交总数超过单页上限时，报告必须返回最新的成交。

    币安 dapi 不传 startTime 时按升序返回窗口内最旧的 limit 条，
    旧逻辑据此向前翻页，导致最近几天的成交永远拉不到（2026-09-11 实盘复现）。
    """
    base = datetime.now()
    old_page = []
    for idx in range(50):
        # 100 条旧成交（约 28 天前，正好撑满单页上限）
        old_page.extend(make_closed_long(idx, base - timedelta(days=28, minutes=idx * 10)))
    recent_page = []
    for idx in range(50, 60):
        # 20 条最近成交（昨天）
        recent_page.extend(make_closed_long(idx, base - timedelta(days=1, minutes=(idx - 50) * 10)))

    exchange = FakeExchange([old_page, recent_page])
    engine = make_engine(exchange)
    monkeypatch.setattr('trade_module.trade_engine.config.SYMBOL', 'BTCUSD_PERP')

    trades = engine._fetch_trade_history_report_trades(target_count=10)

    assert len(trades) == 10
    # 必须是最近的 10 笔（exit 65150+），而不是最旧的
    assert all(t['exit_price'] >= 65150 for t in trades)
    # 第一段拉满 100 条后，第二页应在同一段内继续向后翻
    assert exchange.calls[1]['end_time'] == exchange.calls[0]['end_time']
    assert exchange.calls[1]['start_time'] > exchange.calls[0]['start_time']
    assert_forward_segmented_calls(exchange)
