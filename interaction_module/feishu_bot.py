#!/usr/bin/env python3
"""飞书通知机器人 - 支持开仓、平仓、止盈等交易事件通知"""
import requests
from datetime import datetime
from typing import Dict, Optional

from core.logger import get_logger
from core.config import config


class FeishuBot:
    def __init__(self):
        self.logger = get_logger('interaction_module.feishu')
        self.webhook = config.FEISHU_WEBHOOK
        self.enabled = config.FEISHU_ENABLED

    def send_message(self, message: str) -> bool:
        """发送普通文本消息"""
        if not self.enabled or not self.webhook:
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

    def send_trade_notification(self, signal: Dict) -> bool:
        """发送交易信号通知（兼容旧接口）"""
        message = f"交易信号: {signal.get('action')} {signal.get('side')}\n原因: {signal.get('reason')}"
        return self.send_message(message)

    def _send_rich_card(self, card: Dict) -> bool:
        """发送富文本卡片消息"""
        if not self.enabled or not self.webhook:
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

    def send_open_position_notification(
        self,
        symbol: str,
        side: str,
        price: float,
        contracts: int,
        signal_name: str,
        ts: Optional[datetime] = None
    ) -> bool:
        """
        发送开仓通知（富文本卡片）

        Args:
            symbol: 交易对
            side: 方向 (long/short)
            price: 开仓价格
            contracts: 合约数量
            signal_name: 信号名称
            ts: 开仓时间
        """
        # 中文方向显示
        side_cn = "做多 📈" if side == 'long' else "做空 📉"
        side_color = "green" if side == 'long' else "red"

        time_str = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        card = {
            "header": {
                "title": {
                    "content": f"开仓通知 {side_cn}",
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
                                "content": f"**开仓价格**\n${price:.2f}"
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
                                "content": f"**信号来源**\n{signal_name}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**开仓时间**\n{time_str}"
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
        gross_usd: float,
        fee_usd: float,
        net_usd: float,
        net_btc: float,
        reason: str,
        tp_hit: list = None
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
            gross_usd: 毛盈亏(USD)
            fee_usd: 手续费(USD)
            net_usd: 净盈亏(USD)
            net_btc: 净盈亏(BTC)
            reason: 平仓原因
            tp_hit: 已触发的止盈级别
        """
        # 中文方向显示
        side_cn = "做多" if side == 'long' else "做空"

        # 盈亏颜色和图标
        if net_usd > 0:
            pnl_color = "green"
            pnl_icon = "盈利 ✅"
        elif net_usd < 0:
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
                                "content": f"**毛盈亏**\n${gross_usd:+.2f}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**手续费**\n-${fee_usd:.2f}"
                            }
                        },
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**净盈亏**\n**${net_usd:+.2f} ({net_btc:+.6f} BTC)**"
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
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**平仓时间**\n{time_str}"
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
        unrealized_pnl: float
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
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**未实现盈亏**\n${unrealized_pnl:+.2f}"
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

    def send_sync_open_notification(
        self,
        symbol: str,
        side: str,
        price: float,
        contracts: int,
        ts: Optional[datetime] = None
    ) -> bool:
        """
        发送同步开仓通知（从币安同步的开仓）

        Args:
            symbol: 交易对
            side: 方向 (long/short)
            price: 开仓价格
            contracts: 合约数量
            ts: 开仓时间
        """
        side_cn = "做多 📈" if side == 'long' else "做空 📉"
        side_color = "green" if side == 'long' else "red"

        time_str = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        card = {
            "header": {
                "title": {
                    "content": f"同步开仓 🔄 {side_cn}",
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
                                "content": f"**开仓价格**\n${price:.2f}"
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
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**同步时间**\n{time_str}"
                            }
                        }
                    ]
                }
            ]
        }

        return self._send_rich_card(card)

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

        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**启动时间**\n{time_str}"
                            }
                        }
                    ]
                }
            ]
        }

        return self._send_rich_card(card)

    def send_sync_close_notification(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        close_price: float,
        contracts: int,
        entry_time: datetime,
        close_time: datetime,
        gross_usd: float,
        fee_usd: float,
        net_usd: float,
        net_btc: float
    ) -> bool:
        """
        发送同步平仓通知（从币安同步的平仓）

        Args:
            symbol: 交易对
            side: 方向
            entry_price: 开仓价格
            close_price: 平仓价格
            contracts: 平仓合约数量
            entry_time: 开仓时间
            close_time: 平仓时间
            gross_usd: 毛盈亏(USD)
            fee_usd: 手续费(USD)
            net_usd: 净盈亏(USD)
            net_btc: 净盈亏(BTC)
        """
        side_cn = "做多" if side == 'long' else "做空"

        if net_usd > 0:
            pnl_color = "green"
            pnl_icon = "盈利 ✅"
        elif net_usd < 0:
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

        card = {
            "header": {
                "title": {
                    "content": f"同步平仓 🔄 - {pnl_icon}",
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
                                "content": f"**数量**\n{contracts}张"
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
                                "content": f"**毛盈亏**\n${gross_usd:+.2f}"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**手续费**\n-${fee_usd:.2f}"
                            }
                        },
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**净盈亏**\n**${net_usd:+.2f} ({net_btc:+.6f} BTC)**"
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
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**同步时间**\n{time_str}"
                            }
                        }
                    ]
                }
            ]
        }

        return self._send_rich_card(card)

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

        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**启动时间**\n{time_str}"
                            }
                        }
                    ]
                }
            ]
        }

        return self._send_rich_card(card)
