#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""企业微信群机器人推送测试（mock requests.post，不发真实请求）"""

import base64
import hashlib
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from interaction_module.wechat_bot import WeChatBot


class FakeResponse:
    def __init__(self, body, status_code=200):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


def make_bot(monkeypatch, enabled=True, webhook='http://fake-webhook', posts=None):
    """构造 WeChatBot 并拦截 requests.post；posts 列表收集所有 payload。"""
    if posts is None:
        posts = []

    def fake_post(url, json=None, timeout=None, **kwargs):
        posts.append({'url': url, 'json': json})
        return FakeResponse({'errcode': 0, 'errmsg': 'ok'})

    monkeypatch.setattr('interaction_module.wechat_bot.config.WECHAT_ENABLED', enabled)
    monkeypatch.setattr('interaction_module.wechat_bot.config.WECHAT_WEBHOOK', webhook)
    monkeypatch.setattr('interaction_module.wechat_bot.requests.post', fake_post)

    return WeChatBot(), posts


def make_trades(n=2):
    return [
        {
            'exit_time': datetime(2026, 10, 8, 17, 29),
            'side': 'short',
            'entry_price': 81009.1,
            'exit_price': 80628.7,
            'net_pnl_btc': 0.046438,
            'fee_btc': 0.003955,
        }
    ] * n


def test_disabled_sends_nothing(monkeypatch):
    bot, posts = make_bot(monkeypatch, enabled=False)
    assert bot.send_markdown('hello') is False
    assert posts == []


def test_empty_webhook_sends_nothing(monkeypatch):
    bot, posts = make_bot(monkeypatch, webhook='')
    assert bot.send_markdown('hello') is False
    assert posts == []


def test_send_markdown_payload_shape(monkeypatch):
    bot, posts = make_bot(monkeypatch)
    assert bot.send_markdown('## 标题') is True
    assert len(posts) == 1
    payload = posts[0]['json']
    assert payload['msgtype'] == 'markdown'
    assert payload['markdown']['content'] == '## 标题'


def test_errcode_nonzero_returns_false(monkeypatch):
    posts = []

    def fake_post(url, json=None, timeout=None, **kwargs):
        posts.append(json)
        return FakeResponse({'errcode': 93000, 'errmsg': 'invalid webhook'})

    monkeypatch.setattr('interaction_module.wechat_bot.config.WECHAT_ENABLED', True)
    monkeypatch.setattr('interaction_module.wechat_bot.config.WECHAT_WEBHOOK', 'http://fake')
    monkeypatch.setattr('interaction_module.wechat_bot.requests.post', fake_post)

    bot = WeChatBot()
    assert bot.send_markdown('hello') is False


def test_http_error_returns_false(monkeypatch):
    monkeypatch.setattr('interaction_module.wechat_bot.config.WECHAT_ENABLED', True)
    monkeypatch.setattr('interaction_module.wechat_bot.config.WECHAT_WEBHOOK', 'http://fake')
    monkeypatch.setattr(
        'interaction_module.wechat_bot.requests.post',
        lambda *a, **k: FakeResponse({}, status_code=500),
    )
    bot = WeChatBot()
    assert bot.send_markdown('hello') is False


def test_send_image_base64_and_md5(monkeypatch, tmp_path):
    bot, posts = make_bot(monkeypatch)
    raw = b'\x89PNG\r\n\x1a\n' + b'fake-png-data' * 100
    img = tmp_path / 'chart.png'
    img.write_bytes(raw)

    assert bot.send_image(str(img)) is True
    assert len(posts) == 1
    payload = posts[0]['json']
    assert payload['msgtype'] == 'image'
    assert base64.b64decode(payload['image']['base64']) == raw
    assert payload['image']['md5'] == hashlib.md5(raw).hexdigest()


def test_send_image_over_2mb_rejected(monkeypatch, tmp_path):
    bot, posts = make_bot(monkeypatch)
    big = tmp_path / 'big.png'
    with open(big, 'wb') as f:
        f.truncate(WeChatBot.IMAGE_MAX_BYTES + 1)

    assert bot.send_image(str(big)) is False
    assert posts == []


def test_send_image_missing_file(monkeypatch):
    bot, posts = make_bot(monkeypatch)
    assert bot.send_image('/nonexistent/chart.png') is False
    assert bot.send_image(None) is False
    assert posts == []


def test_trade_history_report_content(monkeypatch, tmp_path):
    bot, posts = make_bot(monkeypatch)
    weekly = [
        {'label': '10-05', 'net_pnl_btc': 0.1, 'trade_count': 1, 'is_current': True},
    ]
    raw = b'\x89PNG\r\n\x1a\n' + b'x' * 2048
    chart = tmp_path / 'weekly.png'
    chart.write_bytes(raw)

    trades = make_trades(2)
    assert bot.send_trade_history_report(
        trades=trades, weekly=weekly, total_balance_btc=3.389181, chart_path=str(chart)
    ) is True

    # 一条 markdown + 一条 image
    assert len(posts) == 2
    md = posts[0]['json']['markdown']['content']
    assert '最近2笔交易报告' in md
    assert '交易明细' in md
    assert '81009.1→80628.7' in md
    assert '+0.046438' in md
    assert '周收益(北京时间)' in md
    assert '10-05' in md
    assert '当前余额: 3.389181' in md
    assert posts[1]['json']['msgtype'] == 'image'


def test_trade_history_report_without_chart_and_weekly(monkeypatch):
    bot, posts = make_bot(monkeypatch)
    assert bot.send_trade_history_report(trades=make_trades(1)) is True
    assert len(posts) == 1
    assert posts[0]['json']['msgtype'] == 'markdown'


def test_trade_history_report_empty_trades(monkeypatch):
    bot, posts = make_bot(monkeypatch)
    assert bot.send_trade_history_report(trades=[]) is False
    assert posts == []


def test_markdown_truncated_to_4096_bytes(monkeypatch):
    bot, posts = make_bot(monkeypatch)
    # 构造超长明细（中文每字 3 字节）
    trades = make_trades(200)
    bot.send_trade_history_report(trades=trades, total_balance_btc=1.0)

    content = posts[0]['json']['markdown']['content']
    assert len(content.encode('utf-8')) <= 4096
    assert content.endswith('…(截断)')


def test_no_trade_notification(monkeypatch):
    bot, posts = make_bot(monkeypatch)
    assert bot.send_no_trade_notification(total_balance_btc=3.389181) is True
    md = posts[0]['json']['markdown']['content']
    assert '无成交记录' in md
    assert '3.389181' in md


def test_no_trade_notification_disabled(monkeypatch):
    bot, posts = make_bot(monkeypatch, enabled=False)
    assert bot.send_no_trade_notification(total_balance_btc=1.0) is False
    assert posts == []
