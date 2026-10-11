#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""周收益聚合与柱状图渲染测试（纯函数，无 DB/网络）"""

import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from interaction_module.weekly_chart import (
    aggregate_weekly_pnl_btc,
    render_weekly_chart_png,
    render_weekly_text_bars,
)


def test_beijing_week_boundary():
    """北京时间周界：UTC 周日 15:59 属上周，16:00(=北京周一 00:00) 属新一周"""
    # now = UTC 2026-10-12 00:00（北京时间 2026-10-12 08:00，周一）
    now = datetime(2026, 10, 12, 0, 0)
    trades = [
        # UTC 周日 15:59:59 = 北京周日 23:59:59 -> 上周（周一 10-05）
        {'close_time': '2026-10-11T15:59:59', 'net_pnl_btc': 0.01},
        # UTC 周日 16:00:00 = 北京周一 00:00:00 -> 本周（周一 10-12）
        {'close_time': '2026-10-11T16:00:00', 'net_pnl_btc': 0.02},
    ]
    weekly = aggregate_weekly_pnl_btc(trades, weeks=2, now=now)

    assert [w['label'] for w in weekly] == ['10-05', '10-12']
    assert weekly[0]['net_pnl_btc'] == 0.01
    assert weekly[0]['trade_count'] == 1
    assert weekly[1]['net_pnl_btc'] == 0.02
    assert weekly[1]['trade_count'] == 1
    assert weekly[1]['is_current'] is True
    assert weekly[0]['is_current'] is False


def test_year_boundary_weeks():
    """跨年周：2026-01-01(周四) 所属周的周一是 2025-12-29"""
    now = datetime(2026, 1, 1, 0, 0)  # UTC
    trades = [
        # UTC 2025-12-28 16:00 = 北京 2025-12-29 00:00（周一）-> 当周
        {'close_time': '2025-12-28T16:00:00', 'net_pnl_btc': 0.03},
        # UTC 2025-12-28 15:59 = 北京 2025-12-28 23:59（周日）-> 上周
        {'close_time': '2025-12-28T15:59:00', 'net_pnl_btc': 0.01},
    ]
    weekly = aggregate_weekly_pnl_btc(trades, weeks=2, now=now)

    assert [w['label'] for w in weekly] == ['12-22', '12-29']
    assert weekly[0]['net_pnl_btc'] == 0.01
    assert weekly[1]['net_pnl_btc'] == 0.03
    assert weekly[1]['is_current'] is True


def test_exact_count_and_empty_weeks_filled():
    """恰好返回 weeks 条；空周补 0；窗口外的成交被忽略"""
    now = datetime(2026, 10, 12, 0, 0)
    trades = [
        {'close_time': '2026-09-14T10:00:00', 'net_pnl_btc': 0.05},  # 周一 09-14 周
        {'close_time': '2025-01-01T00:00:00', 'net_pnl_btc': 9.9},   # 远早于窗口 -> 忽略
    ]
    weekly = aggregate_weekly_pnl_btc(trades, weeks=4, now=now)

    assert len(weekly) == 4
    assert [w['label'] for w in weekly] == ['09-21', '09-28', '10-05', '10-12']
    assert all(w['net_pnl_btc'] == 0.0 for w in weekly)
    assert all(w['trade_count'] == 0 for w in weekly)
    assert [w['is_current'] for w in weekly] == [False, False, False, True]


def test_invalid_and_missing_values_skipped():
    now = datetime(2026, 10, 12, 0, 0)
    trades = [
        {'close_time': None, 'net_pnl_btc': 0.5},
        {'close_time': 'not-a-time', 'net_pnl_btc': 0.5},
        {'close_time': '2026-10-12T00:00:00', 'net_pnl_btc': None},
        {'close_time': '2026-10-12T00:00:00'},  # 缺 net_pnl_btc
    ]
    weekly = aggregate_weekly_pnl_btc(trades, weeks=1, now=now)
    assert len(weekly) == 1
    assert weekly[0]['net_pnl_btc'] == 0.0
    # close_time 合法但 pnl 非法的行不计入笔数；close_time 非法的行整体跳过
    assert weekly[0]['trade_count'] == 0


def test_accepts_datetime_and_pandas_timestamp():
    import pandas as pd
    now = datetime(2026, 10, 12, 0, 0)
    trades = [
        {'close_time': datetime(2026, 10, 12, 1, 0), 'net_pnl_btc': 0.01},
        {'close_time': pd.Timestamp('2026-10-12T02:00:00'), 'net_pnl_btc': 0.02},
    ]
    weekly = aggregate_weekly_pnl_btc(trades, weeks=1, now=now)
    assert weekly[0]['net_pnl_btc'] == 0.03
    assert weekly[0]['trade_count'] == 2


def test_render_text_bars():
    weekly = [
        {'label': '09-28', 'net_pnl_btc': -0.05, 'trade_count': 1, 'is_current': False},
        {'label': '10-05', 'net_pnl_btc': 0.0, 'trade_count': 0, 'is_current': False},
        {'label': '10-12', 'net_pnl_btc': 0.1, 'trade_count': 2, 'is_current': True},
    ]
    text = render_weekly_text_bars(weekly, width=10)
    lines = text.split('\n')

    assert len(lines) == 3
    # 盈利周按 max|pnl| 缩放到满宽
    assert '▇' * 10 in lines[2]
    assert '+0.100000' in lines[2]
    assert lines[2].endswith('(本周)')
    # 亏损周用浅色块，长度为一半
    assert '▒' * 5 in lines[0]
    assert '-0.050000' in lines[0]
    assert '(本周)' not in lines[0]
    # 零周空条
    assert '▇' not in lines[1] and '▒' not in lines[1]
    assert '+0.000000' in lines[1]


def test_render_text_bars_empty_and_all_zero():
    assert render_weekly_text_bars([]) == ''
    weekly = [
        {'label': '10-12', 'net_pnl_btc': 0.0, 'trade_count': 0, 'is_current': True},
    ]
    text = render_weekly_text_bars(weekly)
    assert '10-12' in text and '+0.000000' in text


def test_render_chart_png_smoke():
    weekly = [
        {'label': '10-05', 'net_pnl_btc': -0.02, 'trade_count': 1, 'is_current': False},
        {'label': '10-12', 'net_pnl_btc': 0.05, 'trade_count': 2, 'is_current': True},
    ]
    path = render_weekly_chart_png(weekly)
    try:
        assert path is not None
        assert os.path.exists(path)
        assert os.path.getsize(path) > 1024
    finally:
        if path and os.path.exists(path):
            os.unlink(path)


def test_render_chart_png_returns_none_without_matplotlib(monkeypatch):
    """无 matplotlib 时返回 None，不抛异常（报告降级为纯文字）"""
    monkeypatch.setitem(sys.modules, 'matplotlib', None)
    weekly = [
        {'label': '10-12', 'net_pnl_btc': 0.05, 'trade_count': 1, 'is_current': True},
    ]
    assert render_weekly_chart_png(weekly) is None


def test_render_chart_png_empty_input():
    assert render_weekly_chart_png([]) is None
