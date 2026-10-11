#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业微信群机器人通知 - 交易历史报告微信推送

企业微信 webhook 机器人能力（与飞书自定义机器人不同）：
- markdown 消息：支持标题/粗体/<font color>，不支持表格和围栏代码块，≤4096 字节
- image 消息：base64 + md5 直接发送，无需预上传，图片 ≤2MB
- 响应判定：HTTP 200 不代表成功，需检查响应体 errcode == 0
"""
import base64
import hashlib
import os
from typing import Dict, List, Optional

import requests

from core.config import config
from core.logger import get_logger

from .feishu_bot import FeishuBot
from .weekly_chart import render_weekly_text_bars


class WeChatBot:
    """企业微信群机器人（交易报告推送）"""

    # 企业微信 markdown 消息体上限 4096 字节，留余量截断
    MARKDOWN_MAX_BYTES = 4000
    # 图片消息 base64 编码前不得超过 2MB
    IMAGE_MAX_BYTES = 2 * 1024 * 1024

    def __init__(self):
        self.logger = get_logger('interaction_module.wechat')
        self.webhook = config.WECHAT_WEBHOOK
        self.enabled = config.WECHAT_ENABLED
        self.display_asset = FeishuBot._resolve_display_asset(getattr(config, 'SYMBOL', ''))

    def _post(self, payload: Dict) -> bool:
        """POST 到企业微信 webhook。errcode==0 才算成功。"""
        if not self.enabled:
            self.logger.debug("企业微信未启用 (WECHAT_ENABLED=0)，跳过发送")
            return False
        if not self.webhook:
            self.logger.debug("企业微信 webhook 未配置 (WECHAT_WEBHOOK)，跳过发送")
            return False
        try:
            response = requests.post(self.webhook, json=payload, timeout=5)
            if response.status_code != 200:
                self.logger.warning(f"企业微信发送失败: HTTP {response.status_code} {response.text}")
                return False
            try:
                body = response.json()
            except ValueError:
                self.logger.warning(f"企业微信响应非 JSON: {response.text}")
                return False
            if body.get('errcode') != 0:
                self.logger.warning(f"企业微信发送被拒: {body}")
                return False
            return True
        except Exception as e:
            self.logger.warning(f"企业微信发送异常: {e}")
            return False

    def send_markdown(self, content: str) -> bool:
        """发送 markdown 消息（企业微信子集：标题/粗体/font color，无表格无代码块）"""
        encoded = content.encode('utf-8')
        if len(encoded) > self.MARKDOWN_MAX_BYTES:
            truncated = encoded[:self.MARKDOWN_MAX_BYTES].decode('utf-8', errors='ignore')
            content = truncated + '\n…(截断)'
        return self._post({"msgtype": "markdown", "markdown": {"content": content}})

    def send_image(self, path: str) -> bool:
        """发送图片消息（base64 + md5，≤2MB）"""
        if not path or not os.path.exists(path):
            return False
        try:
            size = os.path.getsize(path)
            if size > self.IMAGE_MAX_BYTES:
                self.logger.warning(f"图片超过 2MB 限制 ({size} 字节)，跳过: {path}")
                return False
            with open(path, 'rb') as f:
                raw = f.read()
            payload = {
                "msgtype": "image",
                "image": {
                    "base64": base64.b64encode(raw).decode('ascii'),
                    "md5": hashlib.md5(raw).hexdigest(),
                },
            }
            return self._post(payload)
        except Exception as e:
            self.logger.warning(f"企业微信图片发送异常: {e}")
            return False

    def send_trade_history_report(
        self,
        trades: list,
        weekly: Optional[List[Dict]] = None,
        total_balance_btc: float = 0.0,
        chart_path: Optional[str] = None,
    ) -> bool:
        """
        发送最近交易历史报告（markdown 文本 + 周收益柱状图图片）

        Args:
            trades: 与 FeishuBot.send_trade_history_report 相同的 dict 列表
            weekly: aggregate_weekly_pnl_btc 返回的周聚合（可选）
            total_balance_btc: 当前总余额(基础币种)
            chart_path: 周收益柱状图 PNG 路径（可选，存在则随报告发图片消息）
        """
        if not self.enabled or not self.webhook or not trades:
            return False

        # 统计汇总（与飞书口径一致）
        total_pnl = sum(t.get('net_pnl_btc', 0) or 0 for t in trades)
        total_fee = sum(t.get('fee_btc', 0) or 0 for t in trades)
        win_count = sum(1 for t in trades if (t.get('net_pnl_btc', 0) or 0) > 0)
        loss_count = len(trades) - win_count
        win_rate = win_count / len(trades) * 100

        pnl_color = "info" if total_pnl > 0 else ("warning" if total_pnl < 0 else "comment")
        pnl_text = "盈利" if total_pnl > 0 else ("亏损" if total_pnl < 0 else "平手")

        lines = [
            f"## 📊 最近{len(trades)}笔交易报告 - {pnl_text}",
            f"> 成功/失败 {win_count}/{loss_count} | 胜率 {win_rate:.1f}%",
            f"> 总盈亏 <font color=\"{pnl_color}\">{total_pnl:+.6f} {self.display_asset}</font>"
            f" | 总手续费 -{total_fee:.6f} {self.display_asset}",
            "",
            "**交易明细**",
        ]

        for i, t in enumerate(trades, 1):
            exit_time = t.get('exit_time', '')
            if hasattr(exit_time, 'strftime'):
                time_str = exit_time.strftime('%m-%d %H:%M')
            else:
                time_str = str(exit_time)[:16] if exit_time else '-'
            side_cn = "多" if t.get('side') == 'long' else "空"
            entry_price = t.get('entry_price', 0) or 0
            exit_price = t.get('exit_price', 0) or 0
            net_pnl = t.get('net_pnl_btc', 0) or 0
            fee = t.get('fee_btc', 0) or 0
            pnl_sign = "+" if net_pnl >= 0 else ""
            lines.append(
                f"**{i}.** {time_str} | {side_cn} | "
                f"{entry_price:.1f}→{exit_price:.1f} | "
                f"{pnl_sign}{net_pnl:.6f} {self.display_asset} | 费:{fee:.6f}"
            )

        if weekly:
            text_bars = render_weekly_text_bars(weekly, self.display_asset)
            if text_bars:
                lines.append("")
                lines.append("**周收益(北京时间)**")
                lines.append(text_bars)

        now_str = FeishuBot._get_now_str()
        lines.append("")
        lines.append(f"当前余额: {total_balance_btc:.6f} {self.display_asset} | 报告时间: {now_str}")

        result = self.send_markdown('\n'.join(lines))

        if chart_path:
            self.send_image(chart_path)

        return result

    def send_no_trade_notification(self, total_balance_btc: float = 0.0) -> bool:
        """无交易心跳通知（与飞书心跳同场景）"""
        if not self.enabled or not self.webhook:
            return False
        now_str = FeishuBot._get_now_str()
        content = (
            "## 📊 交易报告\n"
            "> 本周期内无成交记录\n"
            f"当前余额: {total_balance_btc:.6f} {self.display_asset} | 报告时间: {now_str}"
        )
        return self.send_markdown(content)
