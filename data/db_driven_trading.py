#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据驱动模拟盘交易系统

功能：
1. 启动时预加载 klines_1m_macd_smooth_ma 表最后1000条数据
2. 监控数据表，有新数据时执行交易逻辑
3. 使用币安BTCUSDT永续合约测试网接口进行交易

使用方法：
    python data/db_driven_trading.py
    
环境变量：
    BINANCE_TESTNET=1              # 使用测试网
    BINANCE_API_KEY=xxx            # API Key
    BINANCE_API_SECRET=xxx         # API Secret
    DB_URI=sqlite:///data/klines.db  # 数据库路径
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import create_engine, text

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import config
from core.logger import get_logger
from exchange_layer import ExchangeType, create_exchange
from signal_module.signal_calculator import SignalCalculator
from trade_module.trade_engine import TradeEngine
from interaction_module.feishu_bot import FeishuBot

logger = get_logger('data.db_driven_trading')

# 监控间隔（秒）
POLL_INTERVAL = 1.0
# 预加载数据条数
PRELOAD_COUNT = 1000
# 余额同步间隔（秒）
BALANCE_SYNC_INTERVAL = 60


class DBDrivenTrader:
    """数据驱动交易器"""
    
    def __init__(self, use_testnet: bool = True):
        """
        初始化交易器
        
        Args:
            use_testnet: 是否使用测试网
        """
        self.logger = logger
        self.use_testnet = use_testnet
        
        # 数据库引擎
        self.engine = self._get_engine()
        
        # 最后处理的数据时间
        self.last_processed_time: Optional[str] = None
        
        # 价格历史（用于信号计算）
        self.price_history: List[float] = []
        self.max_price_history = 100
        
        # 前一行数据（用于信号计算）
        self.prev_row: Optional[Dict] = None
        
        # 初始化信号计算器
        self.signal_calculator = SignalCalculator()
        
        # 初始化交易引擎（会自动根据配置选择交易所）
        self._init_exchange()
        self.trade_engine = TradeEngine()

        # 飞书通知机器人
        self.feishu_bot = FeishuBot()

        self.logger.info("=" * 60)
        self.logger.info("数据驱动交易器初始化完成")
        self.logger.info(f"使用测试网: {self.use_testnet}")
        self.logger.info(f"交易对: {config.SYMBOL}")
        self.logger.info("=" * 60)

        # 发送系统启动通知
        try:
            mode_str = "测试网" if self.use_testnet else "实盘"
            exchange_type = os.environ.get('EXCHANGE_TYPE', 'binance_testnet' if self.use_testnet else 'binance_live')
            self.feishu_bot.send_system_startup_notification(
                system_name="数据驱动交易系统",
                mode=mode_str,
                symbol=config.SYMBOL,
                exchange_type=exchange_type
            )
        except Exception as e:
            self.logger.warning(f"飞书启动通知发送失败: {e}")
    
    def _get_engine(self):
        """获取数据库引擎"""
        db_uri = os.environ.get("DB_URI") or "sqlite:///data/klines.db"
        return create_engine(db_uri)
    
    def _init_exchange(self):
        """初始化交易所连接"""
        # 设置环境变量以使用测试网或实盘
        if self.use_testnet:
            os.environ['BINANCE_TESTNET'] = '1'
            os.environ['EXCHANGE_TYPE'] = 'binance_testnet'
        else:
            os.environ['BINANCE_TESTNET'] = '0'
            os.environ['EXCHANGE_TYPE'] = 'binance_live'
        # 无论测试网还是实盘，都关闭回测模式
        os.environ['DB_SIM_MODE'] = '0'
        os.environ['REPLAY_MODE'] = '0'

        # 环境变量修改后需要刷新 config，否则 TradeEngine 会继续读取默认回测配置
        try:
            config._load_env()  # noqa: SLF001 — 内部刷新以应用最新环境变量
            self.logger.info("已刷新配置，交易所将按最新环境变量选择")
        except Exception as e:  # pragma: no cover - 防御性日志
            self.logger.warning(f"刷新配置失败: {e}")

        # 调试：打印配置值
        self.logger.info(f"=== 配置调试 ===")
        self.logger.info(f"  EXCHANGE_TYPE: {config.EXCHANGE_TYPE}")
        self.logger.info(f"  BINANCE_TESTNET: {config.BINANCE_TESTNET}")
        self.logger.info(f"  DB_SIM_MODE: {config.DB_SIM_MODE}")
        self.logger.info(f"  REPLAY_MODE: {config.REPLAY_MODE}")
        self.logger.info(f"  os.EXCHANGE_TYPE: {os.environ.get('EXCHANGE_TYPE', 'None')}")
        self.logger.info(f"  use_testnet: {self.use_testnet}")
        self.logger.info(f"==================")
        
        # 余额同步相关
        self.last_balance_sync = 0  # 上次同步时间戳
        self.current_balance = 0.0  # 当前BTC余额
        self.available_balance = 0.0  # 可用余额
        self.unrealized_pnl = 0.0  # 未实现盈亏
    
    def sync_balance(self):
        """
        从交易所同步BTC余额
        
        币本位合约使用BTC作为保证金
        """
        try:
            # 获取账户信息
            account_info = self.trade_engine.exchange.get_account_info()
            
            self.current_balance = account_info.total_wallet_balance
            self.available_balance = account_info.available_balance
            self.unrealized_pnl = account_info.unrealized_pnl
            
            # 更新交易引擎的资金
            self.trade_engine.realized_pnl = self.current_balance
            
            self.logger.info(
                f"💰 余额同步 | "
                f"总余额: {self.current_balance:.6f} BTC | "
                f"可用: {self.available_balance:.6f} BTC | "
                f"未实现盈亏: {self.unrealized_pnl:.6f} BTC"
            )
            
            self.last_balance_sync = time.time()
            return True
            
        except Exception as e:
            self.logger.error(f"余额同步失败: {e}")
            return False
    
    def _should_sync_balance(self) -> bool:
        """检查是否需要同步余额"""
        return time.time() - self.last_balance_sync >= BALANCE_SYNC_INTERVAL
    
    def preload_data(self) -> pd.DataFrame:
        """
        预加载最后N条数据用于初始化信号计算器
        
        Returns:
            DataFrame: 预加载的数据
        """
        self.logger.info(f"预加载最后 {PRELOAD_COUNT} 条数据...")
        
        with self.engine.connect() as conn:
            query = text(f"""
                SELECT * FROM klines_1m_macd_smooth_ma
                ORDER BY open_time DESC
                LIMIT {PRELOAD_COUNT}
            """)
            df = pd.read_sql(query, conn)
        
        if df.empty:
            self.logger.warning("没有找到预加载数据")
            return df
        
        # 按时间升序排列
        df = df.sort_values('open_time').reset_index(drop=True)
        
        self.logger.info(f"预加载了 {len(df)} 条数据")
        self.logger.info(f"  时间范围: {df['open_time'].iloc[0]} ~ {df['open_time'].iloc[-1]}")
        
        # 记录最后处理的时间（直接使用数据库中的原始格式）
        last_time_raw = df['open_time'].iloc[-1]
        # 直接转换为字符串，保持数据库格式
        self.last_processed_time = str(last_time_raw).replace('T', ' ')[:19]
        
        self.logger.info(f"  最后处理时间（标准化）: {self.last_processed_time}")
        
        # 预热信号计算器（更新移动平均值）
        self.logger.info("预热信号计算器...")
        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            # 只更新移动平均值，不生成信号
            self._warm_up_signal_calculator(row_dict)
            
            # 更新价格历史
            close_price = row_dict.get('close', 0)
            if close_price > 0:
                self.price_history.append(close_price)
                if len(self.price_history) > self.max_price_history:
                    self.price_history.pop(0)
            
            self.prev_row = row_dict
        
        self.logger.info("✓ 预热完成")
        return df
    
    def _warm_up_signal_calculator(self, row: Dict):
        """预热信号计算器（只更新移动平均值）"""
        ts = pd.to_datetime(row.get('open_time'))
        
        # 更新各个指标的移动平均值
        tracker = self.signal_calculator.time_rolling_tracker
        
        # 15分钟指标
        tracker.update('macd15m', ts, row.get('macd15m', 0))
        tracker.update('dif15m', ts, row.get('dif15m', 0))
        tracker.update('dea15m', ts, row.get('dea15m', 0))
        tracker.update('macd15m_2', ts, row.get('macd15m', 0))
        tracker.update('dif15m_2', ts, row.get('dif15m', 0))
        tracker.update('dea15m_2', ts, row.get('dea15m', 0))
        
        # 1小时指标
        tracker.update('macd1h', ts, row.get('macd1h', 0))
        tracker.update('dif1h', ts, row.get('dif1h', 0))
        tracker.update('dea1h', ts, row.get('dea1h', 0))
        tracker.update('macd1h_2', ts, row.get('macd1h', 0))
        tracker.update('dif1h_2', ts, row.get('dif1h', 0))
        tracker.update('dea1h_2', ts, row.get('dea1h', 0))
        
        # 4小时指标
        tracker.update('macd4h', ts, row.get('macd4h', 0))
        tracker.update('dif4h', ts, row.get('dif4h', 0))
        tracker.update('dea4h', ts, row.get('dea4h', 0))
        tracker.update('macd4h_2', ts, row.get('macd4h', 0))
        tracker.update('dif4h_2', ts, row.get('dif4h', 0))
        tracker.update('dea4h_2', ts, row.get('dea4h', 0))
        
        # 1天指标
        tracker.update('macd1d', ts, row.get('macd1d', 0))
        tracker.update('dif1d', ts, row.get('dif1d', 0))
        tracker.update('dea1d', ts, row.get('dea1d', 0))
        tracker.update('macd1d_2', ts, row.get('macd1d', 0))
        tracker.update('dif1d_2', ts, row.get('dif1d', 0))
        tracker.update('dea1d_2', ts, row.get('dea1d', 0))
    
    def get_new_data(self) -> List[Dict]:
        """
        获取新数据
        
        Returns:
            List[Dict]: 新数据列表
        """
        if self.last_processed_time is None:
            return []
        
        with self.engine.connect() as conn:
            # 直接使用保存的时间字符串（已经是数据库格式）
            last_time = self.last_processed_time
            
            # 调试：打印查询条件
            # self.logger.debug(f"查询条件: open_time > '{last_time}'")
            
            query = text("""
                SELECT * FROM klines_1m_macd_smooth_ma
                WHERE open_time > :last_time
                ORDER BY open_time ASC
            """)
            result = conn.execute(query, {"last_time": last_time+"+00:00"})
            rows = result.fetchall()
            columns = result.keys()
            
            # 调试：打印查询结果数量
            if rows:
                self.logger.debug(f"查询到 {len(rows)} 条新数据")
        
        if not rows:
            return []
        
        # 转换为字典列表
        new_data = []
        for row in rows:
            row_dict = dict(zip(columns, row))
            new_data.append(row_dict)
        
        return new_data
    
    def process_new_data(self, row: Dict):
        """
        处理新数据，执行交易逻辑
        
        使用 TradeEngine.process_tick() 来处理完整的交易逻辑，
        包括开仓、止盈、止损、回撤等。
        
        Args:
            row: 新的K线数据（含指标）
        """
        open_time = row.get('open_time')
        close_price = row.get('close', 0)
        
        self.logger.info(f"[{open_time}] 处理新数据 | 收盘价={close_price:.2f}")
        
        # 更新价格历史
        if close_price > 0:
            self.price_history.append(close_price)
            if len(self.price_history) > self.max_price_history:
                self.price_history.pop(0)
        
        # 将价格历史转换为 pandas Series（signal_calculator 需要 .iloc 方法）
        state_prices_series = pd.Series(self.price_history) if self.price_history else None
        
        # 计算开仓信号
        signal = self.signal_calculator.calculate_open_signal(
            indicators=row,
            row_prev=self.prev_row,
            state_prices=state_prices_series
        )
        
        if signal:
            self.logger.info(f"🎯 检测到{signal.side}信号: {signal.reason}")
            if signal.details:
                self.logger.info(f"   详情: {signal.details}")
        
        # 使用 TradeEngine.process_tick() 处理完整的交易逻辑
        # 包括：开仓、止盈、止损、回撤、超时检查
        self.trade_engine.process_tick(
            ts=pd.to_datetime(open_time),
            row=row,
            signal=signal
        )
        
        # 更新前一行数据
        self.prev_row = row
        # 保存时间，直接使用原始格式并标准化
        self.last_processed_time = str(open_time).replace('T', ' ')[:19]
        self.logger.debug(f"更新 last_processed_time = {self.last_processed_time}")
    
    def run(self):
        """运行交易循环"""
        self.logger.info("=" * 60)
        self.logger.info("启动数据驱动交易系统")
        self.logger.info(f"启动时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
        self.logger.info("=" * 60)
        
        # 预加载数据
        self.preload_data()
        
        # 首次同步余额
        self.logger.info("同步交易所余额...")
        self.sync_balance()
        
        self.logger.info("开始监控数据库...")
        self.logger.info(f"最后处理时间: {self.last_processed_time}")
        self.logger.info("按 Ctrl+C 停止")
        
        try:
            while True:
                # 获取新数据
                new_data = self.get_new_data()
                
                if new_data:
                    self.logger.info(f"发现 {len(new_data)} 条新数据")
                    for row in new_data:
                        self.process_new_data(row)
                
                # 定时同步余额
                if self._should_sync_balance():
                    self.sync_balance()
                
                # 等待下一次轮询
                time.sleep(POLL_INTERVAL)
                
        except KeyboardInterrupt:
            self.logger.info("\n停止交易系统")
            self._print_summary()
    
    def _print_summary(self):
        """打印交易统计"""
        self.logger.info("=" * 60)
        self.logger.info("交易统计")
        self.logger.info("=" * 60)
        
        # 持仓统计
        self.logger.info(f"当前持仓: {len(self.trade_engine.positions)}")
        for pos in self.trade_engine.positions:
            self.logger.info(f"  - {pos.side} | 入场={pos.entry_price:.2f} | 数量={pos.contracts}")
        
        # 交易记录
        self.logger.info(f"总交易次数: {len(self.trade_engine.trades)}")
        
        # 盈亏统计
        total_pnl = sum(t.net_pnl for t in self.trade_engine.trades)
        self.logger.info(f"总盈亏: {total_pnl:.6f} BTC")
        
        # 最终余额
        self.sync_balance()
        self.logger.info(f"最终余额: {self.current_balance:.6f} BTC")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="数据驱动模拟盘交易系统")
    parser.add_argument(
        "--live",
        action="store_true",
        help="使用实盘（默认使用测试网）"
    )
    parser.add_argument(
        "--preload",
        type=int,
        default=1000,
        help="预加载数据条数（默认1000）"
    )
    args = parser.parse_args()
    
    global PRELOAD_COUNT
    PRELOAD_COUNT = args.preload
    
    # 创建交易器
    trader = DBDrivenTrader(use_testnet=not args.live)
    
    # 运行
    trader.run()


if __name__ == "__main__":
    main()
