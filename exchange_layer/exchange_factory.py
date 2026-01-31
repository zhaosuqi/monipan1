#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易所工厂 - 根据配置创建交易所实例
"""

from enum import Enum
from typing import Optional

from core.config import config
# Lazy imports to avoid circular import with trade_engine
# from .binance_exchange import BinanceExchange
# from .mock_exchange import MockExchange
from core.logger import get_logger

from .base_exchange import BaseExchange

logger = get_logger('exchange_layer.factory')


class ExchangeType(Enum):
    """交易所类型"""
    BINANCE_LIVE = "binance_live"      # 币安实盘
    BINANCE_TESTNET = "binance_testnet"  # 币安测试网
    MOCK_LOCAL = "mock_local"          # 本地模拟（数据库）


def create_exchange(
    exchange_type: Optional[ExchangeType] = None,
    **kwargs
) -> BaseExchange:
    """
    创建交易所实例

    Args:
        exchange_type: 交易所类型，如果为None则从配置自动检测
        **kwargs: 额外参数（如db_path, table_name等）

    Returns:
        交易所实例
    """
    if exchange_type is None:
        # 根据配置自动检测
        exchange_type = detect_exchange_type()

    logger.info(f"创建交易所实例: {exchange_type.value}")

    if exchange_type == ExchangeType.BINANCE_LIVE:
        from .binance_exchange import BinanceExchange

        # 实盘使用实盘密钥，如果没有则回退到通用密钥
        api_key = config.BINANCE_LIVE_API_KEY or config.BINANCE_API_KEY
        api_secret = config.BINANCE_LIVE_API_SECRET or config.BINANCE_API_SECRET
        logger.info(f"实盘 API Key: {api_key[:8]}... (长度: {len(api_key)})")
        logger.info(f"实盘 API Secret: {api_secret[:8]}... (长度: {len(api_secret)})")
        exchange = BinanceExchange(
            api_key=api_key,
            api_secret=api_secret,
            testnet=False
        )

    elif exchange_type == ExchangeType.BINANCE_TESTNET:
        from .binance_exchange import BinanceExchange

        # 测试网优先使用测试网密钥，如果没有则回退到通用密钥
        api_key = config.BINANCE_TESTNET_API_KEY or config.BINANCE_API_KEY
        api_secret = config.BINANCE_TESTNET_API_SECRET or config.BINANCE_API_SECRET
        logger.info(f"测试网 API Key: {api_key[:8]}... (长度: {len(api_key)})")
        exchange = BinanceExchange(
            api_key=api_key,
            api_secret=api_secret,
            testnet=True
        )

    elif exchange_type == ExchangeType.MOCK_LOCAL:
        from .mock_exchange import MockExchange
        exchange = MockExchange(
            db_path=kwargs.get('db_path', config.HIST_DB_PATH),
            table_name=kwargs.get('table_name', config.HIST_TABLE),
            api_key="",  # 本地模拟不需要API密钥
            api_secret="",
            testnet=False
        )

    else:
        raise ValueError(f"不支持的交易所类型: {exchange_type}")

    return exchange


def detect_exchange_type() -> ExchangeType:
    """
    根据配置自动检测交易所类型

    检测逻辑：
    1. 如果 EXCHANGE_TYPE 已设置，使用该值
    2. 如果 DB_SIM_MODE=1 或 REPLAY_MODE=1，使用 MOCK_LOCAL
    3. 如果 BINANCE_TESTNET=1，使用 BINANCE_TESTNET
    4. 否则使用 BINANCE_LIVE

    Returns:
        ExchangeType
    """
    # 优先使用配置的交易所类型
    if config.EXCHANGE_TYPE:
        try:
            return ExchangeType(config.EXCHANGE_TYPE.lower())
        except ValueError:
            logger.warning(f"无效的 EXCHANGE_TYPE: {config.EXCHANGE_TYPE}，使用自动检测")

    is_replay = config.DB_SIM_MODE or config.REPLAY_MODE

    if is_replay:
        return ExchangeType.MOCK_LOCAL
    elif config.BINANCE_TESTNET:
        return ExchangeType.BINANCE_TESTNET
    else:
        return ExchangeType.BINANCE_LIVE


# 全局交易所实例
_exchange_instance: Optional[BaseExchange] = None


def get_exchange(**kwargs) -> BaseExchange:
    """
    获取全局交易所实例（单例模式）

    Args:
        **kwargs: 创建参数

    Returns:
        交易所实例
    """
    global _exchange_instance

    if _exchange_instance is None or not _exchange_instance.is_connected():
        _exchange_instance = create_exchange(**kwargs)
        _exchange_instance.connect()

    return _exchange_instance


def reset_exchange():
    """重置全局交易所实例"""
    global _exchange_instance

    if _exchange_instance and _exchange_instance.is_connected():
        _exchange_instance.disconnect()

    _exchange_instance = None


def switch_exchange(exchange_type: ExchangeType, **kwargs):
    """
    切换交易所类型

    Args:
        exchange_type: 新的交易所类型
        **kwargs: 创建参数
    """
    logger.info(f"切换交易所: {exchange_type.value}")

    # 断开当前连接
    reset_exchange()

    # 创建新实例
    global _exchange_instance
    _exchange_instance = create_exchange(exchange_type, **kwargs)
    _exchange_instance.connect()

    logger.info("✓ 交易所切换完成")
