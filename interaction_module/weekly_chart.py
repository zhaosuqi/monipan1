#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
周收益聚合与柱状图渲染（纯函数模块，无 DB / 无网络）

- aggregate_weekly_pnl_btc: 按北京时间周（周一~周日）聚合净盈亏
- render_weekly_text_bars:   Unicode 文本柱状图（飞书卡片 / 微信 markdown 用）
- render_weekly_chart_png:   matplotlib PNG 柱状图（微信图片消息用，延迟导入，
                             无 matplotlib 或渲染异常时返回 None，报告降级为纯文字）
"""
import os
import tempfile
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


def render_weekly_chart_png(
    weekly: List[Dict[str, Any]],
    asset: str = 'BTC',
) -> Optional[str]:
    """
    渲染周收益柱状图 PNG，返回临时文件路径。

    全英文/数字标签（实盘 Linux 无中文字体，避免方块乱码）。
    matplotlib 延迟导入 + Agg 无头后端；缺包或任何异常返回 None。
    """
    if not weekly:
        return None

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        labels = [w['label'] for w in weekly]
        values = [w.get('net_pnl_btc', 0) or 0 for w in weekly]

        fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
        colors = []
        for v in values:
            colors.append('#2ba245' if v >= 0 else '#d64541')

        bars = ax.bar(labels, values, color=colors, width=0.6)

        # 当前周标记为进行中：半透明 + 斜纹
        for w, bar in zip(weekly, bars):
            if w.get('is_current'):
                bar.set_alpha(0.6)
                bar.set_hatch('//')

        ax.axhline(0, color='#888888', linewidth=0.8)
        ax.set_title(f'Weekly Net PnL ({asset})')
        ax.grid(axis='y', linestyle='--', alpha=0.3)
        ax.set_axisbelow(True)

        max_abs = max(abs(v) for v in values) if values else 0
        offset = max_abs * 0.03 if max_abs > 0 else 0.0001
        for bar, v in zip(bars, values):
            x = bar.get_x() + bar.get_width() / 2
            if v >= 0:
                ax.text(x, v + offset, f'{v:+.4f}',
                        ha='center', va='bottom', fontsize=8)
            else:
                ax.text(x, v - offset, f'{v:+.4f}',
                        ha='center', va='top', fontsize=8)

        fig.tight_layout()

        fd, path = tempfile.mkstemp(prefix='weekly_pnl_', suffix='.png')
        os.close(fd)
        fig.savefig(path)
        plt.close(fig)
        return path

    except Exception:
        return None
