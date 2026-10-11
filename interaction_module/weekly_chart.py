#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
周收益聚合与文本柱状图渲染（纯函数模块，无 DB / 无网络）

- aggregate_weekly_pnl_btc: 按北京时间周（周一~周日）聚合净盈亏
- render_weekly_text_bars:   Unicode 文本柱状图（飞书卡片用）
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# 北京时间相对 UTC 的偏移（position_records 的 close_time 为 UTC naive）
BEIJING_OFFSET = timedelta(hours=8)


def _parse_utc_naive(value: Any) -> Optional[datetime]:
    """解析 UTC naive 时间（str ISO-8601 / datetime / pandas.Timestamp），失败返回 None。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value).strip())
    except (ValueError, TypeError):
        return None


def _week_monday(dt: datetime) -> datetime:
    """取 dt 所在周（周一为界）的周一 00:00。"""
    monday = dt - timedelta(days=dt.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def aggregate_weekly_pnl_btc(
    trades: List[Dict[str, Any]],
    weeks: int = 8,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    按北京时间周聚合净盈亏。

    Args:
        trades: [{'close_time': UTC str|datetime, 'net_pnl_btc': float}, ...]
        weeks: 统计周数（含当前周）
        now: 当前时刻（UTC naive，默认 datetime.utcnow()，测试可注入）

    Returns:
        旧 -> 新恰好 weeks 条:
        [{week_start: date, label: 'MM-DD', net_pnl_btc: float,
          trade_count: int, is_current: bool}]，空周补 0
    """
    weeks = max(1, int(weeks))
    now_utc = now or datetime.utcnow()
    now_bj = now_utc + BEIJING_OFFSET
    current_monday = _week_monday(now_bj)
    oldest_monday = current_monday - timedelta(days=7 * (weeks - 1))

    buckets: Dict[datetime, Dict[str, Any]] = {}
    for i in range(weeks):
        monday = oldest_monday + timedelta(days=7 * i)
        buckets[monday.date()] = {
            'week_start': monday.date(),
            'label': monday.strftime('%m-%d'),
            'net_pnl_btc': 0.0,
            'trade_count': 0,
            'is_current': i == weeks - 1,
        }

    for t in trades:
        dt_utc = _parse_utc_naive(t.get('close_time'))
        if dt_utc is None:
            continue
        monday = _week_monday(dt_utc + BEIJING_OFFSET).date()
        bucket = buckets.get(monday)
        if bucket is None:
            continue  # 窗口之外
        raw_pnl = t.get('net_pnl_btc')
        if raw_pnl is None:
            continue  # 盈亏缺失的行不计入（报告中宁可少一笔也不按 0 误计）
        try:
            pnl = float(raw_pnl)
        except (TypeError, ValueError):
            continue
        bucket['net_pnl_btc'] += pnl
        bucket['trade_count'] += 1

    return [buckets[oldest_monday.date() + timedelta(days=7 * i)] for i in range(weeks)]


def render_weekly_text_bars(
    weekly: List[Dict[str, Any]],
    asset: str = 'BTC',
    width: int = 12,
) -> str:
    """
    Unicode 文本柱状图，每行: '10-06 ▇▇▇▇     +0.123400 (本周)'

    按 max|pnl| 缩放；盈利 '▇'，亏损 '▒'，零周空条；当前周后缀 '(本周)'。
    """
    if not weekly:
        return ''

    max_abs = max(abs(w.get('net_pnl_btc', 0) or 0) for w in weekly)
    lines = []
    for w in weekly:
        pnl = w.get('net_pnl_btc', 0) or 0
        bar_len = round(abs(pnl) / max_abs * width) if max_abs > 0 else 0
        if bar_len == 0:
            bar = ''
        elif pnl >= 0:
            bar = '▇' * bar_len
        else:
            bar = '▒' * bar_len
        suffix = ' (本周)' if w.get('is_current') else ''
        lines.append(f"{w['label']} {bar:<{width}} {pnl:+.6f}{suffix}")

    return '\n'.join(lines)
