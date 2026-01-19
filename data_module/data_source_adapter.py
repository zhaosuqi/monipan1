#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据源适配器 - 统一Binance API和交易所接口层的数据接口
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd

from core.logger import get_logger
from core.config import config

logger = get_logger(__name__)


class DataSourceAdapter:
    """
    数据源适配器 - 统一两种模式的数据接口

    模式1: 实盘模式 (DB_SIM_MODE=0, REPLAY_MODE=0)
        - 从Binance API获取实时数据
        - 用于实盘交易和实时监控

    模式2: 回测/验证模式 (DB_SIM_MODE=1 or REPLAY_MODE=1)
        - 通过MockExchange接口获取历史K线数据
        - 用于策略回测和验证计算准确性
        - 不直接访问数据库，而是通过交易所接口层
    """

    def __init__(self, mode: Optional[str] = None):
        """
        初始化数据源适配器

        Args:
            mode: 运行模式 'live' 或 'replay'
                  如果为None，则根据配置自动检测
        """
        if mode is None:
            # 自动检测模式
            self.mode = 'replay' if config.DB_SIM_MODE or config.REPLAY_MODE else 'live'
        else:
            self.mode = mode

        logger.info(f"初始化数据源适配器，模式: {self.mode}")

        if self.mode == 'live':
            # 实盘模式 - 使用Binance API
            from .kline_fetcher import KlineFetcher
            self.source = KlineFetcher()
            self.exchange = None
            logger.info("使用Binance API数据源")
        else:
            # 回测模式 - 使用MockExchange（通过exchange_layer）
            from exchange_layer import create_exchange, ExchangeType
            self.exchange = create_exchange(ExchangeType.MOCK_LOCAL)
            self.exchange.connect()
            self.source = None
            logger.info(f"使用MockExchange接口数据源: {config.HIST_DB_PATH}")

    def get_klines(self, limit: int = 1000, **kwargs) -> List[Dict[str, Any]]:
        """
        获取K线数据 - 统一接口

        Args:
            limit: 获取数量
            **kwargs: 其他参数
                - start_time: 开始时间
                - end_time: 结束时间
                - symbol: 交易对
                - interval: 时间周期

        Returns:
            K线数据列表
        """
        if self.mode == 'live':
            # 实盘模式 - 从Binance API获取
            logger.debug(f"从Binance API获取最新{limit}条K线")
            return self.source.fetch_latest_klines(limit=limit, **kwargs)
        else:
            # 回测模式 - 从MockExchange获取K线
            logger.debug(f"从MockExchange获取K线数据，limit={limit}")
            return self._get_klines_from_exchange(limit, **kwargs)

    def _get_klines_from_exchange(self, limit: int = 1000, **kwargs) -> List[Dict[str, Any]]:
        """
        从MockExchange获取K线数据（回测模式）

        Args:
            limit: 获取数量
            **kwargs: 其他参数

        Returns:
            K线数据列表
        """
        try:
            symbol = kwargs.get('symbol', config.SYMBOL)
            interval = kwargs.get('interval', config.KLINE_INTERVAL)
            start_time = kwargs.get('start_time')
            end_time = kwargs.get('end_time')

            # 转换时间格式为datetime对象
            if isinstance(start_time, str):
                start_time = pd.to_datetime(start_time).to_pydatetime()
            if isinstance(end_time, str):
                end_time = pd.to_datetime(end_time).to_pydatetime()

            # 通过exchange获取K线
            klines = self.exchange.get_klines(
                symbol=symbol,
                interval=interval,
                limit=limit,
                start_time=start_time,
                end_time=end_time
            )

            # 转换为字典格式（兼容原有代码）
            result = []
            for kline in klines:
                result.append({
                    'open_time': kline.open_time,
                    'open': kline.open,
                    'high': kline.high,
                    'low': kline.low,
                    'close': kline.close,
                    'volume': kline.volume,
                    'close_time': kline.close_time,
                    'quote_volume': kline.quote_volume,
                    'trades': kline.trades,
                    'taker_buy_base': kline.taker_buy_base,
                    'taker_buy_quote': kline.taker_buy_quote,
                })

            return result

        except Exception as e:
            logger.error(f"从MockExchange获取K线失败: {e}", exc_info=True)
            return []

    def get_klines_by_time_range(
        self,
        start_time: str,
        end_time: str,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        按时间范围获取K线数据

        Args:
            start_time: 开始时间 (格式: '2024-01-01 00:00:00')
            end_time: 结束时间 (格式: '2024-01-10 23:59:59')
            **kwargs: 其他参数

        Returns:
            K线数据列表
        """
        if self.mode == 'live':
            # 实盘模式 - Binance API不支持直接时间范围查询
            logger.warning(f"实盘模式不支持精确时间范围查询，将获取最新数据")
            return self.source.fetch_latest_klines(limit=1000, **kwargs)
        else:
            # 回测模式 - 通过exchange按时间范围查询
            logger.debug(f"从MockExchange获取时间范围K线: {start_time} 至 {end_time}")
            return self._get_klines_from_exchange(
                limit=100000,  # 大数量限制
                start_time=start_time,
                end_time=end_time,
                **kwargs
            )

    def get_latest_kline(self) -> Optional[Dict[str, Any]]:
        """
        获取最新一条K线

        Returns:
            最新K线数据，如果没有则返回None
        """
        klines = self.get_klines(limit=1)
        if klines and len(klines) > 0:
            return klines[0]
        return None

    def get_warmup_data(self, days: int = 200) -> List[Dict[str, Any]]:
        """
        获取预热数据（用于指标计算）

        Args:
            days: 预热天数

        Returns:
            历史K线数据列表
        """
        if self.mode == 'live':
            # 实盘模式 - 从Binance API获取
            logger.info(f"从Binance API获取最近{days}天的预热数据")
            return self.source.fetch_historical_klines(days=days)
        else:
            # 回测模式 - 通过exchange获取
            logger.info(f"从MockExchange获取{days}天的预热数据")
            # 计算天数对应的K线数量（1分钟K线）
            limit = days * 24 * 60
            return self._get_klines_from_exchange(limit=limit)

    def is_live_mode(self) -> bool:
        """是否为实盘模式"""
        return self.mode == 'live'

    def is_replay_mode(self) -> bool:
        """是否为回测/验证模式"""
        return self.mode == 'replay'

    def get_mode_info(self) -> Dict[str, Any]:
        """
        获取当前模式信息

        Returns:
            模式信息字典
        """
        if self.mode == 'live':
            return {
                'mode': self.mode,
                'mode_name': '实盘模式',
                'data_source': 'Binance API',
                'symbol': config.SYMBOL,
                'testnet': config.BINANCE_TESTNET,
            }
        else:
            return {
                'mode': self.mode,
                'mode_name': '回测/验证模式（MockExchange接口）',
                'data_source': f'MockExchange (数据库: {config.HIST_DB_PATH})',
                'db_path': config.HIST_DB_PATH,
                'table_name': config.HIST_TABLE,
                'connected': self.exchange.is_connected() if self.exchange else False,
            }


def create_data_source(mode: Optional[str] = None) -> DataSourceAdapter:
    """
    工厂函数：创建数据源适配器

    Args:
        mode: 运行模式，如果为None则自动检测

    Returns:
        数据源适配器实例
    """
    return DataSourceAdapter(mode=mode)


# 全局数据源实例
_data_source: Optional[DataSourceAdapter] = None


def get_data_source() -> DataSourceAdapter:
    """
    获取全局数据源实例（单例模式）

    每次调用时检查当前模式，如果模式变化则重新创建

    Returns:
        数据源适配器实例
    """
    global _data_source
    current_mode = get_current_mode()

    # 如果单例不存在或模式不匹配，重新创建
    if _data_source is None or _data_source.mode != current_mode:
        _data_source = DataSourceAdapter(mode=current_mode)

    return _data_source


def reset_data_source():
    """重置全局数据源实例"""
    global _data_source
    _data_source = None


# 便捷函数
def is_live_mode() -> bool:
    """快速检测是否为实盘模式"""
    return not (config.DB_SIM_MODE or config.REPLAY_MODE)


def is_replay_mode() -> bool:
    """快速检测是否为回测模式"""
    return config.DB_SIM_MODE or config.REPLAY_MODE


def get_current_mode() -> str:
    """获取当前运行模式"""
    return 'replay' if is_replay_mode() else 'live'
