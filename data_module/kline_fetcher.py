#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K线数据获取器
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from binance.cm_futures import CMFutures

from core.logger import get_logger
from core.config import config


class KlineFetcher:
    """K线数据获取器"""

    def __init__(self):
        self.logger = get_logger('data_module.kline_fetcher')

        # 根据是否测试网选择不同的端点
        if config.BINANCE_TESTNET:
            # 测试网
            self.client = CMFutures(
                key=config.BINANCE_API_KEY,
                secret=config.BINANCE_API_SECRET
            )
            # 设置测试网端点
            self.client.base_url = 'https://testnet.binancefuture.com'
        else:
            # 实盘
            self.client = CMFutures(
                key=config.BINANCE_API_KEY,
                secret=config.BINANCE_API_SECRET
            )

    def fetch_latest_klines(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        获取最新的K线数据

        Args:
            limit: 获取数量，默认使用配置值

        Returns:
            K线数据列表
        """
        try:
            limit = limit or config.KLINE_LIMIT
            self.logger.debug(f"获取最新{limit}条K线")

            klines = self.client.klines(
                symbol=config.SYMBOL,
                interval=config.KLINE_INTERVAL,
                limit=limit
            )

            # 转换为字典格式
            result = []
            for kline in klines:
                result.append({
                    'open_time': kline[0],
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5]),
                    'close_time': kline[6],
                    'quote_volume': float(kline[7]),
                    'trades': int(kline[8]),
                    'taker_buy_base': float(kline[9]),
                    'taker_buy_quote': float(kline[10]),
                    'ignore': kline[11]
                })

            self.logger.debug(f"成功获取{len(result)}条K线")
            return result

        except Exception as e:
            self.logger.error(f"获取K线失败: {e}", exc_info=True)
            return []

    def fetch_klines_by_time(
        self,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        获取指定时间范围的K线

        Args:
            start_time: 开始时间
            end_time: 结束时间
            limit: 单次获取数量

        Returns:
            K线数据列表
        """
        try:
            start_ts = int(start_time.timestamp() * 1000)
            end_ts = int(end_time.timestamp() * 1000) if end_time else None

            self.logger.debug(f"获取K线: {start_time} - {end_time}")

            klines = self.client.klines(
                symbol=config.SYMBOL,
                interval=config.KLINE_INTERVAL,
                startTime=start_ts,
                endTime=end_ts,
                limit=limit
            )

            result = []
            for kline in klines:
                result.append({
                    'open_time': kline[0],
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5]),
                    'close_time': kline[6],
                    'quote_volume': float(kline[7]),
                    'trades': int(kline[8]),
                    'taker_buy_base': float(kline[9]),
                    'taker_buy_quote': float(kline[10]),
                    'ignore': kline[11]
                })

            self.logger.debug(f"成功获取{len(result)}条K线")
            return result

        except Exception as e:
            self.logger.error(f"获取K线失败: {e}", exc_info=True)
            return []

    def fetch_historical_klines(
        self,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        获取历史K线数据

        Args:
            days: 获取最近多少天

        Returns:
            K线数据列表
        """
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)

            all_klines = []
            current_start = start_time

            while current_start < end_time:
                klines = self.fetch_klines_by_time(
                    current_start,
                    end_time,
                    limit=1000
                )

                if not klines:
                    break

                all_klines.extend(klines)

                # 更新起始时间为最后一条K线的时间
                current_start = datetime.fromtimestamp(
                    klines[-1]['close_time'] / 1000
                ) + timedelta(seconds=1)

                self.logger.debug(f"已获取{len(all_klines)}条K线")

            self.logger.info(f"获取历史K线完成: {len(all_klines)}条")
            return all_klines

        except Exception as e:
            self.logger.error(f"获取历史K线失败: {e}", exc_info=True)
            return []
