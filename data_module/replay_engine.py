#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测引擎 - 从历史数据回放K线并模拟交易
通过MockExchange接口获取数据，不再直接访问数据库
"""

import pandas as pd
from typing import Dict, Optional

from core.logger import get_logger
from core.config import config
from core.database import get_db
from data_module.data_source_adapter import create_data_source


class ReplayEngine:
    """回测引擎 - 通过MockExchange接口回放K线并模拟交易"""

    def __init__(self):
        self.logger = get_logger('data_module.replay')
        self.db = get_db()
        # 使用DataSourceAdapter（通过MockExchange接口）
        self.data_source = create_data_source()
        # 同时创建MockExchange用于订单操作
        from exchange_layer import create_exchange, ExchangeType
        self.exchange = create_exchange(ExchangeType.MOCK_LOCAL)
        self.exchange.connect()

    def run_backtest(
        self,
        start_time: str,
        end_time: str,
        warm_days: int = 50,
        chunk_size: int = 2000
    ) -> Dict:
        """
        运行回测

        Args:
            start_time: 开始时间 (格式: 2024-01-01 00:00:00)
            end_time: 结束时间 (格式: 2024-01-10 23:59:59)
            warm_days: 预热天数
            chunk_size: 每次读取的K线数量

        Returns:
            回测结果统计
        """
        self.logger.info("=" * 80)
        self.logger.info("回测模式启动")
        self.logger.info("=" * 80)

        # 转换时间
        start_ts = pd.to_datetime(start_time)
        end_ts = pd.to_datetime(end_time)

        self.logger.info(f"回测时间范围: {start_ts} 至 {end_ts}")
        self.logger.info(f"预热天数: {warm_days}天")

        # 1. 检查数据可用性
        self._check_data_availability(start_ts, end_ts)

        # 2. 加载预热数据
        warm_data = self._load_warm_data(start_ts, warm_days)
        self.logger.info(f"加载预热数据: {len(warm_data)}条")

        # 3. 预热指标引擎
        from data_module.indicator_calculator import IndicatorCalculator
        indicator_engine = IndicatorCalculator()
        indicator_engine.seed_warm_data(warm_data)

        # 4. 回测主循环
        stats = self._replay_loop(
            start_ts=start_ts,
            end_ts=end_ts,
            chunk_size=chunk_size,
            indicator_engine=indicator_engine
        )

        self.logger.info("=" * 80)
        self.logger.info("回测完成")
        self.logger.info(f"处理K线数: {stats['bars_processed']}")
        self.logger.info(f"交易次数: {stats['trade_count']}")
        self.logger.info(f"实现盈亏: {stats['realized_pnl']:.2f} USD")
        self.logger.info("=" * 80)

        return stats

    def _check_data_availability(self, start_ts: pd.Timestamp, end_ts: pd.Timestamp):
        """检查数据库中是否有足够的数据（通过DataSourceAdapter）"""
        # 通过data_source获取数据
        klines = self.data_source.get_klines(
            limit=1,
            symbol=config.SYMBOL,
            interval=config.KLINE_INTERVAL
        )

        if not klines:
            raise ValueError("无法获取K线数据，请检查数据库")

        # 确认数据源已连接
        mode_info = self.data_source.get_mode_info()
        self.logger.info(f"✓ 数据源已连接: {mode_info['data_source']}")

        # 尝试获取最早和最晚的数据来检查时间范围
        try:
            earliest = self.data_source.get_klines(
                symbol=config.SYMBOL,
                interval=config.KLINE_INTERVAL,
                limit=1
            )
            # 获取最新的数据（通过限制数量并取最后一个）
            latest_batch = self.data_source.get_klines(
                symbol=config.SYMBOL,
                interval=config.KLINE_INTERVAL,
                limit=1000
            )
            if latest_batch:
                db_start = pd.to_datetime(earliest[0]['open_time'])
                db_end = pd.to_datetime(latest_batch[-1]['open_time'])

                self.logger.info(f"数据库时间范围: {db_start} 至 {db_end}")
                self.logger.info(f"回测时间范围: {start_ts} 至 {end_ts}")

                if start_ts < db_start:
                    raise ValueError(f"开始时间 {start_ts} 早于数据库起始时间 {db_start}")

                if end_ts > db_end:
                    raise ValueError(f"结束时间 {end_ts} 晚于数据库结束时间 {db_end}")
        except Exception as e:
            self.logger.warning(f"无法验证时间范围: {e}")
            self.logger.info("将继续执行回测，请确保时间范围内有数据")

    def _load_warm_data(self, start_ts: pd.Timestamp, days: int) -> pd.DataFrame:
        """
        加载预热数据（通过DataSourceAdapter）

        Args:
            start_ts: 回测开始时间
            days: 预热天数

        Returns:
            预热数据DataFrame
        """
        preload_start = start_ts - pd.Timedelta(days=days)
        preload_end = start_ts - pd.Timedelta(minutes=1)

        # 使用data_source获取预热数据
        klines = self.data_source.get_klines_by_time_range(
            start_time=preload_start.isoformat(),
            end_time=preload_end.isoformat(),
            symbol=config.SYMBOL,
            interval=config.KLINE_INTERVAL
        )

        # 转换为DataFrame（保持与原有格式兼容）
        if klines:
            df = pd.DataFrame(klines)
            self.logger.info(f"预热数据范围: {preload_start} 至 {preload_end}, 共 {len(df)} 条")
            return df
        else:
            self.logger.warning(f"未找到预热数据: {preload_start} 至 {preload_end}")
            # 返回空DataFrame，但包含必要的列
            return pd.DataFrame(columns=['open_time', 'open', 'high', 'low', 'close', 'volume'])

    def _replay_loop(
        self,
        start_ts: pd.Timestamp,
        end_ts: pd.Timestamp,
        chunk_size: int,
        indicator_engine
    ) -> Dict:
        """
        回测主循环

        Args:
            start_ts: 开始时间
            end_ts: 结束时间
            chunk_size: 分块大小
            indicator_engine: 指标引擎

        Returns:
            统计信息
        """
        bar_count = 0
        trade_count = 0
        realized_pnl = 0.0

        # 批量写入缓冲区
        persist_buffer = []
        persist_batch_size = 500  # 每500条K线批量写入一次

        # 清空回测相关表
        self.logger.info("清空回测历史数据...")
        self.db.execute("DELETE FROM sim_log")
        self.db.execute("DELETE FROM orders")
        self.db.execute("DELETE FROM order_status_history")
        self.db.execute("DELETE FROM klines_1m_sim")
        self.logger.info("✓ 历史数据已清理 (sim_log, orders, order_status_history, klines_1m_sim)")

        # 从数据库迭代读取K线
        for bar in self._iter_bars(start_ts, end_ts, chunk_size):
            bar_count += 1

            # 1. 更新指标
            try:
                indicators = indicator_engine.update(bar)
            except Exception as e:
                self.logger.error(f"指标更新失败: {e}")
                continue

            # 2. 添加到批量写入缓冲区（不立即写入数据库）
            persist_buffer.append((bar, indicators))

            # 3. 批量写入数据库
            if len(persist_buffer) >= persist_batch_size:
                self._persist_bars_batch(persist_buffer)
                persist_buffer.clear()

            # 4. 执行交易逻辑
            pnl_result = self._execute_trading_logic(bar, indicators)

            if pnl_result:
                realized_pnl += pnl_result.get('pnl', 0)
                trade_count += 1

            # 5. 定期刷新日志
            if bar_count % 500 == 0:
                self.logger.info(
                    f"已处理 {bar_count} 条K线, "
                    f"当前时间: {bar['open_time']}, "
                    f"交易次数: {trade_count}, "
                    f"实现盈亏: {realized_pnl:.2f} USD"
                )

        # 写入剩余数据
        if persist_buffer:
            self._persist_bars_batch(persist_buffer)

        return {
            'bars_processed': bar_count,
            'trade_count': trade_count,
            'realized_pnl': realized_pnl
        }

    def _iter_bars(
        self,
        start_ts: pd.Timestamp,
        end_ts: pd.Timestamp,
        chunk_size: int
    ):
        """
        从DataSourceAdapter流式读取K线（优化内存使用）

        Args:
            start_ts: 开始时间
            end_ts: 结束时间
            chunk_size: 分块大小（每次从数据库读取的K线数量）

        Yields:
            K线数据字典
        """
        # 计算总时间范围
        total_seconds = (end_ts - start_ts).total_seconds()
        chunk_seconds = chunk_size * 60  # 假设1分钟K线

        # 分批读取，避免一次性加载所有数据到内存
        current_start = start_ts
        while current_start < end_ts:
            # 计算当前批次的结束时间
            current_end = min(current_start + pd.Timedelta(seconds=chunk_seconds), end_ts)

            # 获取当前批次的数据
            klines = self.data_source.get_klines_by_time_range(
                start_time=current_start.isoformat(),
                end_time=current_end.isoformat(),
                symbol=config.SYMBOL,
                interval=config.KLINE_INTERVAL
            )

            # 逐条yield
            for kline in klines:
                yield kline

            # 移动到下一个批次
            current_start = current_end + pd.Timedelta(minutes=1)

    def _persist_bars_batch(self, batch: list):
        """批量持久化K线数据到klines_1m_sim表"""
        try:
            # 准备批量插入数据
            records = []
            for bar, indicators in batch:
                records.append((
                    bar['open_time'].isoformat() if hasattr(bar['open_time'], 'isoformat') else str(bar['open_time']),
                    float(bar['open']),
                    float(bar['high']),
                    float(bar['low']),
                    float(bar['close']),
                    float(bar['volume'])
                ))

            # 批量插入
            self.db.conn.executemany("""
                INSERT OR REPLACE INTO klines_1m_sim
                (open_time, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?)
            """, records)
            self.db.conn.commit()

        except Exception as e:
            self.logger.error(f"批量持久化K线失败: {e}")

    def _persist_bar(self, bar: dict, indicators: dict):
        """持久化K线数据到klines_1m_sim表"""
        try:
            self.db.execute("""
                INSERT OR REPLACE INTO klines_1m_sim
                (open_time, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                bar['open_time'].isoformat(),
                bar['open'],
                bar['high'],
                bar['low'],
                bar['close'],
                bar['volume']
            ))
        except Exception as e:
            self.logger.error(f"持久化K线失败: {e}")

    def _execute_trading_logic(self, bar: dict, indicators: dict) -> Optional[Dict]:
        """
        执行交易逻辑（通过self.exchange进行订单操作）

        Args:
            bar: K线数据
            indicators: 指标数据

        Returns:
            盈亏信息
        """
        # 这里集成信号计算和订单执行逻辑
        # 使用self.exchange进行订单操作（已经连接到MockExchange）

        # 示例：当需要下单时
        # if should_buy:
        #     order = self.exchange.place_order(
        #         symbol=config.SYMBOL,
        #         side='BUY',
        #         order_type='MARKET',
        #         quantity=1.0
        #     )
        #     self.logger.info(f"下单成功: {order.order_id}, 状态={order.status.value}")

        # 示例：查询账户
        # account = self.exchange.get_account_info()
        # self.logger.info(f"账户余额: {account.total_wallet_balance}")

        # 暂时返回None,后续会集成完整的交易逻辑
        return None

# 注意: 旧的iter_sqlite_bars函数已移除
# 现在统一使用DataSourceAdapter通过MockExchange接口获取数据
