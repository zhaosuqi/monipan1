#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""飞书机器人多 webhook 推送测试（mock requests.post，不发真实请求）"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from interaction_module.feishu_bot import FeishuBot, parse_webhooks


class FakeResponse:
    def __init__(self, status_code=200, text='ok'):
        self.status_code = status_code
        self.text = text


def make_bot(monkeypatch, webhook, enabled=True, posts=None, fail_urls=(), raise_urls=()):
    """构造 FeishuBot 并拦截 requests.post；fail_urls 返回 500，raise_urls 抛异常。"""
    if posts is None:
        posts = []

    def fake_post(url, json=None, timeout=None, **kwargs):
        posts.append({'url': url, 'json': json})
        if url in raise_urls:
            raise ConnectionError('boom')
        if url in fail_urls:
            return FakeResponse(500, 'server error')
        return FakeResponse(200)

    monkeypatch.setattr('interaction_module.feishu_bot.config.FEISHU_WEBHOOK', webhook)
    monkeypatch.setattr('interaction_module.feishu_bot.config.FEISHU_ENABLED', enabled)
    monkeypatch.setattr('interaction_module.feishu_bot.requests.post', fake_post)

    return FeishuBot(), posts


def test_parse_webhooks():
    assert parse_webhooks('http://a,http://b') == ['http://a', 'http://b']
    assert parse_webhooks(' http://a , http://b,') == ['http://a', 'http://b']
    assert parse_webhooks('http://a') == ['http://a']
    assert parse_webhooks('') == []
    assert parse_webhooks(None) == []
    assert parse_webhooks(',, ,') == []


def test_single_webhook_unchanged(monkeypatch):
    bot, posts = make_bot(monkeypatch, 'http://hook-a')
    assert bot.webhooks == ['http://hook-a']
    assert bot.send_message('hello') is True
    assert len(posts) == 1
    assert posts[0]['url'] == 'http://hook-a'
    assert posts[0]['json']['msg_type'] == 'text'
    assert posts[0]['json']['content']['text'] == 'hello'


def test_two_webhooks_both_receive_same_payload(monkeypatch):
    bot, posts = make_bot(monkeypatch, 'http://hook-a, http://hook-b')
    assert bot.webhooks == ['http://hook-a', 'http://hook-b']

    assert bot.send_message('推送两次') is True
    assert len(posts) == 2
    assert [p['url'] for p in posts] == ['http://hook-a', 'http://hook-b']
    assert posts[0]['json'] == posts[1]['json']


def test_one_webhook_failure_does_not_block_other(monkeypatch):
    bot, posts = make_bot(
        monkeypatch, 'http://hook-a,http://hook-b', fail_urls=('http://hook-a',)
    )
    # 第一个地址 500：第二个仍收到，整体返回 False
    assert bot.send_message('hello') is False
    assert [p['url'] for p in posts] == ['http://hook-a', 'http://hook-b']


def test_one_webhook_exception_does_not_block_other(monkeypatch):
    bot, posts = make_bot(
        monkeypatch, 'http://hook-a,http://hook-b', raise_urls=('http://hook-b',)
    )
    assert bot.send_message('hello') is False
    assert [p['url'] for p in posts] == ['http://hook-a', 'http://hook-b']


def test_disabled_sends_nothing(monkeypatch):
    bot, posts = make_bot(monkeypatch, 'http://hook-a,http://hook-b', enabled=False)
    assert bot.send_message('hello') is False
    assert posts == []


def test_empty_webhook_sends_nothing(monkeypatch):
    bot, posts = make_bot(monkeypatch, '')
    assert bot.webhooks == []
    assert bot.send_message('hello') is False
    assert posts == []


def test_rich_card_fans_out_to_all_webhooks(monkeypatch):
    bot, posts = make_bot(monkeypatch, 'http://hook-a,http://hook-b')
    card = {"header": {"title": {"content": "t", "tag": "plain_text"}}, "elements": []}
    assert bot._send_rich_card(card) is True
    assert [p['url'] for p in posts] == ['http://hook-a', 'http://hook-b']
    assert all(p['json']['msg_type'] == 'interactive' for p in posts)
    assert posts[0]['json'] == posts[1]['json']


def test_low_freq_mode_still_filters(monkeypatch):
    """低频推送模式下被过滤的类别，多地址也不应发送"""
    bot, posts = make_bot(monkeypatch, 'http://hook-a,http://hook-b')
    monkeypatch.setattr(bot, 'push_freq', FeishuBot.PUSH_FREQ_LOW)
    # 'message' 类别在低频模式下被过滤
    assert bot.send_message('普通消息') is False
    assert posts == []
    # 'alert' 类别低频模式放行，两个地址都收到
    assert bot.send_message('异常告警', category='alert') is True
    assert len(posts) == 2
