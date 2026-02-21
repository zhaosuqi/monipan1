#!/usr/bin/env python3
"""飞书通知机器人 - 支持开仓、平仓、止盈等交易事件通知"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import requests

from core.config import config
from core.logger import get_logger


class FeishuBot:
    # 东八区时区
    TZ_EAST8 = timezone(timedelta(hours=8))

    @staticmethod
    def _resolve_display_asset(symbol: str) -> str:
        """从交易对中提取用于显示的基础币种，例如 XXXUSD_PERP -> XXX。"""
        symbol_upper = (symbol or '').upper()
        if not symbol_upper:
            return 'ASSET'

        symbol_main = symbol_upper.split('_', 1)[0]
        for quote_suffix in ('USDT', 'USDC', 'BUSD', 'FDUSD', 'TUSD', 'USD'):
            if symbol_main.endswith(quote_suffix) and len(symbol_main) > len(quote_suffix):
                return symbol_main[:-len(quote_suffix)]

        return symbol_main

    def __init__(self):
        self.logger = get_logger('interaction_module.feishu')
        self.webhook = config.FEISHU_WEBHOOK
        self.enabled = config.FEISHU_ENABLED
        self.display_asset = self._resolve_display_asset(getattr(config, 'SYMBOL', ''))

    @staticmethod
    def _get_now_str() -> str:
        """获取当前东八区时间字符串"""
        return datetime.now(FeishuBot.TZ_EAST8).strftime("%Y-%m-%d %H:%M:%S")

    def send_message(self, message: str) -> bool:
        """发送普通文本消息"""
        if not self.enabled:
            self.logger.debug("飞书未启用 (FEISHU_ENABLED=0)，跳过发送")
            return False
        if not self.webhook:
            self.logger.warning("飞书Webhook未配置 (FEISHU_WEBHOOK为空)，跳过发送")
            return False

        try:
            data = {
                "msg_type": "text",
                "content": {"text": message}
            }

            response = requests.post(self.webhook, json=data, timeout=5)

            if response.status_code == 200:
                self.logger.debug(f"飞书消息发送成功: {message[:50]}")
                return True
            else:
                self.logger.error(f"飞书消息发送失败: {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"飞书消息发送异常: {e}")
            return False


    def _send_rich_card(self, card: Dict) -> bool:
        """发送富文本卡片消息"""
        if not self.enabled:
            self.logger.debug("飞书未启用 (FEISHU_ENABLED=0)，跳过发送")
            return False
        if not self.webhook:
            self.logger.warning("飞书Webhook未配置 (FEISHU_WEBHOOK为空)，跳过发送")
            return False

        try:
            data = {
                "msg_type": "interactive",
                "card": card
            }

            response = requests.post(self.webhook, json=data, timeout=5)

            if response.status_code == 200:
                self.logger.debug("飞书卡片消息发送成功")
                return True
            else:
                self.logger.error(f"飞书卡片发送失败: {response.status_code}, {response.text}")
                return False

        except Exception as e:
            self.logger.error(f"飞书卡片发送异常: {e}")
            return False

    def send_open_signal_detected_notification(
        self,
        symbol: str,
        side: str,
        close_price: float,
        high_price: float,
        low_price: float,
        available_capital: float,
        capital_asset: str,
        signal_name: str,
        ts: Optional[datetime] = None
    ) -> bool:
        """
        发送检测到开仓信号通知（尚未下单）
        """
        side_cn = "做多 📈" if side == 'long' else "做空 📉"
        side_color = "blue" if side == 'long' else "red"
        time_str = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        card = {
            "header": {
                "title": {
                    "content": f"检测到开仓信号 🎯 {side_cn}",
                    "tag": "plain_text"
                },
                "template": side_color
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**交易对**\n{symbol}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**信号方向**\n{side_cn}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**时间**\n{time_str}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**收盘价**\n${close_price:.2f}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**最高价**\n${high_price:.2f}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**最低价**\n${low_price:.2f}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**可用资金**\n{available_capital:.6f} {capital_asset}"
                            }
                        },
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**信号来源**\n{signal_name}"
                            }
                        },
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**发送时间**\n{self._get_now_str()}"
                            }
                        }
                    ]
                }
            ]
        }

        return self._send_rich_card(card)

    def send_open_order_placed_notification(
        self,
        symbol: str,
        side: str,
        price: float,
        contracts: int,
        signal_name: str,
        order_id: str,
        ts: Optional[datetime] = None
    ) -> bool:
        """
        发送开仓挂单通知（富文本卡片）
        """
        side_cn = "做多 📈" if side == 'long' else "做空 📉"
        side_color = "blue"
        time_str = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        card = {
            "header": {
                "title": {
                    "content": f"开仓挂单 📝 {side_cn}",
                    "tag": "plain_text"
                },
                "template": side_color
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**交易对**\n{symbol}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**方向**\n{side_cn}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**挂单价格**\n${price:.2f}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**挂单数量**\n{contracts}张"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**订单ID**\n{order_id}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**信号来源**\n{signal_name}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**挂单时间**\n{time_str}"
                            }
                        },
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**发送时间**\n{self._get_now_str()}"
                            }
                        }
                    ]
                }
            ]
        }

        return self._send_rich_card(card)

    def send_open_order_filled_notification(
        self,
        symbol: str,
        side: str,
        price: float,
        contracts: int,
        signal_name: str,
        ts: Optional[datetime] = None,
        tp1_price: Optional[float] = None,
        sl_price: Optional[float] = None
    ) -> bool:
        """
        发送开仓成交通知（富文本卡片）
        """
        side_cn = "做多 📈" if side == 'long' else "做空 📉"
        side_color = "green" if side == 'long' else "red"
        time_str = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        card = {
            "header": {
                "title": {
                    "content": f"开仓成交 ✅ {side_cn}",
                    "tag": "plain_text"
                },
                "template": side_color
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**交易对**\n{symbol}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**方向**\n{side_cn}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**成交价格**\n${price:.2f}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**成交数量**\n{contracts}张"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**信号来源**\n{signal_name}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**成交时间**\n{time_str}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**一级止盈**\n${tp1_price:.2f}" if tp1_price else "**一级止盈**\n-"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**止损价格**\n${sl_price:.2f}" if sl_price else "**止损价格**\n-"
                            }
                        },
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**发送时间**\n{self._get_now_str()}"
                            }
                        }
                    ]
                }
            ]
        }

        return self._send_rich_card(card)

    def send_open_order_canceled_notification(
        self,
        symbol: str,
        side: str,
        price: float,
        contracts: int,
        signal_name: str,
        order_id: str,
        reason: str,
        ts: Optional[datetime] = None
    ) -> bool:
        """
        发送开仓挂单撤回通知（未成交）
        """
        side_cn = "做多 📈" if side == 'long' else "做空 📉"
        time_str = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        card = {
            "header": {
                "title": {
                    "content": f"挂单撤回 ↩️ {side_cn}",
                    "tag": "plain_text"
                },
                "template": "orange"
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**交易对**\n{symbol}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**方向**\n{side_cn}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**挂单价格**\n${price:.2f}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**挂单数量**\n{contracts}张"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**订单ID**\n{order_id}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**原因**\n{reason}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**信号来源**\n{signal_name}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**撤单时间**\n{time_str}"
                            }
                        },
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**发送时间**\n{self._get_now_str()}"
                            }
                        }
                    ]
                }
            ]
        }

        return self._send_rich_card(card)

    def send_close_position_notification(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        close_price: float,
        contracts: int,
        entry_time: datetime,
        close_time: datetime,
        gross_btc: float,
        fee_btc: float,
        net_btc: float,
        reason: str,
        tp_hit: list = None,
        total_balance_btc: float = 0.0
    ) -> bool:
        """
        发送平仓通知（富文本卡片，含详细盈亏）

        Args:
            symbol: 交易对
            side: 方向 (long/short)
            entry_price: 开仓价格
            close_price: 平仓价格
            contracts: 合约数量
            entry_time: 开仓时间
            close_time: 平仓时间
            gross_btc: 毛盈亏(基础币种)
            fee_btc: 手续费(基础币种)
            net_btc: 净盈亏(基础币种)
            reason: 平仓原因
            tp_hit: 已触发的止盈级别
            total_balance_btc: 当前总余额(基础币种)
        """
        # 调试日志：检查传入的价格
        self.logger.info(f"[飞书平仓通知] entry_price={entry_price:.2f}, close_price={close_price:.2f}")

        # 中文方向显示
        side_cn = "做多" if side == 'long' else "做空"

        # 盈亏颜色和图标
        if net_btc > 0:
            pnl_color = "green"
            pnl_icon = "盈利 ✅"
        elif net_btc < 0:
            pnl_color = "red"
            pnl_icon = "亏损 ❌"
        else:
            pnl_color = "grey"
            pnl_icon = "平手 ➖"

        # 计算持仓时长
        duration = close_time - entry_time
        hours, remainder = divmod(duration.total_seconds(), 3600)
        minutes, _ = divmod(remainder, 60)
        duration_str = f"{int(hours)}h{int(minutes)}m"

        time_str = close_time.strftime("%Y-%m-%d %H:%M:%S")

        # 止盈级别显示
        tp_str = ", ".join([f"L{x}" for x in (tp_hit or [])]) if tp_hit else "无"

        # 原因标签
        reason_badge = self._get_reason_badge(reason)

        card = {
            "header": {
                "title": {
                    "content": f"平仓通知 - {pnl_icon}",
                    "tag": "plain_text"
                },
                "template": pnl_color
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**交易对**\n{symbol}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**方向**\n{side_cn}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**开仓价**\n${entry_price:.2f}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**平仓价**\n${close_price:.2f}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**合约数量**\n{contracts}张"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**持仓时长**\n{duration_str}"
                            }
                        }
                    ]
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**毛盈亏**\n{gross_btc:+.8f} {self.display_asset}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**手续费**\n-{fee_btc:.8f} {self.display_asset}"
                            }
                        },
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**净盈亏**\n**{net_btc:+.8f} {self.display_asset}**"
                            }
                        },
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**当前总余额**\n**{total_balance_btc:.6f} {self.display_asset}** 💰"
                            }
                        }
                    ]
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**平仓原因**\n{reason_badge}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**止盈级别**\n{tp_str}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**平仓时间**\n{time_str}"
                            }
                        },
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**发送时间**\n{self._get_now_str()}"
                            }
                        }
                    ]
                }
            ]
        }

        return self._send_rich_card(card)

    def send_tp_hit_notification(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        current_price: float,
        tp_level: int,
        tp_price: float,
        contracts: int,
        unrealized_pnl: float
    ) -> bool:
        """
        发送止盈级别触发通知

        Args:
            symbol: 交易对
            side: 方向
            entry_price: 开仓价格
            current_price: 当前价格
            tp_level: 止盈级别 (1, 2, 3...)
            tp_price: 止盈价格
            contracts: 合约数量
            unrealized_pnl: 未实现盈亏(USD)
        """
        side_cn = "做多 📈" if side == 'long' else "做空 📉"

        card = {
            "header": {
                "title": {
                    "content": f"止盈触发 🎯 - L{tp_level}",
                    "tag": "plain_text"
                },
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**交易对**\n{symbol}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**方向**\n{side_cn}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**开仓价**\n${entry_price:.2f}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**当前价**\n${current_price:.2f}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**止盈级别**\nL{tp_level} (${tp_price:.2f})"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**未实现盈亏**\n${unrealized_pnl:+.2f}"
                            }
                        },
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**发送时间**\n{self._get_now_str()}"
                            }
                        }
                    ]
                }
            ]
        }

        return self._send_rich_card(card)

    def send_tp_pullback_notification(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        current_price: float,
        highest_tp_level: int,
        pullback_price: float,
        unrealized_pnl: float,
        contracts: int
    ) -> bool:
        """
        发送止盈回撤通知

        Args:
            symbol: 交易对
            side: 方向
            entry_price: 开仓价格
            current_price: 当前价格
            highest_tp_level: 最高触及的止盈级别
            pullback_price: 回撤触发价格
            unrealized_pnl: 未实现盈亏(USD)
            contracts: 回撤的合约数量
        """
        side_cn = "做多" if side == 'long' else "做空"

        card = {
            "header": {
                "title": {
                    "content": f"止盈回撤 ⚠️ - L{highest_tp_level}后回撤",
                    "tag": "plain_text"
                },
                "template": "orange"
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**交易对**\n{symbol}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**方向**\n{side_cn}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**开仓价**\n${entry_price:.2f}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**当前价**\n${current_price:.2f}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**最高级别**\nL{highest_tp_level}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**回撤价**\n${pullback_price:.2f}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**回撤数量**\n{contracts}张"
                            }
                        },
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**未实现盈亏**\n${unrealized_pnl:+.2f}"
                            }
                        },
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**发送时间**\n{self._get_now_str()}"
                            }
                        }
                    ]
                }
            ]
        }

        return self._send_rich_card(card)

    def _get_reason_badge(self, reason: str) -> str:
        """根据平仓原因返回对应的徽章"""
        reason_map = {
            "TP": "<font color=green>止盈</font>",
            "tp": "<font color=green>止盈</font>",
            "止盈": "<font color=green>止盈</font>",
            "SL": "<font color=red>止损</font>",
            "sl": "<font color=red>止损</font>",
            "止损": "<font color=red>止损</font>",
            "SIGNAL": "<font color=blue>信号</font>",
            "signal": "<font color=blue>信号</font>",
            "信号": "<font color=blue>信号</font>",
            "TIMEOUT": "<font color=grey>超时</font>",
            "timeout": "<font color=grey>超时</font>",
            "超时": "<font color=grey>超时</font>",
            "DIF15": "<font color=orange>反转</font>",
            "dif15": "<font color=orange>反转</font>",
        }
        return reason_map.get(reason, reason)


    def send_system_startup_notification(
        self,
        system_name: str,
        mode: str,
        symbol: str,
        exchange_type: str = None
    ) -> bool:
        """
        发送系统启动通知

        Args:
            system_name: 系统名称
            mode: 运行模式 (测试网/实盘)
            symbol: 交易对
            exchange_type: 交易所类型
        """
        mode_color = "blue" if mode == "测试网" else "red"
        mode_icon = "🧪" if mode == "测试网" else "🔴"

        card = {
            "header": {
                "title": {
                    "content": f"系统启动通知 {mode_icon}",
                    "tag": "plain_text"
                },
                "template": mode_color
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**系统名称**\n{system_name}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**运行模式**\n{mode}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**交易对**\n{symbol}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**交易所**\n{exchange_type or '币安'}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**启动时间**\n{self._get_now_str()}"
                            }
                        },
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**发送时间**\n{self._get_now_str()}"
                            }
                        }
                    ]
                }
            ]
        }

        return self._send_rich_card(card)

    def send_binance_error_notification(
        self,
        error_message: str,
        error_type: str = "连接异常",
        mode: str = "实盘"
    ) -> bool:
        """
        发送币安接口异常通知

        Args:
            error_message: 错误信息
            error_type: 错误类型 (连接异常/下单失败/查询失败等)
            mode: 运行模式 (实盘/测试网)
        """
        mode_color = "red" if mode == "实盘" else "orange"
        mode_icon = "🔴" if mode == "实盘" else "🧪"

        card = {
            "header": {
                "title": {
                    "content": f"币安接口异常 ⚠️ - {error_type}",
                    "tag": "plain_text"
                },
                "template": mode_color
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**运行模式**\n{mode_icon} {mode}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**错误类型**\n{error_type}"
                            }
                        },
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**错误信息**\n{error_message}"
                            }
                        },
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**发生时间**\n{self._get_now_str()}"
                            }
                        }
                    ]
                }
            ]
        }

        return self._send_rich_card(card)


    def send_trade_history_report(
        self,
        trades: list,
        total_balance_btc: float = 0.0
    ) -> bool:
        """
        发送最近交易历史报告

        Args:
            trades: 交易记录列表，每个元素包含:
                - exit_time: 平仓时间
                - side: 方向 (long/short)
                - entry_price: 开仓价格
                - exit_price: 平仓价格
                - net_pnl_btc: 净盈亏(基础币种)
                - fee_btc: 手续费(基础币种)
            total_balance_btc: 当前总余额(基础币种)
        """
        if not trades:
            return False

        # 统计汇总
        total_pnl = sum(t.get('net_pnl_btc', 0) or 0 for t in trades)
        total_fee = sum(t.get('fee_btc', 0) or 0 for t in trades)
        win_count = sum(1 for t in trades if (t.get('net_pnl_btc', 0) or 0) > 0)
        loss_count = len(trades) - win_count

        # 报告颜色
        if total_pnl > 0:
            pnl_color = "green"
            pnl_icon = "盈利 ✅"
        elif total_pnl < 0:
            pnl_color = "red"
            pnl_icon = "亏损 ❌"
        else:
            pnl_color = "grey"
            pnl_icon = "平手 ➖"

        # 构建交易明细文本
        trade_lines = []
        for i, t in enumerate(trades, 1):
            exit_time = t.get('exit_time', '')
            if hasattr(exit_time, 'strftime'):
                time_str = exit_time.strftime('%m-%d %H:%M')
            else:
                time_str = str(exit_time)[:16] if exit_time else '-'
            
            side = t.get('side', '')
            side_cn = "多" if side == 'long' else "空"
            entry_price = t.get('entry_price', 0) or 0
            exit_price = t.get('exit_price', 0) or 0
            net_pnl = t.get('net_pnl_btc', 0) or 0
            fee = t.get('fee_btc', 0) or 0
            
            pnl_sign = "+" if net_pnl >= 0 else ""
            trade_lines.append(
                f"{i}. {time_str} | {side_cn} | "
                f"{entry_price:.1f}→{exit_price:.1f} | "
                f"{pnl_sign}{net_pnl:.6f} {self.display_asset} | 费:{fee:.6f}"
            )

        trades_content = "\n".join(trade_lines) if trade_lines else "暂无交易记录"

        card = {
            "header": {
                "title": {
                    "content": f"📊 最近{len(trades)}笔交易报告 - {pnl_icon}",
                    "tag": "plain_text"
                },
                "template": pnl_color
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**成功/失败**\n{win_count}/{loss_count}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**胜率**\n{win_count/len(trades)*100:.1f}%" if trades else "**胜率**\n-"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**总盈亏**\n{total_pnl:+.6f} {self.display_asset}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**总手续费**\n-{total_fee:.6f} {self.display_asset}"
                            }
                        }
                    ]
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**交易明细**\n```\n{trades_content}\n```"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**当前余额**\n{total_balance_btc:.6f} {self.display_asset}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**报告时间**\n{self._get_now_str()}"
                            }
                        }
                    ]
                }
            ]
        }

        return self._send_rich_card(card)
