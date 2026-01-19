#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易所数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class OrderSide(Enum):
    """订单方向"""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """订单类型"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(Enum):
    """订单状态"""
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class Kline:
    """K线数据"""
    symbol: str
    interval: str
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: datetime
    quote_volume: float = 0.0
    trades: int = 0
    taker_buy_base: float = 0.0
    taker_buy_quote: float = 0.0

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'interval': self.interval,
            'open_time': self.open_time,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'close_time': self.close_time,
            'quote_volume': self.quote_volume,
            'trades': self.trades,
            'taker_buy_base': self.taker_buy_base,
            'taker_buy_quote': self.taker_buy_quote,
        }


@dataclass
class Order:
    """订单数据"""
    order_id: str
    client_order_id: str
    symbol: str
    side: OrderSide
    type: OrderType
    status: OrderStatus
    price: float
    quantity: float
    filled_quantity: float = 0.0
    avg_price: float = 0.0
    commission: float = 0.0
    commission_asset: str = ""
    time_in_force: str = "GTC"
    create_time: datetime = None
    update_time: datetime = None
    stop_price: float = None

    def __post_init__(self):
        if self.create_time is None:
            self.create_time = datetime.now()
        if self.update_time is None:
            self.update_time = datetime.now()

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'orderId': self.order_id,
            'clientOrderId': self.client_order_id,
            'symbol': self.symbol,
            'side': self.side.value,
            'type': self.type.value,
            'status': self.status.value,
            'price': self.price,
            'origQty': self.quantity,
            'executedQty': self.filled_quantity,
            'avgPrice': self.avg_price,
            'commission': self.commission,
            'timeInForce': self.time_in_force,
            'createTime': int(self.create_time.timestamp() * 1000) if self.create_time else None,
            'updateTime': int(self.update_time.timestamp() * 1000) if self.update_time else None,
            'stopPrice': self.stop_price,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Order':
        """从字典创建订单"""
        return cls(
            order_id=str(data.get('orderId', '')),
            client_order_id=str(data.get('clientOrderId', '')),
            symbol=data.get('symbol', ''),
            side=OrderSide(data.get('side', 'BUY')),
            type=OrderType(data.get('type', 'MARKET')),
            status=OrderStatus(data.get('status', 'NEW')),
            price=float(data.get('price', 0)),
            quantity=float(data.get('origQty', 0)),
            filled_quantity=float(data.get('executedQty', 0)),
            avg_price=float(data.get('avgPrice', 0)),
            commission=float(data.get('commission', 0)),
            time_in_force=data.get('timeInForce', 'GTC'),
            stop_price=data.get('stopPrice'),
        )


@dataclass
class AccountInfo:
    """账户信息"""
    total_wallet_balance: float  # 总钱包余额
    available_balance: float     # 可用余额
    unrealized_pnl: float        # 未实现盈亏

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'totalWalletBalance': self.total_wallet_balance,
            'availableBalance': self.available_balance,
            'unrealizedPnl': self.unrealized_pnl,
        }
