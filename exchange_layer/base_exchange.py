#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易所基础接口 - 抽象基类
定义统一的交易所API接口
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from .models import AccountInfo, Kline, Order


class BaseExchange(ABC):
    """
    交易所基础接口抽象类

    所有交易所实现必须继承此类并实现所有抽象方法
    """

    def __init__(self, api_key: str = "", api_secret: str = "", testnet: bool = False):
        """
        初始化交易所

        Args:
            api_key: API密钥
            api_secret: API密钥
            testnet: 是否使用测试网
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.connected = False

    @abstractmethod
    def connect(self) -> bool:
        """
        连接到交易所

        Returns:
            bool: 连接是否成功
        """
        pass

    @abstractmethod
    def disconnect(self):
        """断开交易所连接"""
        pass

    @abstractmethod
    def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 1000,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Kline]:
        """
        获取K线数据

        Args:
            symbol: 交易对
            interval: 时间周期 (1m, 5m, 15m, 1h, 4h, 1d等)
            limit: 数量限制
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            K线数据列表
        """
        pass

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        client_order_id: Optional[str] = None,
        current_time: Optional[datetime] = None,
        **kwargs
    ) -> Order:
        """
        下单

        Args:
            symbol: 交易对
            side: 方向 (BUY/SELL)
            order_type: 订单类型 (MARKET/LIMIT/STOP_MARKET/STOP_LIMIT)
            quantity: 数量
            price: 价格 (限价单必需)
            stop_price: 止损价格 (止损单必需)
            client_order_id: 客户端订单ID
            current_time: 当前K线时间戳（下单时刻）
            **kwargs: 其他参数

        Returns:
            Order: 订单对象
        """
        pass

    @abstractmethod
    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """
        取消订单

        Args:
            symbol: 交易对
            order_id: 订单ID

        Returns:
            bool: 是否成功取消
        """
        pass

    @abstractmethod
    def modify_order(
        self,
        symbol: str,
        order_id: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None
    ) -> bool:
        """
        修改订单

        Args:
            symbol: 交易对
            order_id: 订单ID
            quantity: 新数量（可选）
            price: 新价格（可选）

        Returns:
            bool: 是否成功修改
        """
        pass

    @abstractmethod
    def cancel_all_orders(self, symbol: str) -> int:
        """
        取消某个交易对的所有订单

        Args:
            symbol: 交易对

        Returns:
            int: 取消的订单数量
        """
        pass

    @abstractmethod
    def get_order(self, symbol: str, order_id: str) -> Optional[Order]:
        """
        查询订单

        Args:
            symbol: 交易对
            order_id: 订单ID

        Returns:
            Order: 订单对象，如果不存在返回None
        """
        pass

    @abstractmethod
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        查询所有挂单

        Args:
            symbol: 交易对，如果为None则查询所有交易对

        Returns:
            挂单列表
        """
        pass

    @abstractmethod
    def get_account_info(self, asset: str = 'BTC') -> AccountInfo:
        """
        获取账户信息

        Args:
            asset: 资产类型，默认 BTC（币本位合约以 BTC 计价）

        Returns:
            AccountInfo: 账户信息
        """
        pass

    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取持仓信息

        Args:
            symbol: 交易对

        Returns:
            持仓信息字典，如果无持仓返回None
        """
        pass

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.connected

    def get_exchange_info(self) -> Dict[str, Any]:
        """
        获取交易所信息

        Returns:
            交易所信息字典
        """
        return {
            'name': self.__class__.__name__,
            'testnet': self.testnet,
            'connected': self.connected,
        }
