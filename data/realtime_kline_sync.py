#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时K线同步脚本

功能:
1. 检查klines_1m表最后一条数据的open_time
2. 从币安获取从open_time到当前时刻的所有分钟K线，补充到klines_1m表
3. 通过WebSocket实时监控分钟级K线数据，持续写入klines_1m表

所有时间使用UTC时间
"""

import asyncio
import json
import os
import signal
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from core.config import config
from core.logger import get_logger

# WebSocket 相关
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    print("警告: 未安装 websockets 库，请运行: pip install websockets")

# 币安 REST API
from binance.cm_futures import CMFutures

logger = get_logger('realtime_kline_sync')


class RealtimeKlineSync:
    """实时K线同步器"""
    
    def __init__(self):
        self.db_path = config.DB_PATH
        self.symbol = config.SYMBOL
        self.interval = '1m'
        self.running = False
        
        # 初始化币安客户端 (用于REST API补数据)
        # if config.BINANCE_TESTNET:
        #     self.client = CMFutures(
        #         key=config.BINANCE_API_KEY,
        #         secret=config.BINANCE_API_SECRET
        #     )
        #     self.client.base_url = 'https://testnet.binancefuture.com'
        #     # 测试网WebSocket (注意：测试网WebSocket可能不稳定，可选用实盘流)
        #     # self.ws_base_url = 'wss://dstream.binancefuture.com'
        #     # 使用实盘WebSocket获取行情（测试网WebSocket不稳定）
        #     self.ws_base_url = 'wss://dstream.binance.com'
        # else:
        self.client = CMFutures(
                key=config.BINANCE_API_KEY,
                secret=config.BINANCE_API_SECRET
            )
        self.ws_base_url = 'wss://dstream.binance.com'
        
        # WebSocket URL (币安合约永续流)
        # 格式: wss://dstream.binance.com/ws/<streamName>
        # K线流: <symbol>@kline_<interval>
        symbol_lower = self.symbol.lower()
        self.ws_url = f"{self.ws_base_url}/ws/{symbol_lower}@kline_{self.interval}"
        
        logger.info(f"初始化完成 - 交易对: {self.symbol}, 数据库: {self.db_path}")
        logger.info(f"WebSocket URL: {self.ws_url}")
    
    def get_db_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,
            isolation_level=None
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_last_kline_time(self) -> Optional[datetime]:
        """获取klines_1m表最后一条数据的open_time (UTC时间)"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT open_time 
                FROM klines_1m 
                ORDER BY open_time DESC 
                LIMIT 1
            """)
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                last_time_str = row['open_time']
                # 解析ISO格式时间字符串
                last_time = datetime.fromisoformat(last_time_str)
                # 确保是UTC时间
                if last_time.tzinfo is None:
                    last_time = last_time.replace(tzinfo=timezone.utc)
                logger.info(f"数据库最后K线时间 (open_time): {last_time}")
                return last_time
            else:
                logger.warning("klines_1m表为空")
                return None
                
        except Exception as e:
            logger.error(f"获取最后K线时间失败: {e}")
            return None
    
    def fetch_klines_rest(
        self, 
        start_time: datetime, 
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        通过REST API获取K线数据
        
        Args:
            start_time: 开始时间 (UTC)
            end_time: 结束时间 (UTC)，默认为当前时间
            limit: 每次请求数量限制
            
        Returns:
            K线数据列表
        """
        try:
            params = {
                'symbol': self.symbol,
                'interval': self.interval,
                'limit': limit,
                'startTime': int(start_time.timestamp() * 1000)
            }
            
            if end_time:
                params['endTime'] = int(end_time.timestamp() * 1000)
            
            logger.debug(f"REST请求K线: {start_time} ~ {end_time or 'now'}")
            
            klines = self.client.klines(**params)
            
            result = []
            for kline in klines:
                # 解析K线数据
                open_time_utc = datetime.fromtimestamp(kline[0] / 1000, tz=timezone.utc)
                close_time_utc = datetime.fromtimestamp(kline[6] / 1000, tz=timezone.utc)
                
                result.append({
                    'symbol': self.symbol,
                    'interval': self.interval,
                    'open_time': open_time_utc,
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5]),
                    'close_time': close_time_utc,
                    'quote_asset_volume': float(kline[7]),
                    'number_of_trades': int(kline[8]),
                    'taker_buy_base': float(kline[9]),
                    'taker_buy_quote': float(kline[10]),
                })
            
            logger.debug(f"获取到 {len(result)} 条K线")
            return result
            
        except Exception as e:
            logger.error(f"REST获取K线失败: {e}")
            return []
    
    def save_klines_to_db(self, klines: List[Dict[str, Any]]) -> int:
        """
        保存K线数据到klines_1m表
        
        Args:
            klines: K线数据列表
            
        Returns:
            成功插入的数量
        """
        if not klines:
            return 0
        
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            inserted_count = 0
            
            for kline in klines:
                try:
                    # 格式化时间为ISO格式
                    open_time_str = kline['open_time'].strftime('%Y-%m-%dT%H:%M:%S')
                    close_time_str = kline['close_time'].strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]
                    
                    sql = """
                        INSERT OR REPLACE INTO klines_1m
                        (symbol, interval, open_time, open, high, low, close, volume,
                         close_time, quote_asset_volume, number_of_trades,
                         taker_buy_base, taker_buy_quote)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    
                    cursor.execute(sql, (
                        kline['symbol'],
                        kline['interval'],
                        open_time_str,
                        kline['open'],
                        kline['high'],
                        kline['low'],
                        kline['close'],
                        kline['volume'],
                        close_time_str,
                        kline['quote_asset_volume'],
                        kline['number_of_trades'],
                        kline['taker_buy_base'],
                        kline['taker_buy_quote'],
                    ))
                    inserted_count += 1
                    
                except sqlite3.IntegrityError:
                    # 已存在，跳过
                    continue
                except Exception as e:
                    logger.warning(f"插入单条K线失败: {e}")
                    continue
            
            conn.commit()
            conn.close()
            
            if inserted_count > 0:
                logger.info(f"✓ 已保存 {inserted_count} 条K线到 klines_1m 表")
            
            return inserted_count
            
        except Exception as e:
            logger.error(f"保存K线到数据库失败: {e}")
            return 0
    
    def sync_historical_klines(self) -> int:
        """
        同步历史K线数据 (从数据库最后一条到当前时间)
        
        Returns:
            同步的K线数量
        """
        logger.info("=" * 50)
        logger.info("开始同步历史K线数据...")
        
        # 获取最后一条K线时间
        last_time = self.get_last_kline_time()
        
        if last_time is None:
            # 如果表为空，默认获取最近1天的数据
            last_time = datetime.now(timezone.utc) - timedelta(days=1)
            logger.info(f"表为空，从1天前开始: {last_time}")
        
        # 计算需要同步的时间范围
        # 从最后一条K线的下一分钟开始
        start_time = last_time + timedelta(minutes=1)
        end_time = datetime.now(timezone.utc)
        
        # 如果开始时间已经超过当前时间，不需要同步
        if start_time >= end_time:
            logger.info("数据已是最新，无需同步历史数据")
            return 0
        
        logger.info(f"同步时间范围: {start_time} ~ {end_time}")
        
        # 计算需要获取的分钟数
        duration_minutes = int((end_time - start_time).total_seconds() / 60)
        logger.info(f"需要同步约 {duration_minutes} 分钟的数据")
        
        total_synced = 0
        current_start = start_time
        
        # 分批获取 (每次最多1000条)
        while current_start < end_time:
            # 强制分片：每次请求 900 分钟范围内的数据
            # 将步长设为 900 (小于 limit 1000)，确保在 limit 限制内能取完该时间段的所有数据
            # 这样可以避免因 limit 截断导致的边界数据丢失问题
            batch_end_time = current_start + timedelta(minutes=900)
            # 确保不超出总结束时间
            request_end_time = min(batch_end_time, end_time)

            klines = self.fetch_klines_rest(
                start_time=current_start,
                end_time=request_end_time,
                limit=1000
            )
            
            if not klines:
                # 当前时间窗口无数据，直接跳过该窗口
                current_start = request_end_time
                continue
            
            # 过滤已完成的K线 (close_time < 当前时间)
            now = datetime.now(timezone.utc)
            finished_klines = [
                k for k in klines 
                if k['close_time'] < now
            ]
            
            if not finished_klines:
                # 获取到的都是未完成的（可能是最新的），结束同步
                break
            
            # 保存到数据库
            synced = self.save_klines_to_db(finished_klines)
            total_synced += synced
            
            # 更新下一批的开始时间
            last_kline_time = finished_klines[-1]['open_time']
            next_start_time = last_kline_time + timedelta(minutes=1)
            
            # 如果 API 返回的数据跳跃了，取 max 以确保进度向前
            if next_start_time > current_start:
                current_start = next_start_time
            else:
                 # 防止死循环：如果返回的数据都在 current_start 之前（异常情况），强制推进
                current_start = request_end_time
            
            # 只有当确实到了总结束时间才停止，不能因为单次返回少于1000就停止
            if current_start >= end_time:
                break
            
            # 避免请求过快
            time.sleep(0.1)
        
        logger.info(f"历史K线同步完成，共同步 {total_synced} 条")
        logger.info("=" * 50)
        
        return total_synced
    
    def parse_ws_kline(self, data: Dict) -> Optional[Dict[str, Any]]:
        """
        解析WebSocket推送的K线数据
        
        Args:
            data: WebSocket消息数据
            
        Returns:
            解析后的K线字典，或None
        """
        try:
            if 'k' not in data:
                return None
            
            k = data['k']
            
            # 解析时间戳
            open_time_utc = datetime.fromtimestamp(k['t'] / 1000, tz=timezone.utc)
            close_time_utc = datetime.fromtimestamp(k['T'] / 1000, tz=timezone.utc)
            
            return {
                'symbol': k['s'],
                'interval': k['i'],
                'open_time': open_time_utc,
                'open': float(k['o']),
                'high': float(k['h']),
                'low': float(k['l']),
                'close': float(k['c']),
                'volume': float(k['v']),
                'close_time': close_time_utc,
                'quote_asset_volume': float(k['q']),
                'number_of_trades': int(k['n']),
                'taker_buy_base': float(k['V']),
                'taker_buy_quote': float(k['Q']),
                'is_closed': k['x'],  # 是否已完成
            }
            
        except Exception as e:
            logger.error(f"解析WebSocket K线数据失败: {e}")
            return None
    
    async def websocket_handler(self):
        """WebSocket处理器 - 实时订阅K线数据"""
        if not WEBSOCKETS_AVAILABLE:
            logger.error("websockets库未安装，无法使用WebSocket功能")
            return
        
        reconnect_delay = 5  # 重连延迟秒数
        max_reconnect_delay = 60  # 最大重连延迟
        
        while self.running:
            try:
                logger.info(f"连接WebSocket: {self.ws_url}")
                
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    logger.info("✓ WebSocket连接成功")
                    reconnect_delay = 5  # 连接成功后重置延迟
                    
                    while self.running:
                        try:
                            # 等待消息
                            message = await asyncio.wait_for(
                                ws.recv(),
                                timeout=30  # 30秒超时
                            )
                            
                            # 解析消息
                            data = json.loads(message)
                            
                            # 解析K线
                            kline = self.parse_ws_kline(data)
                            
                            if kline:
                                # 只保存已完成的K线
                                if kline['is_closed']:
                                    # 检查数据连续性，如果断档则补齐
                                    last_db_time = self.get_last_kline_time()
                                    if last_db_time:
                                        time_diff = kline['open_time'] - last_db_time
                                        # 如果间隔超过1分钟（即不是连续的下一分钟数据）
                                        if time_diff > timedelta(minutes=1):
                                            logger.warning(f"检测到数据中断! DB最后时间: {last_db_time}, 当前推送时间: {kline['open_time']}, 触发自动补齐...")
                                            # 调用REST API补齐数据
                                            # 注意：sync_historical_klines是同步阻塞的，但补齐少量数据很快
                                            self.sync_historical_klines()
                                    
                                    logger.info(
                                        f"收到已完成K线: {kline['open_time']} "
                                        f"O:{kline['open']:.1f} H:{kline['high']:.1f} "
                                        f"L:{kline['low']:.1f} C:{kline['close']:.1f}"
                                    )
                                    
                                    # 移除is_closed字段后保存
                                    del kline['is_closed']
                                    self.save_klines_to_db([kline])
                                else:
                                    # 实时K线更新（未完成）
                                    logger.debug(
                                        f"实时K线: {kline['open_time']} "
                                        f"C:{kline['close']:.1f} V:{kline['volume']:.0f}"
                                    )
                                    
                        except asyncio.TimeoutError:
                            # 超时，发送ping保持连接
                            logger.debug("发送ping保持连接...")
                            continue
                            
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"WebSocket连接关闭: {e}")
                if self.running:
                    logger.info(f"{reconnect_delay}秒后重连...")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                    
            except Exception as e:
                logger.error(f"WebSocket错误: {e}")
                if self.running:
                    logger.info(f"{reconnect_delay}秒后重连...")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
    
    def stop(self):
        """停止同步"""
        logger.info("正在停止...")
        self.running = False
    
    async def run_async(self):
        """异步运行主循环"""
        self.running = True
        
        # 1. 先同步历史数据
        self.sync_historical_klines()
        
        # 2. 启动WebSocket实时监控
        logger.info("启动WebSocket实时监控...")
        await self.websocket_handler()
    
    def run(self):
        """运行同步器"""
        # 设置信号处理
        def signal_handler(signum, frame):
            self.stop()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            asyncio.run(self.run_async())
        except KeyboardInterrupt:
            logger.info("用户中断")
        finally:
            logger.info("同步器已停止")


def main():
    """主函数"""
    print("=" * 60)
    print("实时K线同步器")
    print("=" * 60)
    print(f"交易对: {config.SYMBOL}")
    print(f"数据库: {config.DB_PATH}")
    print(f"测试网: {'是' if config.BINANCE_TESTNET else '否'}")
    print("=" * 60)
    
    if not WEBSOCKETS_AVAILABLE:
        print("\n错误: 请先安装 websockets 库")
        print("运行: pip install websockets")
        sys.exit(1)
    
    sync = RealtimeKlineSync()
    sync.run()


if __name__ == '__main__':
    # 确保logger不向 root 传播，以防第三方库(如websockets/binance)配置了stderr handler
    # 从而导致 debug 日志泄漏到 error.log
    logger.propagate = False
    main()
