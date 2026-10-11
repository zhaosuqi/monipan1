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


# ==================== 本地库数据源（TRADE_REPORT_SOURCE=db）====================

import pytest

from core.config import config as _config
from core.database import Database
from core.trade_recorder import PositionRecord, TradeRecorder


@pytest.fixture
def tmp_recorder(tmp_path, monkeypatch):
    """指向临时库的 TradeRecorder（测试后恢复原单例）。"""
    monkeypatch.setattr(_config, 'DB_PATH', str(tmp_path / 't.db'))
    monkeypatch.setattr(Database, '_instance', None)
    monkeypatch.setattr(TradeRecorder, '_instance', None)
    monkeypatch.setattr(TradeRecorder, '_initialized', False)
    return TradeRecorder()


def seed_closed_position(recorder, idx, close_time, entry=65000.0, exit=65100.0,
                         net_pnl_usd=1.0, fee_usd=0.05, side='long'):
    """通过真实写入路径种一笔完整平仓记录。close_time: UTC ISO 字符串。"""
    pid = f'pos-{idx}'
    assert recorder.record_position_open(PositionRecord(
        position_id=pid,
        trace_id=f'trace-{idx}',
        symbol='BTCUSD_PERP',
        side=side,
        entry_price=entry,
        entry_contracts=10,
        open_time='2026-09-01T00:00:00',
        entry_order_id=f'open-{idx}',
    ))
    assert recorder.record_position_close(
        position_id=pid,
        exit_price=exit,
        exit_contracts=10,
        close_time=close_time,
        exit_reason='take_profit_final',
        total_fee=fee_usd,
        gross_pnl=net_pnl_usd + fee_usd,
        net_pnl=net_pnl_usd,
        exit_order_id=f'close-{idx}',
    )


def make_db_engine(recorder, monkeypatch, exchange=None):
    """构造走 db 数据源的引擎（绕过 __init__）。"""
    engine = TradeEngine.__new__(TradeEngine)
    engine.exchange = exchange
    engine.logger = type('Logger', (), {
        'info': lambda *args, **kwargs: None,
        'warning': lambda *args, **kwargs: None,
    })()
    engine.trade_recorder = recorder
    engine.display_asset = 'BTC'
    monkeypatch.setattr('trade_module.trade_engine.config.SYMBOL', 'BTCUSD_PERP')
    return engine


def test_db_report_returns_most_recent_by_close_time(tmp_recorder, monkeypatch):
    """种 12 笔，应取 close_time 最新的 10 笔且按时间升序输出"""
    base = datetime(2026, 10, 1, 0, 0)
    for i in range(12):
        seed_closed_position(
            tmp_recorder, i,
            close_time=(base + timedelta(hours=i)).isoformat(),
            exit=65100.0 + i,
        )
    engine = make_db_engine(tmp_recorder, monkeypatch)

    trades = engine._fetch_report_trades_from_db(10)

    assert len(trades) == 10
    # 最新 10 笔（idx 2..11，exit 65102..65111）
    assert all(t['exit_price'] >= 65102.0 for t in trades)
    # 时间升序
    times = [t['exit_time'] for t in trades]
    assert times == sorted(times)


def test_db_report_usd_to_btc_conversion(tmp_recorder, monkeypatch):
    """USD 口径按 exit_price 精确还原 BTC（net_usd = net_btc * close_price 的逆运算）"""
    seed_closed_position(
        tmp_recorder, 0,
        close_time='2026-10-01T00:00:00',
        exit=65100.0, net_pnl_usd=6.51, fee_usd=0.651,
    )
    engine = make_db_engine(tmp_recorder, monkeypatch)

    trades = engine._fetch_report_trades_from_db(10)

    assert len(trades) == 1
    assert abs(trades[0]['net_pnl_btc'] - 0.0001) < 1e-10
    assert abs(trades[0]['fee_btc'] - 0.00001) < 1e-10
    assert trades[0]['side'] == 'long'
    assert trades[0]['entry_price'] == 65000.0


def test_db_report_excludes_incomplete_rows(tmp_recorder, monkeypatch):
    """OPEN / SYNC_CLOSE 空值行 / exit_price=0 的行都不应进入报告"""
    # 正常完整行
    seed_closed_position(tmp_recorder, 0, close_time='2026-10-01T00:00:00')
    # OPEN 未平仓
    tmp_recorder.record_position_open(PositionRecord(
        position_id='pos-open', trace_id='t', symbol='BTCUSD_PERP', side='long',
        entry_price=65000.0, entry_contracts=10, open_time='2026-10-01T00:00:00',
        entry_order_id='o1',
    ))
    # SYNC_CLOSE 空值行 + exit_price=0 行（直接 SQL 模拟同步脚本写入）
    tmp_recorder.db.execute("""
        INSERT INTO position_records (
            position_id, trace_id, symbol, side, entry_price, entry_contracts,
            open_time, status, exit_reason
        ) VALUES ('pos-sync', 't', 'BTCUSD_PERP', 'short', 65000.0, 10,
                  '2026-10-01T00:00:00', 'CLOSED', 'SYNC_CLOSE')
    """)
    tmp_recorder.db.execute("""
        INSERT INTO position_records (
            position_id, trace_id, symbol, side, entry_price, entry_contracts,
            open_time, status, exit_price, net_pnl, close_time
        ) VALUES ('pos-zero', 't', 'BTCUSD_PERP', 'long', 65000.0, 10,
                  '2026-10-01T00:00:00', 'CLOSED', 0, 1.0, '2026-10-02T00:00:00')
    """)

    engine = make_db_engine(tmp_recorder, monkeypatch)
    trades = engine._fetch_report_trades_from_db(10)

    assert len(trades) == 1
    assert trades[0]['exit_price'] == 65100.0


def test_db_report_empty_table(tmp_recorder, monkeypatch):
    engine = make_db_engine(tmp_recorder, monkeypatch)
    assert engine._fetch_report_trades_from_db(10) == []


class CapturingBot:
    """捕获发送参数的 feishu/wechat bot 替身"""

    def __init__(self):
        self.report_kwargs = None
        self.no_trade_kwargs = None

    def send_trade_history_report(self, **kwargs):
        self.report_kwargs = kwargs
        return True

    def send_no_trade_notification(self, **kwargs):
        self.no_trade_kwargs = kwargs
        return True


class FakeAccountInfo:
    total_wallet_balance = 3.389181


def make_send_engine(recorder, monkeypatch, exchange=None):
    engine = make_db_engine(recorder, monkeypatch, exchange=exchange)
    engine.feishu_bot = CapturingBot()
    engine.wechat_bot = CapturingBot()
    monkeypatch.setattr('trade_module.trade_engine.config.TRADE_REPORT_SOURCE', 'db')
    monkeypatch.setattr('trade_module.trade_engine.config.TRADE_REPORT_WEEKLY_WEEKS', 8)
    monkeypatch.setattr('trade_module.trade_engine.config.TRADE_REPORT_CHART_ENABLED', False)
    monkeypatch.setattr('trade_module.trade_engine.config.FEISHU_ENABLED', False)
    monkeypatch.setattr('trade_module.trade_engine.config.FEISHU_WEBHOOK', '')
    return engine


def test_send_report_db_source_end_to_end(tmp_recorder, monkeypatch):
    """db 源端到端：飞书收到 weekly（8 周），微信收到同样数据，且不调用 API 路径"""
    now = datetime.utcnow()
    seed_closed_position(tmp_recorder, 0, close_time=now.isoformat(), exit=65100.0)

    class FakeExchangeWithBalance(FakeExchange):
        def get_account_info(self, asset):
            return FakeAccountInfo()

    exchange = FakeExchangeWithBalance([])
    engine = make_send_engine(tmp_recorder, monkeypatch, exchange=exchange)

    engine._send_trade_history_report()

    feishu_kwargs = engine.feishu_bot.report_kwargs
    assert feishu_kwargs is not None
    assert len(feishu_kwargs['trades']) == 1
    assert len(feishu_kwargs['weekly']) == 8
    assert feishu_kwargs['total_balance_btc'] == 3.389181
    # 本周（最后一周）应聚合到这笔成交
    assert feishu_kwargs['weekly'][-1]['trade_count'] == 1
    assert feishu_kwargs['weekly'][-1]['is_current'] is True

    wx_kwargs = engine.wechat_bot.report_kwargs
    assert wx_kwargs is not None
    assert len(wx_kwargs['trades']) == 1
    assert len(wx_kwargs['weekly']) == 8
    # 测试环境关闭图表 -> chart_path 为 None
    assert wx_kwargs['chart_path'] is None
    # db 源不应调用交易所 API
    assert exchange.calls == []


def test_send_report_db_exception_falls_back_to_api(tmp_recorder, monkeypatch):
    """db 读取异常时回退 API 路径"""
    base = datetime.now() - timedelta(days=1)
    page = []
    for idx in range(10):
        page.extend(make_closed_long(idx, base - timedelta(minutes=idx * 10)))
    exchange = FakeExchange([page])
    engine = make_send_engine(tmp_recorder, monkeypatch, exchange=exchange)

    def boom(*args, **kwargs):
        raise RuntimeError('db down')
    monkeypatch.setattr(engine.trade_recorder, 'get_recent_closed_positions', boom)

    engine._send_trade_history_report()

    feishu_kwargs = engine.feishu_bot.report_kwargs
    assert feishu_kwargs is not None
    assert len(feishu_kwargs['trades']) == 10  # 来自 API 回退路径
    assert len(exchange.calls) >= 1


def test_send_report_no_trade_heartbeat_both_bots(tmp_recorder, monkeypatch):
    """空库 → 无交易心跳，飞书与微信都被调用"""
    exchange = type('Ex', (), {'get_account_info': lambda self, asset: FakeAccountInfo()})()
    engine = make_send_engine(tmp_recorder, monkeypatch, exchange=exchange)

    engine._send_trade_history_report()

    assert engine.feishu_bot.report_kwargs is None
    assert engine.feishu_bot.no_trade_kwargs is not None
    assert engine.wechat_bot.no_trade_kwargs is not None
    assert engine.wechat_bot.no_trade_kwargs['total_balance_btc'] == 3.389181


def test_weekly_aggregation_uses_beijing_week(tmp_recorder, monkeypatch):
    """周聚合按北京时间：当前北京周周一 00:00 前后各一笔，分别落入本周/上周"""
    now = datetime.utcnow()
    now_bj = now + timedelta(hours=8)
    # 当前北京周的周一 00:00（北京）对应的 UTC 时刻
    monday_bj = (now_bj - timedelta(days=now_bj.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    monday_utc = monday_bj - timedelta(hours=8)

    # 本周第一分钟（北京周一 00:01 = UTC 周日 16:01）
    seed_closed_position(tmp_recorder, 0,
                         close_time=(monday_utc + timedelta(minutes=1)).isoformat(),
                         exit=65100.0, net_pnl_usd=6.51)
    # 上周最后一分钟（北京周日 23:59 = UTC 周日 15:59）
    seed_closed_position(tmp_recorder, 1,
                         close_time=(monday_utc - timedelta(minutes=1)).isoformat(),
                         exit=65100.0, net_pnl_usd=6.51)

    engine = make_db_engine(tmp_recorder, monkeypatch)
    weekly = engine._fetch_weekly_pnl_btc()

    assert len(weekly) == 8
    assert weekly[-1]['is_current'] is True
    assert weekly[-1]['trade_count'] == 1                    # 本周一笔
    assert abs(weekly[-1]['net_pnl_btc'] - 0.0001) < 1e-10
    assert weekly[-2]['trade_count'] == 1                    # 上周一笔
    assert abs(weekly[-2]['net_pnl_btc'] - 0.0001) < 1e-10
