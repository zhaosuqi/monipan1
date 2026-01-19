#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易所接口层 - 提供统一的交易所API抽象
支持三种模式：
1. 本地数据库回测服务
2. 本地虚拟币安API服务（模拟币安接口）
3. 币安官方虚拟盘/实盘
"""

from .base_exchange import BaseExchange
# Lazy imports to avoid circular import with trade_engine
# from .binance_exchange import BinanceExchange
# from .mock_exchange import MockExchange
from .exchange_factory import ExchangeType, create_exchange, get_exchange
from .models import Kline, Order, OrderStatus, OrderSide, OrderType

# Provide lazy access to exchange implementations
def __getattr__(name):
    if name == 'BinanceExchange':
        from .binance_exchange import BinanceExchange
        return BinanceExchange
    if name == 'MockExchange':
        from .mock_exchange import MockExchange
        return MockExchange
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    'BaseExchange',
    'BinanceExchange',
    'MockExchange',
    'ExchangeType',
    'create_exchange',
    'get_exchange',
    'Kline',
    'Order',
    'OrderStatus',
    'OrderSide',
    'OrderType',
]
