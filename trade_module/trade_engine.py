#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易引擎 - 核心交易逻辑
包含: 开仓、平仓、止盈、止损、回撤、超时等完整逻辑

开仓流程:
1. 检查资金和风控
2. 通过Exchange接口下单
3. 检测订单状态（FILLED/EXPIRED/REJECTED）
4. 成功 -> 进入持仓
5. 失败 -> 作废本地订单，继续寻找信号
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from core.config import config
from core.logger import get_logger
# 新增: 导入Exchange接口
from exchange_layer import ExchangeType, create_exchange
# 飞书通知
from interaction_module.feishu_bot import FeishuBot
from trade_module.account_tracker import AccountTracker
from trade_module.local_order import LocalOrderManager
from trade_module.local_order import Order as LocalOrder
# 导入交易记录器
from core.trade_recorder import get_trade_recorder, TradeRecord, PositionRecord


@dataclass
class Position:
    """持仓信息"""
    id: str
    side: str  # 'long' or 'short'
    entry_price: float
    entry_time: pd.Timestamp
    contracts: int
    entry_contracts: int
    contract_size_btc: float
    tp_hit: List[float] = field(default_factory=list)
    tp_activated: bool = False
    tp_hit_value: float = 0.0
    trace_id: str = ""
    benchmark_price: Optional[float] = None
    up_once: bool = False

    # 入场时的指标值
    entry_hist4: Optional[float] = None
    entry_dif4: Optional[float] = None
    entry_hist1h: Optional[float] = None
    entry_hist15: Optional[float] = None

    # 新增: 止损单追踪
    sl_triggered: bool = False  # 止损是否被触发
    sl_order_id: Optional[str] = None  # 当前止损单ID
    sl_order_attempts: int = 0  # 止损单尝试次数
    sl_order_last_time: Optional[pd.Timestamp] = None  # 最后一次挂止损单时间

    # 新增: 止盈单追踪
    tp_order_id: Optional[str] = None  # 当前止盈单ID
    tp_order_level: int = 0  # 当前止盈单级别 (0表示未挂单)
    tp_order_contracts: int = 0  # 当前止盈单数量

    # 新增: 止盈回撤追踪 (新策略)
    tp_level_reached: int = 0  # 已达到的止盈级别 (1-N，0表示未触发)
    tp_confirmed_price: Optional[float] = None  # 确认的止盈价格（分钟收盘价确认）
    tp_drawdown_price: Optional[float] = None  # 止盈回撤触发价格
    tp_highest_price: Optional[float] = None  # 止盈后的最高价（多头）/最低价（空头）


@dataclass
class Trade:
    """交易记录"""
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    side: str
    entry_price: float
    exit_price: float
    qty: int
    gross_pnl: float
    net_pnl: float
    reason: str
    trace_id: str


class TradeEngine:
    """交易引擎 - 处理开仓、平仓、止盈、止损等核心逻辑"""

    @staticmethod
    def _resolve_display_asset(symbol: str) -> str:
        """从交易对中提取用于显示/余额查询的基础币种，例如 ETHUSD_PERP -> ETH。"""
        symbol_upper = (symbol or '').upper()
        if not symbol_upper:
            return 'BTC'

        # 先去掉常见后缀（如 _PERP），再按常见计价币后缀裁剪
        symbol_main = symbol_upper.split('_', 1)[0]
        for quote_suffix in ('USDT', 'USDC', 'BUSD', 'FDUSD', 'TUSD', 'USD'):
            if symbol_main.endswith(quote_suffix) and len(symbol_main) > len(quote_suffix):
                return symbol_main[:-len(quote_suffix)]

        return symbol_main

    def __init__(self, exchange=None):
        self.logger = get_logger('trade_module.engine')
        self.order_manager = LocalOrderManager()
        self.account_tracker = AccountTracker()
        # 飞书通知机器人
        self.feishu_bot = FeishuBot()

        # 新增: 创建Exchange实例，支持外部注入
        self.exchange = exchange or create_exchange()
        if not getattr(self.exchange, 'connected', False):
            self.exchange.connect()

        # 持仓和交易记录
        self.positions: List[Position] = []
        self.trades: List[Trade] = []
        self.logs: List[tuple] = []

        # 交易记录器（持久化到数据库）
        self.trade_recorder = get_trade_recorder()

        # 账户状态
        self.initial_capital = config.POSITION_BTC
        self.realized_pnl = self.initial_capital
        self.cached_total_balance = self.initial_capital  # 缓存的交易所账户总余额（由定时同步更新）
        self.display_asset = self._resolve_display_asset(getattr(config, 'SYMBOL', ''))

        # 统计数据
        self.signals_count = 0
        self.triggers_count = 0
        self.processed_count = 0  # 已处理的K线数量

        # 资金锁定（挂单占用的可用资金）
        self.locked_capital = 0.0

        # 订单统计
        self.order_success_count = 0
        self.order_failed_count = 0

        # 止损冷却
        self.stoploss_time = None  # 最后止损时间
        self.stoploss_side = None  # 最后止损方向

        # 远端订单巡检
        self.order_sync_interval = getattr(config, 'ORDER_SYNC_INTERVAL', 120)
        self.order_sync_log_limit = getattr(config, 'ORDER_SYNC_LOG_LIMIT', 5)
        self.last_order_sync: Optional[pd.Timestamp] = None

        # 后台订单巡检线程，避免依赖主循环
        self._order_sync_stop_event = threading.Event()
        self._order_sync_thread = None
        if self.order_sync_interval > 0:
            self._order_sync_thread = threading.Thread(
                target=self._order_sync_loop,
                name="order-sync-thread",
                daemon=True,
            )
            self._order_sync_thread.start()
            self.logger.info(
                f"后台订单巡检线程已启动，每 {self.order_sync_interval}s 执行一次"
            )

        # 交易历史报告定时发送
        self.trade_history_report_interval = getattr(config, 'TRADE_HISTORY_REPORT_INTERVAL', 0)
        self.trade_history_report_count = getattr(config, 'TRADE_HISTORY_REPORT_COUNT', 10)
        self.last_trade_history_report: Optional[pd.Timestamp] = None
        self._trade_report_stop_event = threading.Event()
        self._trade_report_thread = None
        if self.trade_history_report_interval > 0:
            self._trade_report_thread = threading.Thread(
                target=self._trade_report_loop,
                name="trade-report-thread",
                daemon=True,
            )
            self._trade_report_thread.start()
            self.logger.info(
                f"交易历史报告线程已启动，每 {self.trade_history_report_interval} 分钟发送一次"
            )

        self.logger.info("=" * 60)
        self.logger.info("交易引擎初始化完成")
        self.logger.info(f"初始资金: {self.initial_capital} {self.display_asset}")
        self.logger.info(f"合约名义价值: ${config.CONTRACT_NOTIONAL}")
        self.logger.info("=" * 60)

    def record_log(self, time_val, event, side, price_val, contracts_val,
                   pnl_val, details_val, fee_rate_val=None, fee_usd_val=None):
        """记录日志"""
        log_entry = (
            time_val, event, side, price_val, contracts_val,
            pnl_val, details_val, fee_rate_val, fee_usd_val,
            self.positions[0].trace_id if self.positions else None,
            self.realized_pnl
        )
        self.logs.append(log_entry)

        self.logger.info(
            f"{event} {side} | "
            f"价格={price_val:.2f} | "
            f"数量={contracts_val} | "
            f"盈亏={pnl_val:.6f} {self.display_asset} | "
            f"{details_val}"
        )

    # ------------------ 外部触发开仓 ------------------

    # ------------------ 远端订单巡检与反向同步 ------------------
    def sync_positions_from_exchange(self, ts: pd.Timestamp, price: float) -> bool:
        """
        从交易所同步持仓到本地，以交易所为准（单向持仓模式）
        
        返回:
            bool: 是否有变化
        """
        try:
            pos_info = self.exchange.get_position(config.SYMBOL)
        except Exception as fetch_err:
            self.logger.warning(f"同步持仓失败(get_position): {fetch_err}")
            return False
            
        # 解析交易所持仓
        remote_amt = float(pos_info.get('position_amount', 0)) if pos_info else 0
        
        # 交易所无持仓
        if remote_amt == 0:
            if self.positions:
                old_positions = [(p.side, p.entry_price, p.contracts) for p in self.positions]
                self.logger.warning(
                    f"🔄 持仓同步: 交易所无持仓，清除本地持仓 | "
                    f"清除: {old_positions}"
                )
                self.positions.clear()
                return True
            return False
        
        # 交易所有持仓
        remote_side = 'long' if remote_amt > 0 else 'short'
        remote_contracts = abs(int(remote_amt))
        remote_entry = float(pos_info.get('entry_price', 0)) or price
        
        # 检查本地持仓是否与交易所一致
        if len(self.positions) == 1:
            local_pos = self.positions[0]
            if (local_pos.side == remote_side and 
                local_pos.contracts == remote_contracts and
                abs(local_pos.entry_price - remote_entry) < 0.01):
                # 完全一致，无需处理
                return False
        
        # 不一致，用交易所持仓替换本地
        old_positions = [(p.side, p.entry_price, p.contracts) for p in self.positions]
        
        # 清空本地
        self.positions.clear()
        
        # 从交易所创建新的本地持仓
        cn = config.CONTRACT_NOTIONAL
        qty_per_contract = cn / remote_entry if remote_entry > 0 else 0
        trace_id = str(uuid.uuid4())
        
        new_pos = Position(
            id=str(uuid.uuid4()),
            side=remote_side,
            entry_price=remote_entry,
            entry_time=ts,
            contracts=remote_contracts,
            entry_contracts=remote_contracts,
            contract_size_btc=qty_per_contract,
            tp_hit=[],
            tp_activated=False,
            tp_hit_value=0.0,
            trace_id=trace_id,
            benchmark_price=remote_entry,
            entry_hist4=None,
            entry_dif4=None,
            entry_hist1h=None,
            entry_hist15=None,
        )
        
        self.positions.append(new_pos)
        
        self.logger.warning(
            f"🔄 持仓同步: 本地与交易所不一致，已同步 | "
            f"交易所: {remote_side}@{remote_entry:.2f} x{remote_contracts} | "
            f"原本地: {old_positions}"
        )
        return True

    def _maybe_sync_remote_orders(self, ts: pd.Timestamp, price: float):
        """定期从交易所拉取订单与持仓，补充本地状态"""
        if self.order_sync_interval <= 0:
            return

        if self.last_order_sync is not None:
            # 统一转为 tz-naive 避免 tz-aware 与 tz-naive 相减报错
            ts_naive = ts.tz_localize(None) if ts.tzinfo is not None else ts
            last_naive = self.last_order_sync.tz_localize(None) if self.last_order_sync.tzinfo is not None else self.last_order_sync
            delta_sec = (ts_naive - last_naive).total_seconds()
            if delta_sec < self.order_sync_interval:
                return

        try:
            open_orders = []
            try:
                open_orders = self.exchange.get_open_orders(config.SYMBOL)
            except Exception as fetch_err:
                self.logger.warning(f"订单巡检失败(get_open_orders): {fetch_err}")

            # 打印部分挂单便于观察
            if open_orders:
                self.logger.info("🔍 挂单巡检 | 总数=%s", len(open_orders))
                for idx, od in enumerate(open_orders[: self.order_sync_log_limit]):
                    self.logger.info(
                        "  #%s id=%s side=%s type=%s status=%s price=%.4f qty=%.4f filled=%.4f",
                        idx + 1,
                        getattr(od, 'order_id', ''),
                        getattr(getattr(od, 'side', None), 'value', getattr(od, 'side', '')),
                        getattr(getattr(od, 'type', None), 'value', getattr(od, 'type', '')),
                        getattr(getattr(od, 'status', None), 'value', getattr(od, 'status', '')),
                        getattr(od, 'price', 0.0) or 0.0,
                        getattr(od, 'quantity', 0.0) or 0.0,
                        getattr(od, 'filled_quantity', 0.0) or 0.0,
                    )

            # 同步持仓已在 process_tick 开头完成，这里不再重复调用
            # 同步可能由其它渠道平仓的情况（已在 sync_positions_from_exchange 中处理）
            # try:
            #     self.sync_external_fills()
            # except Exception as e:
            #     self.logger.warning(f"同步外部成交时出错: {e}")

        except Exception as e:  # 防御性日志，避免中断主流程
            self.logger.warning(f"订单巡检异常: {e}", exc_info=True)
        finally:
            self.last_order_sync = ts

    def _order_sync_loop(self):
        """后台线程：不依赖主循环的订单巡检"""
        # 使用 Event.wait 便于快速退出
        interval = max(1, int(self.order_sync_interval))
        while not self._order_sync_stop_event.is_set():
            try:
                ts = pd.Timestamp.utcnow()
                # price 在反向同步中仅作备用，实时价缺失时可为0
                self._maybe_sync_remote_orders(ts, price=0.0)
            except Exception as e:
                self.logger.warning(f"后台订单巡检异常: {e}", exc_info=True)
            self._order_sync_stop_event.wait(interval)

    def stop(self):
        """停止后台线程"""
        # 停止订单巡检线程
        if not self._order_sync_stop_event.is_set():
            self._order_sync_stop_event.set()
        if self._order_sync_thread and self._order_sync_thread.is_alive():
            self._order_sync_thread.join(timeout=2)
        # 停止交易报告线程
        if not self._trade_report_stop_event.is_set():
            self._trade_report_stop_event.set()
        if self._trade_report_thread and self._trade_report_thread.is_alive():
            self._trade_report_thread.join(timeout=2)

    def _trade_report_loop(self):
        """后台线程：定时发送交易历史报告"""
        interval_seconds = max(60, int(self.trade_history_report_interval * 60))
        # 首次启动时先等待一个周期，避免与启动时的显式调用重复
        self._trade_report_stop_event.wait(interval_seconds)
        while not self._trade_report_stop_event.is_set():
            try:
                self._send_trade_history_report()
            except Exception as e:
                self.logger.warning(f"发送交易历史报告异常: {e}", exc_info=True)
            self._trade_report_stop_event.wait(interval_seconds)

    def _send_trade_history_report(self):
        """发送交易历史报告到飞书"""
        self.logger.info("=" * 60)
        self.logger.info("📊 [交易历史报告] 开始生成...")
        self.logger.info(f"   内存中交易记录数: {len(self.trades)}")
        self.logger.info(f"   报告显示条数配置: {self.trade_history_report_count}")
        
        trade_list = []
        
        # 优先使用内存中的交易记录
        if False:
            self.logger.info("   使用内存中的交易记录")
            # 获取最近N笔交易
            report_count = self.trade_history_report_count
            recent_trades = self.trades[-report_count:] if len(self.trades) > report_count else self.trades

            # 转换为飞书报告需要的格式
            for trade in recent_trades:
                # 计算手续费（从 gross_pnl 和 net_pnl 推算）
                gross_pnl_btc = trade.gross_pnl / trade.exit_price if trade.exit_price else 0
                net_pnl_btc = trade.net_pnl / trade.exit_price if trade.exit_price else 0
                fee_btc = gross_pnl_btc - net_pnl_btc

                trade_list.append({
                    'exit_time': trade.exit_time,
                    'side': trade.side,
                    'entry_price': trade.entry_price,
                    'exit_price': trade.exit_price,
                    'net_pnl_btc': net_pnl_btc,
                    'fee_btc': fee_btc
                })
        else:
            # 内存中没有交易记录，尝试从交易所 API 获取
            self.logger.info("   内存中无交易记录，从交易所获取历史成交...")
            try:
                # 获取更多记录以便配对开仓和平仓
                trades_from_api = self.exchange.get_user_trades(
                    config.SYMBOL, limit=200
                )
                self.logger.info(
                    f"   交易所返回成交记录数: "
                    f"{len(trades_from_api) if trades_from_api else 0}"
                )
                
                if trades_from_api:
                    from collections import defaultdict

                    # 按订单ID分组
                    grouped = defaultdict(list)
                    for t in trades_from_api:
                        grouped[t.get('orderId')].append(t)
                    
                    # 汇总每个订单的信息
                    order_summaries = []
                    for order_id, order_trades in grouped.items():
                        total_pnl = sum(
                            float(t.get('realizedPnl', 0) or 0)
                            for t in order_trades
                        )
                        total_fee = sum(
                            float(t.get('commission', 0) or 0)
                            for t in order_trades
                        )
                        total_qty = sum(
                            float(t.get('qty', 0) or 0)
                            for t in order_trades
                        )
                        first_trade = order_trades[0]
                        trade_side = first_trade.get('side')  # BUY or SELL
                        avg_price = float(first_trade.get('price', 0) or 0)
                        trade_time = first_trade.get('time', 0)
                        
                        order_summaries.append({
                            'order_id': order_id,
                            'time': trade_time,
                            'trade_side': trade_side,
                            'price': avg_price,
                            'qty': total_qty,
                            'pnl': total_pnl,
                            'fee': total_fee,
                            'is_close': abs(total_pnl) > 0
                        })
                    
                    # 按时间排序（早到晚）
                    order_summaries.sort(key=lambda x: x['time'])
                    
                    # 分离开仓和平仓订单
                    # 开仓: BUY开多(pnl=0), SELL开空(pnl=0)
                    # 平仓: SELL平多(pnl!=0), BUY平空(pnl!=0)
                    long_opens = []   # BUY且pnl=0 -> 开多
                    short_opens = []  # SELL且pnl=0 -> 开空
                    
                    close_orders = []
                    
                    for order in order_summaries:
                        if not order['is_close']:
                            # 开仓订单
                            if order['trade_side'] == 'BUY':
                                long_opens.append(order)
                            else:
                                short_opens.append(order)
                        else:
                            # 平仓订单
                            # SELL平多，找最近的开多订单
                            # BUY平空，找最近的开空订单
                            if order['trade_side'] == 'SELL':
                                position_side = 'long'
                                opens_list = long_opens
                            else:
                                position_side = 'short'
                                opens_list = short_opens
                            
                            # 找该平仓之前最近的开仓
                            entry_price = 0
                            for i in range(len(opens_list) - 1, -1, -1):
                                if opens_list[i]['time'] < order['time']:
                                    entry_price = opens_list[i]['price']
                                    opens_list.pop(i)  # 配对后移除
                                    break
                            
                            exit_time = pd.to_datetime(
                                order['time'], unit='ms'
                            ) if order['time'] else None
                            
                            close_orders.append({
                                'exit_time': exit_time,
                                'side': position_side,
                                'entry_price': entry_price,
                                'exit_price': order['price'],
                                'net_pnl_btc': order['pnl'],
                                'fee_btc': order['fee']
                            })
                    
                    self.logger.info(f"   筛选出平仓订单数: {len(close_orders)}")
                    
                    # 按时间排序，取最近N笔
                    close_orders.sort(key=lambda x: x['exit_time'] or pd.Timestamp.min, reverse=True)
                    trade_list = close_orders[:self.trade_history_report_count]
                    trade_list.reverse()  # 时间正序
                    
                    self.logger.info(f"   最终报告交易数: {len(trade_list)}")
                else:
                    self.logger.info("   交易所返回空记录")
            except Exception as e:
                self.logger.warning(f"   从交易所获取历史成交失败: {e}", exc_info=True)
        
        if not trade_list:
            self.logger.info("   暂无交易记录，跳过报告发送")
            self.logger.info("=" * 60)
            return

        # 输出报告详情到日志
        self.logger.info("-" * 50)
        self.logger.info("📋 交易历史报告详情:")
        for idx, t in enumerate(trade_list, 1):
            exit_time_str = t['exit_time'].strftime('%m-%d %H:%M') \
                if t.get('exit_time') else 'N/A'
            side_str = '多' if t.get('side') == 'long' else '空'
            entry_p = t.get('entry_price', 0)
            exit_p = t.get('exit_price', 0)
            pnl = t.get('net_pnl_btc', 0)
            fee = t.get('fee_btc', 0)
            self.logger.info(
                f"   {idx}. {exit_time_str} | {side_str} | "
                f"{entry_p:.1f}→{exit_p:.1f} | "
                f"{pnl:+.6f} {self.display_asset} | 费:{fee:.6f}"
            )
        self.logger.info("-" * 50)

        # 发送报告
        self.logger.info(f"   准备发送飞书报告，交易数: {len(trade_list)}")
        self.logger.info(
            f"   飞书配置: FEISHU_ENABLED={config.FEISHU_ENABLED}, "
            f"WEBHOOK长度={len(config.FEISHU_WEBHOOK) if config.FEISHU_WEBHOOK else 0}"
        )
        
        # 从交易所API获取真实账户余额
        try:
            account_info = self.exchange.get_account_info(self.display_asset)
            total_balance_eth = account_info.total_wallet_balance
            self.logger.info(f"   交易所账户余额: {total_balance_eth:.8f} {self.display_asset}")
        except Exception as e:
            self.logger.warning(f"   获取交易所余额失败，使用本地记录: {e}")
            total_balance_eth = 1
        
        try:
            result = self.feishu_bot.send_trade_history_report(
                trades=trade_list,
                total_balance_btc=total_balance_eth
            )
            self.last_trade_history_report = pd.Timestamp.utcnow()
            self.logger.info(f"📊 交易历史报告发送结果: {result}")
            self.logger.info("=" * 60)
        except Exception as e:
            self.logger.warning(f"发送交易历史报告失败: {e}", exc_info=True)
            self.logger.info("=" * 60)


        # 新策略：不预先挂止盈单，改为实时监测后再挂单
        # if config.TP_LEVELS:
        #     self._place_initial_tp_order(pos, ts)

    def open_position(self, ts, price: float, row: Dict,
                      side: str, signal_name: str) -> bool:
        """
        开仓（通过Exchange接口下单）

        流程:
        1. 检查资金和风控
        2. 通过Exchange.place_order()下单到交易所
        3. 检测订单状态:
           - FILLED: 成功，创建持仓
           - EXPIRED/REJECTED: 失败，作废本地订单，继续寻找信号
           - NEW: 待成交（限价单可能需要等待）

        Args:
            ts: 开仓时间(pandas.Timestamp, str, or datetime)
            price: 开仓价格
            row: K线数据(包含指标)
            side: 'long' or 'short'
            signal_name: 信号名称

        Returns:
            bool: 是否成功开仓（订单成交）
        """
        # 📊 调试：记录开仓尝试
        ts_str = str(ts)
        debug_mode = '18:42' in ts_str or '19:39' in ts_str or '19:44' in ts_str

        # 始终使用收盘价作为限价挂单价格
        price = row.get('close', price)

        # 🔍 详细日志：记录每次开仓尝试
        self.logger.info("=" * 80)
        self.logger.info(f"🎯 [开仓尝试] 时间={ts_str} | 方向={side} | 价格={price:.2f} | 信号={signal_name}")
        self.logger.info(f"   当前持仓数: {len(self.positions)}")
        for idx, pos in enumerate(self.positions):
            self.logger.info(f"   持仓{idx+1}: {pos.side} | 入场={pos.entry_price:.2f} | 数量={pos.contracts}张")
        self.logger.info(f"   可用资金: {self.realized_pnl:.6f} {self.display_asset}")
        self.logger.info(f"   NO_LIMIT_POS: {config.NO_LIMIT_POS}")
        self.logger.info("=" * 80)

        # 转换时间戳为pandas.Timestamp
        if not isinstance(ts, pd.Timestamp):
            if isinstance(ts, str):
                ts = pd.to_datetime(ts)
            elif isinstance(ts, datetime):
                ts = pd.Timestamp(ts)
            else:
                try:
                    ts = pd.to_datetime(ts)
                except Exception as e:
                    self.logger.error(
                        f"无法转换时间戳: {ts}, 类型: {type(ts)}, 错误: {e}"
                    )
                    return False

        if debug_mode:
            self.logger.info(f"🔍 [开仓尝试] {ts_str} | {side} | 价格={price:.2f} | 信号={signal_name}")

        # 计算可用资金（扣除已锁定部分）
        leverage = max(1.0, float(getattr(config, 'LEVERAGE', 1)))

        if config.NO_LIMIT_POS:
            available_capital = 1.0
            total_balance = 1.0
        else:
            available_capital = max(0.0, self.realized_pnl - self.locked_capital)
            # 使用缓存的账户总余额（由定时同步更新）
            total_balance = self.cached_total_balance

        # 预留账户总余额的2%作为安全垫，避免资金耗尽导致开仓失败
        reserve_ratio = 0.02 if not config.NO_LIMIT_POS else 0.0
        min_reserve = total_balance * reserve_ratio  # 按缓存的账户总余额计算预留
        tradable_capital = max(0.0, available_capital - min_reserve)

        if debug_mode:
            self.logger.info(
                f"💰 [资金检查] 账户总资金={total_balance:.6f} {self.display_asset} | "
                f"可用资金={available_capital:.6f} {self.display_asset} | "
                f"预留={min_reserve:.6f} {self.display_asset} | "
                f"可交易={tradable_capital:.6f} {self.display_asset}"
            )

        if tradable_capital <= 0:
            self.logger.warning(
                f"❌ [{ts_str}] ❌❌❌ 开仓失败: 可交易资金不足 "
                f"(可用={available_capital:.6f} {self.display_asset}, "
                f"预留={min_reserve:.6f} {self.display_asset})，跳过开仓"
            )
            return False

        # 检查止损冷却 - 与macd_refactor.py保持一致
        if self.stoploss_time is not None:
            time_since_stoploss = (ts - self.stoploss_time).total_seconds() / 60
            if time_since_stoploss < config.STOP_LOSS_HOLD_TIME and side == self.stoploss_side:
                msg = (f"❌❌❌ 开仓失败: 跳过开仓 - 距离{side}止损仅{time_since_stoploss:.1f}分钟 "
                       f"(冷却期{config.STOP_LOSS_HOLD_TIME}分钟)")
                if debug_mode:
                    self.logger.warning(f"❌ [{ts_str}] {msg}")
                else:
                    self.logger.info(msg)
                return False

        # 检查价格是否有效
        if not price or price <= 0:
            self.logger.error(
                f"❌❌❌ 开仓失败: [{ts_str}] 开仓价格无效: {price} (type: {type(price).__name__}), "
                f"跳过开仓 | 信号: {signal_name}"
            )
            self.logger.error(
                f"   K线数据: price={row.get('price')}, close={row.get('close')}, "
                f"open={row.get('open')}, high={row.get('high')}, low={row.get('low')}"
            )
            return False

        # 计算合约数量
        cn = config.CONTRACT_NOTIONAL
        max_contracts = int((tradable_capital * price * leverage) / cn)

        if debug_mode:
            self.logger.info(f"📊 [合约计算] 价格={price:.2f} | 面值={cn} | 最大合约数={max_contracts}")

        # 检查是否足够开仓
        insufficient = (
            config.TP_RATIO_PER_LEVEL > 0 and
            max_contracts * config.TP_RATIO_PER_LEVEL <= 1
        )
        if insufficient or max_contracts <= 0:
            msg = (f"❌❌❌ 开仓失败: 资金不足，无法开仓。"
                   f"可用资金={available_capital:.6f} {self.display_asset}, "
                   f"当前价格={price:.2f}, "
                   f"计算得出={max_contracts}张合约, "
                   f"要求至少={1 / config.TP_RATIO_PER_LEVEL if config.TP_RATIO_PER_LEVEL > 0 else 0:.1f}张")
            if debug_mode:
                self.logger.warning(f"❌ [{ts_str}] {msg}")
            else:
                self.logger.info(msg)
            return False

        # 解析开仓模式：MAKER=限价挂单，TAKER=市价吃单
        open_mode = str(getattr(config, 'OPEN_TAKER_OR_MAKER', 'TAKER') or 'TAKER').strip().upper()
        if open_mode not in ('MAKER', 'TAKER'):
            self.logger.warning(f"OPEN_TAKER_OR_MAKER 配置非法: {open_mode}，回退为 TAKER")
            open_mode = 'TAKER'
        is_maker_open = open_mode == 'MAKER'

        # 预估手续费并锁定对应资金
        open_fee_rate = config.MAKER_FEE_RATE if is_maker_open else config.TAKER_FEE_RATE

        required_margin_btc = (max_contracts * cn) / (price * leverage)
        estimated_fee_btc = (max_contracts * cn * open_fee_rate) / price
        required_btc = required_margin_btc + estimated_fee_btc if not config.NO_LIMIT_POS else 0.0

        if not config.NO_LIMIT_POS:
            self.locked_capital += required_btc
            self.logger.info(
                f"🔒 [资金锁定] {required_btc:.6f} {self.display_asset} | "
                f"已锁定={self.locked_capital:.6f} {self.display_asset} | "
                f"可用={self.realized_pnl - self.locked_capital:.6f} {self.display_asset}"
            )

        # ============================================================
        # 🚀 新增: 通过Exchange接口下单
        # ============================================================
        exchange_side = 'BUY' if side == 'long' else 'SELL'
        open_mode_desc = '限价挂单(MAKER)' if is_maker_open else '市价吃单(TAKER)'

        self.logger.info(
            f"📡 [下单到交易所] {exchange_side} | "
            f"{open_mode_desc} | 价格={price:.2f} | 数量={max_contracts}张"
        )

        try:
            # 生成 trace_id（用于关联 sim_log 和 orders）
            trace_id = str(uuid.uuid4())
            filled_contracts = max_contracts

            # 按配置选择 MAKER/LIMIT 或 TAKER/MARKET 开仓
            order_type = 'LIMIT' if is_maker_open else 'MARKET'
            order_params = {
                'symbol': config.SYMBOL,
                'side': exchange_side,
                'order_type': order_type,
                'quantity': float(max_contracts),
                'current_time': ts,
                'business_order_type': 'OPEN',  # 业务类型：开仓
                'trace_id': trace_id,  # 传递 trace_id
                'kline_close_time': str(row.get('close_time', '')),  # K线收盘时间
            }
            if is_maker_open:
                order_params['price'] = float(price)
                order_params['timeInForce'] = 'GTC'

            order = self.exchange.place_order(**order_params)

            avg_price_display = (
                order.avg_price if order.avg_price and order.avg_price > 0
                else (order.price if order.price and order.price > 0 else price)
            )
            self.logger.info(
                f"📋 [订单响应] ID={order.order_id} | "
                f"状态={order.status.value} | "
                f"成交价={avg_price_display:.2f}"
            )

            # 仅 MAKER 模式发送挂单通知（TAKER 市价单会直接走成交通知）
            if is_maker_open:
                try:
                    self.feishu_bot.send_open_order_placed_notification(
                        symbol=config.SYMBOL,
                        side=side,
                        price=price,
                        contracts=max_contracts,
                        signal_name=signal_name,
                        order_id=str(order.order_id),
                        ts=ts.to_pydatetime() if hasattr(ts, 'to_pydatetime') else ts
                    )
                except Exception as e:
                    self.logger.warning(f"飞书开仓挂单通知发送失败: {e}")

            # 检测订单状态
            if order.status.value == 'FILLED':
                # ✅ 订单成交成功
                self.logger.info(f"✅ [订单成交] 订单 {order.order_id} 已完全成交")
                self.order_success_count += 1
                actual_price = (
                    order.avg_price if order.avg_price is not None and order.avg_price > 0
                    else order.price if hasattr(order, 'price') else price
                )  # 使用成交价，回退到下单价

            elif order.status.value in ['EXPIRED', 'REJECTED']:
                # ❌ 订单失败
                self.logger.warning(
                    f"❌ [订单失败] 订单 {order.order_id} {order.status.value}，"
                    f"作废本地订单，继续寻找信号"
                )
                self.order_failed_count += 1
                if not config.NO_LIMIT_POS:
                    self.locked_capital = max(0.0, self.locked_capital - required_btc)
                return False  # 不创建持仓

            elif order.status.value in ['NEW', 'PARTIALLY_FILLED']:
                # 交易所（尤其测试网）市价单也可能先返回 NEW，统一做短轮询确认最终状态
                poll_timeout = int(
                    getattr(
                        config,
                        'OPEN_LIMIT_TIMEOUT_SECONDS' if is_maker_open else 'OPEN_MARKET_TIMEOUT_SECONDS',
                        180 if is_maker_open else 10
                    )
                )
                poll_interval = 2.0 if is_maker_open else 0.5
                mode_cn = "限价单" if is_maker_open else "市价单"
                self.logger.info(
                    f"⏳ [订单待成交] {mode_cn} {order.order_id} 状态为{order.status.value}，"
                    f"开始轮询等待成交..."
                )
                start_time = time.time()
                final_status = None
                final_order = order

                while time.time() - start_time < poll_timeout:
                    try:
                        queried_order = self.exchange.get_order(config.SYMBOL, order.order_id)
                        if queried_order:
                            final_order = queried_order
                            self.logger.debug(
                                f"📊 [轮询订单] ID={order.order_id} | "
                                f"状态={queried_order.status.value} | "
                                f"avg_price={queried_order.avg_price:.2f} | "
                                f"filled_qty={queried_order.filled_quantity}"
                            )
                            if queried_order.status.value == 'FILLED':
                                final_status = 'FILLED'
                                break
                            elif queried_order.status.value in ['EXPIRED', 'REJECTED', 'CANCELED']:
                                final_status = queried_order.status.value
                                break
                    except Exception as poll_err:
                        self.logger.warning(f"轮询订单状态异常: {poll_err}")
                    time.sleep(poll_interval)

                # 超时后的兜底处理
                if final_status is None:
                    if is_maker_open:
                        self.logger.warning(
                            f"⌛ [挂单超时] 订单 {order.order_id} 超过 {poll_timeout} 秒未完全成交，准备撤单"
                        )
                        try:
                            self.exchange.cancel_order(config.SYMBOL, order.order_id)
                        except Exception as cancel_err:
                            self.logger.warning(f"撤单异常: {cancel_err}")

                        # 撤单后再查询一次最终状态
                        try:
                            queried_order = self.exchange.get_order(config.SYMBOL, order.order_id)
                            if queried_order:
                                final_order = queried_order
                                final_status = queried_order.status.value
                        except Exception as query_err:
                            self.logger.warning(f"撤单后查询订单异常: {query_err}")
                    else:
                        self.logger.warning(
                            f"⌛ [市价单超时] 订单 {order.order_id} 超过 {poll_timeout} 秒仍未成交"
                        )
                        # 市价单无法可靠撤单，直接再查询一次最终状态
                        try:
                            queried_order = self.exchange.get_order(config.SYMBOL, order.order_id)
                            if queried_order:
                                final_order = queried_order
                                final_status = queried_order.status.value
                        except Exception as query_err:
                            self.logger.warning(f"市价单超时后查询订单异常: {query_err}")

                if final_order and final_order.status.value == 'FILLED':
                    # ✅ 订单最终成交
                    self.logger.info(f"✅ [订单成交] 订单 {order.order_id} 轮询确认已成交")
                    self.order_success_count += 1
                    order = final_order
                    filled_contracts = int(float(final_order.filled_quantity or max_contracts))
                    actual_price = (
                        final_order.avg_price if final_order.avg_price > 0
                        else price
                    )
                elif final_order and float(final_order.filled_quantity or 0) > 0:
                    # ✅ 部分成交后撤单，按实际成交数量入场
                    filled_contracts = int(float(final_order.filled_quantity))
                    if filled_contracts <= 0:
                        self.order_failed_count += 1
                        if not config.NO_LIMIT_POS:
                            self.locked_capital = max(0.0, self.locked_capital - required_btc)
                        return False
                    self.logger.info(
                        f"✅ [部分成交] 订单 {order.order_id} 部分成交后已撤单 | 成交={filled_contracts}/{max_contracts}"
                    )
                    self.order_success_count += 1
                    order = final_order
                    actual_price = (
                        final_order.avg_price if final_order.avg_price > 0 else price
                    )
                else:
                    # ❌ 订单未能在规定时间内成交
                    self.logger.warning(
                        f"❌ [订单失败] 订单 {order.order_id} 在{poll_timeout}秒内未成交，"
                        f"最终状态={final_status or 'UNKNOWN'}，放弃本次开仓"
                    )
                    try:
                        self.feishu_bot.send_open_order_canceled_notification(
                            symbol=config.SYMBOL,
                            side=side,
                            price=price,
                            contracts=max_contracts,
                            signal_name=signal_name,
                            order_id=str(order.order_id),
                            reason=f"{poll_timeout}秒未成交，已撤单",
                            ts=ts.to_pydatetime() if hasattr(ts, 'to_pydatetime') else ts
                        )
                    except Exception as notify_err:
                        self.logger.warning(f"飞书开仓撤单通知发送失败: {notify_err}")
                    self.order_failed_count += 1
                    if not config.NO_LIMIT_POS:
                        self.locked_capital = max(0.0, self.locked_capital - required_btc)
                    return False

            else:
                # 未知状态
                self.logger.error(
                    f"❓ [未知状态] 订单 {order.order_id} 状态: {order.status.value}"
                )
                self.order_failed_count += 1
                if not config.NO_LIMIT_POS:
                    self.locked_capital = max(0.0, self.locked_capital - required_btc)
                return False

        except Exception as e:
            self.logger.error(f"❌ [下单异常] {e}", exc_info=True)
            self.order_failed_count += 1
            if not config.NO_LIMIT_POS:
                self.locked_capital = max(0.0, self.locked_capital - required_btc)
            return False

        # ============================================================
        # 订单成交成功，创建持仓
        # ============================================================

        qty_per_contract = cn / actual_price
        open_notional_usd = cn * filled_contracts

        # 若交易所返回真实手续费（币种在 order.commission_asset 中），优先使用
        commission_asset = getattr(order, 'commission_asset', '') or ''
        real_fee = getattr(order, 'commission', 0.0) or 0.0
        if real_fee > 0 and commission_asset.upper() in (self.display_asset, ''):
            open_fee_btc = real_fee
        else:
            open_fee_btc = (open_notional_usd * open_fee_rate) / actual_price

        # 解锁占用资金并扣除实际成本
        if not config.NO_LIMIT_POS:
            self.locked_capital = max(0.0, self.locked_capital - required_btc)
            # 占用保证金按杠杆缩放
            self.realized_pnl -= (filled_contracts * cn / (actual_price * leverage)) + open_fee_btc
        else:
            self.realized_pnl = 0

        # 创建持仓（使用实际成交价格）
        pos = Position(
            id=str(uuid.uuid4()),
            side=side,
            entry_price=actual_price,  # 使用实际成交价
            entry_time=ts,
            contracts=filled_contracts,
            entry_contracts=filled_contracts,
            contract_size_btc=qty_per_contract,
            tp_hit=[],
            tp_activated=False,
            tp_hit_value=0.0,
            trace_id=trace_id,  # 使用与订单相同的 trace_id
            benchmark_price=actual_price,
            entry_hist4=row.get('macd4h'),
            entry_dif4=row.get('dif4h'),
            entry_hist1h=row.get('macd1h'),
            entry_hist15=row.get('macd15m'),
        )

        self.positions.append(pos)
        self.triggers_count += 1

        # 记录开仓到数据库 (TradeRecorder)
        try:
            # 获取成交记录，使用成交ID作为 trade_id
            trade_id = str(order.order_id)  # 默认使用订单ID
            try:
                trades = self.exchange.get_user_trades(config.SYMBOL, order_id=int(order.order_id))
                if trades and len(trades) > 0:
                    # 使用第一条成交记录的ID作为 trade_id
                    trade_id = str(trades[0].get('id', order.order_id))
                    self.logger.info(f"获取到成交记录: trade_id={trade_id}, 成交数量={len(trades)}")
            except Exception as e:
                self.logger.warning(f"获取成交记录失败，使用订单ID作为trade_id: {e}")

            position_record = PositionRecord(
                position_id=pos.id,
                trace_id=trace_id,
                symbol=config.SYMBOL,
                side=side,
                entry_price=actual_price,
                entry_contracts=filled_contracts,
                open_time=ts.isoformat() if hasattr(ts, 'isoformat') else str(ts),
                status='OPEN',
                entry_order_id=str(order.order_id)
            )
            self.trade_recorder.record_position_open(position_record)

            # 同时记录交易记录（使用成交ID）
            trade_record = TradeRecord(
                trace_id=trace_id,
                trade_id=trade_id,
                symbol=config.SYMBOL,
                side=side,
                action='OPEN',
                entry_price=actual_price,
                exit_price=None,
                contracts=filled_contracts,
                position_id=pos.id,
                order_id=str(order.order_id),
                fee_rate=open_fee_rate,
                fee_usd=open_fee_btc * actual_price,
                source='trade_engine',
                trade_time=ts.isoformat() if hasattr(ts, 'isoformat') else str(ts),
                notes=f"开仓信号: {signal_name}"
            )
            self.trade_recorder.record_trade(trade_record)
        except Exception as e:
            self.logger.warning(f"记录开仓到数据库失败: {e}")

        # 飞书开仓通知
        try:
            # 计算一级止盈和止损价格
            tp_levels = list(config.TP_LEVELS) if config.TP_LEVELS else []
            if side == 'long':
                tp1_price = actual_price * tp_levels[0] if tp_levels else None
                sl_price = actual_price * (1 - config.STOP_LOSS_POINTS)
            else:
                tp1_price = actual_price * (2 - tp_levels[0]) if tp_levels else None
                sl_price = actual_price * (1 + config.STOP_LOSS_POINTS)
            
            self.feishu_bot.send_open_order_filled_notification(
                symbol=config.SYMBOL,
                side=side,
                price=actual_price,
                contracts=filled_contracts,
                signal_name=signal_name,
                ts=ts.to_pydatetime() if hasattr(ts, 'to_pydatetime') else ts,
                tp1_price=tp1_price,
                sl_price=sl_price
            )
        except Exception as e:
            self.logger.warning(f"飞书开仓通知发送失败: {e}")

        if debug_mode:
            self.logger.info(f"✅ [{ts_str}] 🎉 开仓成功！{side} {filled_contracts}张 @ {actual_price:.2f}")

        # 记录日志
        self.record_log(
            ts,
            f"开仓{'多头' if side == 'long' else '空头'}",
            side,
            actual_price,
            filled_contracts,
            -1 * open_fee_btc,
            f"开仓成功({signal_name}) "
            f"HIST15={row.get('macd15m', 0):.2f} "
            f"HIST1H={row.get('macd1h', 0):.2f} "
            f"HIST4={row.get('macd4h', 0):.2f}",
            open_fee_rate,
            open_fee_btc * actual_price
        )

        self.logger.info(
            f"✓ 开仓成功 | {side.upper()} | "
            f"价格={actual_price:.2f} | "
            f"数量={filled_contracts}张 | "
            f"手续费={open_fee_btc:.6f} {self.display_asset} (资产={commission_asset or f'{self.display_asset}/估算'}) | "
            f"剩余资金={self.realized_pnl:.6f} {self.display_asset} | "
            f"订单ID={order.order_id}"
        )

        # ============================================================
        # 开仓成功后，不再预先挂止盈单
        # 改为实时监测价格，当触及止盈条件时再挂单
        # ============================================================
        # if config.TP_LEVELS:
        #     self._place_initial_tp_order(pos, ts)

        return True

    def close_position(self, pos: Position, close_time, close_price: float,
                       reason: str, net_btc: Optional[float] = None,
                       pnl_already_applied: bool = False,
                       real_fee_btc: Optional[float] = None,
                       real_pnl_btc: Optional[float] = None,
                       close_order_id: Optional[str] = None):
        """
        平仓

        Args:
            pos: 持仓对象
            close_time: 平仓时间(pandas.Timestamp, str, or datetime)
            close_price: 平仓价格
            reason: 平仓原因
            net_btc: 净盈亏(BTC)，如果为None则计算
            pnl_already_applied: 盈亏是否已经在上游处理
            real_fee_btc: 从交易所接口获取的真实手续费(BTC)，用于飞书通知
            real_pnl_btc: 从交易所接口获取的真实实现盈亏(BTC)，用于飞书通知
            close_order_id: 平仓订单ID，用于获取成交明细
        """
        # 转换时间戳为pandas.Timestamp
        if not isinstance(close_time, pd.Timestamp):
            if isinstance(close_time, str):
                close_time = pd.to_datetime(close_time)
            elif isinstance(close_time, datetime):
                close_time = pd.Timestamp(close_time)
            else:
                try:
                    close_time = pd.to_datetime(close_time)
                except Exception as e:
                    self.logger.error(
                        f"无法转换时间戳: {close_time}, "
                        f"类型: {type(close_time)}, 错误: {e}"
                    )
                    return

        if pos not in self.positions:
            self.logger.warning(f"持仓{pos.id}不存在，无法平仓")
            return

        # 检查价格是否有效
        if not close_price or close_price <= 0:
            self.logger.error(
                f"❌ [{close_time}] 平仓价格无效: {close_price} (type: {type(close_price).__name__})"
            )
            self.logger.error(
                f"   持仓信息: {pos.side} | 入场价={pos.entry_price:.2f} | "
                f"数量={pos.contracts}张 | 入场时间={pos.entry_time}"
            )
            self.logger.error(
                f"   平仓原因: {reason}"
            )
            self.logger.error(
                f"   K线索引: {id(pos)} | 持仓ID: {pos.id}"
            )
            return

        # 📊 输出平仓前信息
        self.logger.info("=" * 80)
        self.logger.info(f"📊 准备平仓 | 持仓ID: {pos.id}")
        self.logger.info(f"平仓时间: {close_time}")
        self.logger.info(f"平仓价格: {close_price:.2f}")
        self.logger.info(f"平仓原因: {reason}")
        self.logger.info(f"持仓方向: {pos.side}")
        self.logger.info(f"入场价格: {pos.entry_price:.2f}")
        self.logger.info(f"持仓数量: {pos.contracts}张")
        self.logger.info(f"入场时间: {pos.entry_time}")
        self.logger.info(f"已触发止盈级别: {pos.tp_hit}")
        self.logger.info("=" * 80)

        cn = config.CONTRACT_NOTIONAL
        notional_usd = cn * pos.contracts
        qty_btc = pos.contracts * pos.contract_size_btc

        # 计算盈亏
        if pos.side == 'long':
            gross_usd = (
                close_price - pos.entry_price
            ) * (qty_btc / close_price)
        else:
            gross_usd = (
                pos.entry_price - close_price
            ) * (qty_btc / close_price)

        close_fee_rate = config.TAKER_FEE_RATE

        # 先计算 fee_btc 和 gross_btc（飞书通知需要）
        fee_btc = (
            (notional_usd * close_fee_rate) / close_price
            if close_price else 0.0
        )
        gross_btc = gross_usd / close_price if close_price else 0.0
        
        if net_btc is None:
            net_btc = gross_btc - fee_btc

        net_usd = net_btc * close_price if close_price else net_btc

        # 更新已实现盈亏（如果尚未在上游处理）
        if net_btc is not None and not pnl_already_applied:
            self.realized_pnl += net_btc

        # 释放锁定资金（使用入场价计算，与开仓时保持一致）
        if not config.NO_LIMIT_POS:
            cn = config.CONTRACT_NOTIONAL
            entry_price = pos.entry_price
            leverage = max(1.0, float(getattr(config, 'LEVERAGE', 1)))
            open_mode = str(getattr(config, 'OPEN_TAKER_OR_MAKER', 'MAKER') or 'MAKER').strip().upper()
            open_fee_rate = config.MAKER_FEE_RATE if open_mode == "MAKER" else config.TAKER_FEE_RATE

            required_margin_btc = (pos.contracts * cn) / (entry_price * leverage) if entry_price > 0 else 0
            estimated_fee_btc = (pos.contracts * cn * open_fee_rate) / entry_price if entry_price > 0 else 0
            locked_btc = required_margin_btc + estimated_fee_btc

            self.locked_capital = max(0.0, self.locked_capital - locked_btc)
            self.logger.info(
                f"🔓 [资金释放] {locked_btc:.6f} {self.display_asset} | "
                f"已锁定={self.locked_capital:.6f} {self.display_asset} | "
                f"可用={self.realized_pnl - self.locked_capital:.6f} {self.display_asset}"
            )

        # 记录交易
        trade = Trade(
            entry_time=pos.entry_time,
            exit_time=close_time,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=close_price,
            qty=pos.contracts,
            gross_pnl=gross_usd,
            net_pnl=net_usd,
            reason=reason,
            trace_id=pos.trace_id
        )
        self.trades.append(trade)

        # 记录平仓到数据库 (TradeRecorder)
        try:
            # 更新持仓记录为关闭状态
            close_time_str = close_time.isoformat() if hasattr(close_time, 'isoformat') else str(close_time)
            self.trade_recorder.record_position_close(
                position_id=pos.id,
                exit_price=close_price,
                exit_contracts=pos.contracts,
                close_time=close_time_str,
                exit_reason=reason,
                total_fee=fee_btc * close_price if close_price else 0,
                gross_pnl=gross_usd,
                net_pnl=net_usd
            )

            # 获取成交记录，使用成交ID作为 trade_id
            trade_id = None
            if close_order_id:
                try:
                    trade_details = self._get_order_trade_details(int(close_order_id))
                    trade_id = trade_details.get('trade_id')
                    if trade_id:
                        self.logger.info(f"获取到平仓成交记录: trade_id={trade_id}")
                except Exception as e:
                    self.logger.warning(f"获取平仓成交记录失败: {e}")

            # 记录平仓交易（使用成交ID）
            trade_record = TradeRecord(
                trace_id=pos.trace_id,
                trade_id=trade_id,  # 使用成交ID，与同步数据一致
                symbol=config.SYMBOL,
                side=pos.side,
                action=reason.upper() if reason else 'CLOSE',
                entry_price=pos.entry_price,
                exit_price=close_price,
                contracts=pos.contracts,
                position_id=pos.id,
                order_id=close_order_id,
                fee_rate=close_fee_rate,
                fee_usd=fee_btc * close_price if close_price else 0,
                gross_pnl=gross_usd,
                net_pnl=net_usd,
                source='trade_engine',
                trade_time=close_time_str,
                notes=f"平仓原因: {reason}"
            )
            self.trade_recorder.record_trade(trade_record)
        except Exception as e:
            self.logger.warning(f"记录平仓到数据库失败: {e}")

        # 注意: 不在这里记录日志,与macd_refactor.py保持一致
        # 日志记录已经在各个业务逻辑中完成(止盈、止损、回撤、超时)
        # 避免重复记录

        self.logger.info(
            f"✓ 平仓成功 | {pos.side.upper()} | "
            f"入场={pos.entry_price:.2f} | "
            f"出场={close_price:.2f} | "
            f"数量={pos.contracts}张 | "
            f"盈亏={net_btc:.6f} {self.display_asset} (${net_usd:.2f}) | "
            f"原因={reason} | "
            f"当前资金={self.realized_pnl:.6f} {self.display_asset}"
        )

        # 平仓后查询交易所账户余额并更新缓存（在发送飞书通知之前）
        try:
            account_info = self.exchange.get_account_info(self.display_asset)
            if account_info and hasattr(account_info, 'total_wallet_balance'):
                self.cached_total_balance = account_info.total_wallet_balance
                # 同步更新 realized_pnl 为交易所实际余额
                self.realized_pnl = account_info.total_wallet_balance
                self.logger.info(
                    f"📊 平仓后账户余额更新: {self.cached_total_balance:.8f} {self.display_asset}"
                )
        except Exception as e:
            self.logger.warning(f"⚠️ 平仓后查询账户余额失败: {e}")

        # 发送飞书平仓通知
        try:
            # 优先使用从交易所接口获取的真实数据(BTC)，否则使用本地计算值
            fee_btc_final = real_fee_btc if real_fee_btc is not None else fee_btc
            pnl_btc_final = real_pnl_btc if real_pnl_btc is not None else net_btc
            
            # 根据真实盈亏重新计算毛利（如果有真实数据）
            gross_btc_final = gross_btc
            if real_pnl_btc is not None and real_fee_btc is not None:
                # 真实毛利 = 真实净利 + 真实手续费
                gross_btc_final = real_pnl_btc + real_fee_btc
            
            self.feishu_bot.send_close_position_notification(
                symbol=config.SYMBOL,
                side=pos.side,
                entry_price=pos.entry_price,
                close_price=close_price,
                contracts=pos.contracts,
                entry_time=pos.entry_time,
                close_time=close_time,
                gross_btc=gross_btc_final,
                fee_btc=fee_btc_final,
                net_btc=pnl_btc_final,
                reason=reason,
                tp_hit=pos.tp_hit if hasattr(pos, 'tp_hit') else [],
                total_balance_btc=self.cached_total_balance
            )
        except Exception as e:
            self.logger.warning(f"发送飞书平仓通知失败: {e}")

        # 移除持仓
        self.positions.remove(pos)








    def apply_take_profit(
        self, pos: Position, ts: pd.Timestamp, price: float, row: Dict
    ) -> bool:
        """
        K线止盈检测（兼容旧逻辑，用于回测模式）

        新策略:
        1. 使用K线最高/最低价检测是否达到止盈级别
        2. 如果达到的不是最后一级别，不进行止盈操作，只记录标准，标定止盈回撤价格
        3. 如果达到最后一级别止盈标准，直接挂市价单平仓

        Args:
            pos: 持仓对象
            ts: 当前时间
            price: 当前价格（收盘价）
            row: K线数据

        Returns:
            bool: 是否全部平仓
        """
        ref_high = row.get('high', price)
        ref_low = row.get('low', price)
        close_price = row.get('close', price)
        tp_levels = list(config.TP_LEVELS)

        if not tp_levels:
            return False

        # 使用入场价作为止盈参考价
        ref_price = pos.entry_price
        cn = config.CONTRACT_NOTIONAL
        max_level_idx = len(tp_levels) - 1  # 最后一级别的索引
        
        # 📊 止盈计算日志
        # 计算各级止盈价格和预期盈利
        tp_info_list = []
        for idx, lvl in enumerate(tp_levels):
            if lvl < 1:
                pts = round(ref_price * lvl, 1)
            elif lvl >= 1 and lvl < 2:
                pts = round(ref_price * (lvl - 1), 1)
            else:
                pts = lvl
            if pos.side == 'long':
                tp_target = round(ref_price + pts, 1)
                tp_pnl = (tp_target - ref_price) * pos.contracts * cn / tp_target
            else:
                tp_target = round(ref_price - pts, 1)
                tp_pnl = (ref_price - tp_target) * pos.contracts * cn / tp_target
            hit_mark = "✓" if lvl in pos.tp_hit else ""
            tp_info_list.append(f"L{idx+1}=${tp_target:.2f}(+{tp_pnl:.6f}{self.display_asset}){hit_mark}")
        
        self.logger.debug(
            f"📊 [止盈检测] 持仓ID={pos.id} | 方向={pos.side} | "
            f"入场价={ref_price:.2f} | 合约={pos.contracts}张"
        )
        self.logger.debug(
            f"   K线价格: 最高={ref_high:.2f} | 最低={ref_low:.2f} | "
            f"收盘={close_price:.2f}"
        )
        self.logger.debug(f"   止盈级别: {' | '.join(tp_info_list)}")

        # 遍历各级别，检查是否触发
        for idx, lvl in enumerate(tp_levels):
            # 跳过已触发的级别
            if lvl in pos.tp_hit:
                continue

            # 计算目标价格
            if lvl < 1:
                pts = round(ref_price * lvl, 1)
            elif lvl >= 1 and lvl < 2:
                pts = round(ref_price * (lvl - 1), 1)
            else:
                pts = lvl

            target_price = (
                round(ref_price + pts, 1)
                if pos.side == 'long'
                else round(ref_price - pts, 1)
            )

            # 检查是否触发止盈（使用最高/最低价判断）
            triggered = False
            if pos.side == 'long':
                if ref_high is not None and ref_high >= target_price:
                    triggered = True
                    self.logger.info(
                        f"🎯 [止盈触发] 多头Lv{idx+1} | "
                        f"最高价{ref_high:.2f} >= 目标价{target_price:.2f}"
                    )
            else:
                if ref_low is not None and ref_low <= target_price:
                    triggered = True
                    self.logger.info(
                        f"🎯 [止盈触发] 空头Lv{idx+1} | "
                        f"最低价{ref_low:.2f} <= 目标价{target_price:.2f}"
                    )

            if not triggered:
                continue

            # ============================================================
            # 止盈触发！
            # ============================================================
            is_last_level = (idx == max_level_idx)

            # 标记此级别已触发
            pos.tp_hit.append(lvl)
            pos.tp_activated = True
            pos.tp_hit_value = target_price
            pos.tp_level_reached = idx + 1  # 1-based级别

            self.logger.info("=" * 80)
            self.logger.info(f"📈 [止盈触发] 持仓ID: {pos.id}")
            self.logger.info(f"级别: {idx + 1}/{len(tp_levels)} (最后级别: {'是' if is_last_level else '否'})")
            self.logger.info(f"目标价: {target_price:.2f}")
            self.logger.info("=" * 80)

            # 飞书止盈触发通知
            try:
                # 计算未实现盈亏
                cn = config.CONTRACT_NOTIONAL
                if pos.side == 'long':
                    unrealized_usd = (close_price - pos.entry_price) * (pos.contracts * pos.contract_size_btc / close_price)
                else:
                    unrealized_usd = (pos.entry_price - close_price) * (pos.contracts * pos.contract_size_btc / close_price)

                self.feishu_bot.send_tp_hit_notification(
                    symbol=config.SYMBOL,
                    side=pos.side,
                    entry_price=pos.entry_price,
                    current_price=close_price,
                    tp_level=idx + 1,
                    tp_price=target_price,
                    contracts=pos.contracts,
                    unrealized_pnl=unrealized_usd
                )
            except Exception as e:
                self.logger.warning(f"飞书止盈触发通知发送失败: {e}")

            if is_last_level:
                # ============================================================
                # 最后一级别：直接市价平仓
                # ============================================================
                self.logger.info(f"🎯 [最后级别止盈] 直接市价全平")

                # 取消所有相关挂单
                self._cancel_all_related_orders(pos)

                # 市价平仓
                return self._market_close_for_tp(pos, ts, close_price)

            else:
                # ============================================================
                # 非最后级别：只记录，标定回撤价格，不平仓
                # ============================================================
                # 计算回撤价格
                if config.DRAWDOWN_POINTS <= 0:
                    self.logger.warning("⚠️ DRAWDOWN_POINTS <= 0，无法计算回撤价格")
                    continue

                dd = (
                    config.DRAWDOWN_POINTS if config.DRAWDOWN_POINTS > 1
                    else round(target_price * config.DRAWDOWN_POINTS, 1)
                )

                if pos.side == 'long':
                    # 多头：回撤价 = 止盈价 - 回撤点
                    drawdown_price = round(target_price - dd, 1)
                else:
                    # 空头：回撤价 = 止盈价 + 回撤点
                    drawdown_price = round(target_price + dd, 1)

                pos.tp_confirmed_price = target_price
                pos.tp_drawdown_price = drawdown_price
                pos.tp_highest_price = (
                    ref_high if pos.side == 'long' else ref_low
                )

                self.logger.info(f"📝 [止盈级别记录] 不平仓")
                self.logger.info(f"   止盈价: {target_price:.2f}")
                self.logger.info(f"   回撤点: {dd:.2f}")
                self.logger.info(f"   回撤触发价: {drawdown_price:.2f}")

                # 记录日志（不平仓）
                self.record_log(
                    ts,
                    'TP_LEVEL_HIT',
                    pos.side,
                    close_price,
                    pos.contracts,
                    0,  # 不平仓，盈亏为0
                    f"止盈级别{idx + 1}触发 回撤价={drawdown_price:.2f}"
                )

                # 只处理第一个触发的级别
                break

        return False

    def _market_close_for_tp(self, pos: Position, ts: pd.Timestamp, price: float) -> bool:
        """
        止盈市价平仓

        Args:
            pos: 持仓对象
            ts: 时间戳
            price: 参考价格

        Returns:
            bool: 是否成功平仓
        """
        close_side = 'SELL' if pos.side == 'long' else 'BUY'
        cn = config.CONTRACT_NOTIONAL

        self.logger.info(
            f"🚨 [止盈市价平仓] {close_side} @ 市价 | 数量={pos.contracts}张"
        )

        # 查询实际持仓余额，如果没有持仓则不下单
        try:
            position_info = self.exchange.get_position(config.SYMBOL)
            if position_info is None:
                self.logger.warning(f"⚠️ [止盈市价平仓] 查询持仓为空，跳过平仓订单")
                return False
            position_amt = abs(position_info.get('position_amount', 0))
            if position_amt <= 0:
                self.logger.warning(f"⚠️ [止盈市价平仓] 持仓余额为0，跳过平仓订单")
                return False
        except Exception as e:
            self.logger.error(f"❌ [止盈市价平仓] 查询持仓失败: {e}")
            # 查询失败时仍然允许下单，保持原有行为

        try:
            order = self.exchange.place_order(
                symbol=config.SYMBOL,
                side=close_side,
                order_type='MARKET',
                quantity=float(pos.contracts),
                price=None,
                business_order_type='TP',
                trace_id=pos.trace_id,
                kline_close_time=str(ts),
                reduceOnly=True  # 🔑 关键：确保是平仓操作，不会开反向仓
            )

            # 如果市价单返回NEW状态，轮询等待成交
            if order.status.value == 'NEW':
                self.logger.info(f"⏳ [止盈平仓订单待成交] 订单 {order.order_id} 轮询等待...")
                poll_timeout = 10
                poll_interval = 0.5
                start_time = time.time()
                
                while time.time() - start_time < poll_timeout:
                    try:
                        queried_order = self.exchange.get_order(config.SYMBOL, order.order_id)
                        if queried_order and queried_order.status.value == 'FILLED':
                            order = queried_order
                            break
                        elif queried_order and queried_order.status.value in ['EXPIRED', 'REJECTED', 'CANCELED']:
                            order = queried_order
                            break
                    except Exception as poll_err:
                        self.logger.warning(f"轮询止盈平仓订单状态异常: {poll_err}")
                    time.sleep(poll_interval)

            if order.status.value == 'FILLED':
                # 轮询查询真实成交价格
                actual_price = self._poll_close_order_price(
                    order.order_id,
                    fallback_price=order.avg_price if order.avg_price > 0 else price
                )
                self.logger.info(f"✅ 止盈市价单成交 @ {actual_price:.2f}")

                # 计算盈亏
                notional_usd = cn * pos.contracts
                if pos.side == 'long':
                    gross_pnl_btc = notional_usd * (1 / pos.entry_price - 1 / actual_price)
                else:
                    gross_pnl_btc = notional_usd * (1 / actual_price - 1 / pos.entry_price)

                fee_rate = config.TAKER_FEE_RATE
                fee_btc = (notional_usd * fee_rate) / actual_price
                net_btc = gross_pnl_btc - fee_btc

                # 更新已实现盈亏
                self.realized_pnl += net_btc

                # 记录日志
                self.record_log(
                    ts,
                    'TAKE_PROFIT_FINAL',
                    pos.side,
                    actual_price,
                    pos.contracts,
                    gross_pnl_btc,
                    f"最后级别止盈全平 级别={pos.tp_level_reached}",
                    fee_rate,
                    fee_btc * actual_price
                )

                # 尝试获取真实的成交明细（手续费和实现盈亏）
                real_fee_btc = None
                real_pnl_btc = None
                trade_details = self._get_order_trade_details(order.order_id)
                real_fee_btc = trade_details.get('real_fee_btc')
                real_pnl_btc = trade_details.get('real_pnl_btc')

                # 关闭持仓
                self.close_position(pos, ts, actual_price, 'take_profit_final', net_btc, pnl_already_applied=True,
                                   real_fee_btc=real_fee_btc, real_pnl_btc=real_pnl_btc,
                                   close_order_id=str(order.order_id))
                return True
            else:
                self.logger.error(f"❌ 止盈市价单失败: {order.status.value}")
                return False

        except Exception as e:
            self.logger.error(f"❌ [止盈市价平仓异常] {e}", exc_info=True)
            return False



    def _poll_close_order_price(self, order_id: str, fallback_price: float) -> float:
        """
        轮询查询平仓单成交价格

        市价单下单后，轮询查询订单状态获取真实的成交价格，
        避免使用下单接口返回的预估价格。

        Args:
            order_id: 订单ID
            fallback_price: 回退价格（查询失败时使用）

        Returns:
            float: 成交价格，查询失败时返回 fallback_price
        """
        timeout = 60  # 60秒超时
        poll_interval = 0.5  # 每次轮询间隔秒数
        start_time = time.time()

        while True:
            elapsed = time.time() - start_time

            # 检查超时
            if elapsed >= timeout:
                self.logger.error(f"❌ [查询订单] 轮询超时({timeout}秒)，订单未成交")
                # 发送飞书告警
                try:
                    self.feishu_bot.send_message(
                        f"⚠️ 平仓订单查询超时\n"
                        f"订单ID: {order_id}\n"
                        f"超时时间: {timeout}秒\n"
                        f"使用fallback价格: ${fallback_price:.2f}"
                    )
                except Exception as e:
                    self.logger.warning(f"飞书告警发送失败: {e}")
                return fallback_price

            try:
                queried_order = self.exchange.get_order(config.SYMBOL, order_id)
                if queried_order is None:
                    self.logger.warning(f"⚠️ [查询订单] 返回None，已轮询{elapsed:.1f}秒")
                    time.sleep(poll_interval)
                    continue

                self.logger.debug(
                    f"📊 [查询订单] ID={order_id} | "
                    f"状态={queried_order.status.value} | "
                    f"avg_price={queried_order.avg_price:.2f} | "
                    f"filled_qty={queried_order.filled_quantity} | "
                    f"已轮询{elapsed:.1f}秒"
                )

                # 订单已完全成交
                if queried_order.status.value == 'FILLED':
                    if queried_order.avg_price > 0:
                        self.logger.info(
                            f"✅ [查询订单] 获取真实成交价: {queried_order.avg_price:.2f} | 耗时{elapsed:.1f}秒"
                        )
                        return queried_order.avg_price
                    else:
                        self.logger.warning(
                            f"⚠️ [查询订单] FILLED但avg_price=0，使用fallback价格 | 耗时{elapsed:.1f}秒"
                        )
                        return fallback_price

                # 订单部分成交，使用已成交部分的均价
                elif queried_order.status.value == 'PARTIALLY_FILLED':
                    if queried_order.avg_price > 0:
                        self.logger.info(
                            f"📊 [查询订单] 部分成交，使用部分均价: {queried_order.avg_price:.2f} | 耗时{elapsed:.1f}秒"
                        )
                        return queried_order.avg_price

                # 订单被拒绝/取消，使用fallback价格
                elif queried_order.status.value in ['REJECTED', 'CANCELED', 'EXPIRED']:
                    self.logger.warning(
                        f"⚠️ [查询订单] 订单{queried_order.status.value}，使用fallback价格 | 耗时{elapsed:.1f}秒"
                    )
                    return fallback_price

                # 其他状态继续轮询
                time.sleep(poll_interval)

            except Exception as e:
                self.logger.warning(
                    f"⚠️ [查询订单] 异常(已轮询{elapsed:.1f}秒): {e}"
                )
                time.sleep(poll_interval)

    def _get_order_trade_details(self, order_id: int) -> dict:
        """
        获取订单成交明细中的手续费和实现盈亏

        通过 get_user_trades 接口获取订单的真实成交数据，
        从中提取手续费(commission)和实现盈亏(realizedPnl)。

        Args:
            order_id: 订单ID

        Returns:
            dict: 包含以下字段：
                - real_fee_btc: 真实手续费(基础币种)，无数据时为 None
                - real_pnl_btc: 真实实现盈亏(基础币种)，无数据时为 None
                - commission_asset: 手续费资产类型
                - trade_id: 第一条成交记录的ID（用于与同步数据去重）
                - trade_ids: 所有成交记录ID列表
        """
        result = {
            'real_fee_btc': None,
            'real_pnl_btc': None,
            'commission_asset': None,
            'trade_id': None,
            'trade_ids': []
        }

        try:
            trades = self.exchange.get_user_trades(config.SYMBOL, order_id=order_id)
            if not trades:
                self.logger.warning(f"⚠️ [成交明细] 订单 {order_id} 无成交记录")
                return result

            total_commission = 0.0
            total_realized_pnl = 0.0
            commission_asset = None
            trade_ids = []

            for trade in trades:
                # 累加手续费
                commission = float(trade.get('commission', 0) or 0)
                total_commission += commission

                # 累加实现盈亏
                realized_pnl = float(trade.get('realizedPnl', 0) or 0)
                total_realized_pnl += realized_pnl

                # 获取手续费资产（通常是 BTC 或 USDT）
                if not commission_asset:
                    commission_asset = trade.get('commissionAsset', '')

                # 收集成交ID
                trade_id = trade.get('id')
                if trade_id:
                    trade_ids.append(str(trade_id))

            # 直接使用 BTC 值（币本位合约）
            result['real_fee_btc'] = total_commission
            result['real_pnl_btc'] = total_realized_pnl
            result['commission_asset'] = commission_asset
            result['trade_ids'] = trade_ids
            if trade_ids:
                result['trade_id'] = trade_ids[0]  # 使用第一条成交ID

        except Exception as e:
            self.logger.warning(f"⚠️ [成交明细] 获取订单 {order_id} 成交明细失败: {e}")

        return result



    def check_stop_loss(self, pos: Position, ts: pd.Timestamp,
                        price: float, high: float = None,
                        low: float = None) -> bool:
        """
        K线止损检测（兼容旧逻辑，用于回测模式）

        Args:
            pos: 持仓对象
            ts: 当前时间
            price: 当前价格（收盘价）
            high: 最高价
            low: 最低价

        Returns:
            bool: 是否触发止损并平仓
        """
        # 计算止损价格
        stop_price = self._calculate_stop_price(pos)
        ref_low = low if low is not None else price
        ref_high = high if high is not None else price

        # 📊 止损计算日志
        self.logger.debug(
            f"📊 [止损检测] 持仓ID={pos.id} | 方向={pos.side} | "
            f"入场价={pos.entry_price:.2f}"
        )
        self.logger.debug(
            f"   止损参数: STOP_LOSS_POINTS={config.STOP_LOSS_POINTS} | "
            f"止损价={stop_price:.2f}"
        )
        self.logger.debug(
            f"   K线价格: 最高={ref_high:.2f} | 最低={ref_low:.2f} | "
            f"收盘={price:.2f}"
        )

        # 检查是否触发止损
        sl_triggered = False
        if pos.side == 'long':
            # 多头: 当前最低价 <= 止损价
            if ref_low <= stop_price:
                sl_triggered = True
                self.logger.info(
                    f"🛑 [止损触发] 多头 | "
                    f"最低价{ref_low:.2f} <= 止损价{stop_price:.2f}"
                )
        else:  # short
            # 空头: 当前最高价 >= 止损价
            if ref_high >= stop_price:
                sl_triggered = True
                self.logger.info(
                    f"🛑 [止损触发] 空头 | "
                    f"最高价{ref_high:.2f} >= 止损价{stop_price:.2f}"
                )

        if not sl_triggered:
            return False

        # ============================================================
        # 止损已触发，取消所有挂单并市价平仓
        # ============================================================
        pos.sl_triggered = True
        self.logger.info("=" * 80)
        self.logger.info(f"🛑 止损触发 | 持仓ID: {pos.id}")
        self.logger.info(f"方向: {pos.side}")
        self.logger.info(f"入场价: {pos.entry_price:.2f}")
        self.logger.info(f"止损价: {stop_price:.2f}")
        self.logger.info(f"当前价: {price:.2f}")
        self.logger.info("=" * 80)

        # 取消所有相关挂单
        self._cancel_all_related_orders(pos)

        # 市价单平仓
        return self._market_close_position(pos, ts, price, reason='stop_loss')

    def _calculate_stop_price(self, pos: Position) -> float:
        """计算止损价格"""
        ref_price = pos.entry_price
        
        # 计算止损点数
        if config.STOP_LOSS_POINTS < 1:
            # 百分比模式
            stop = round(ref_price * config.STOP_LOSS_POINTS, 1)
            self.logger.debug(
                f"   止损计算(百分比): {ref_price:.2f} × {config.STOP_LOSS_POINTS} = {stop:.1f}"
            )
        else:
            # 固定点数模式
            stop = config.STOP_LOSS_POINTS
            self.logger.debug(
                f"   止损计算(固定点数): {stop:.1f}"
            )

        if pos.side == 'long':
            result = ref_price - stop
            self.logger.debug(
                f"   多头止损价: {ref_price:.2f} - {stop:.1f} = {result:.2f}"
            )
            return result
        else:  # short
            result = ref_price + stop
            self.logger.debug(
                f"   空头止损价: {ref_price:.2f} + {stop:.1f} = {result:.2f}"
            )
            return result

    def _cancel_all_related_orders(self, pos: Position):
        """
        取消所有与持仓相关的挂单

        Args:
            pos: 持仓对象
        """
        self.logger.info(f"🔕 [取消所有挂单] 持仓ID: {pos.id}")
        
        try:
            open_orders = self.exchange.get_open_orders(config.SYMBOL)
            if not open_orders:
                self.logger.info("   没有需要取消的挂单")
                return
            
            cancelled_count = 0
            for order in open_orders:
                try:
                    self.logger.info(
                        f"   撤销订单: ID={order.order_id} | "
                        f"方向={order.side.value} | 价格={order.price:.2f}"
                    )
                    self.exchange.cancel_order(config.SYMBOL, order.order_id)
                    cancelled_count += 1
                except Exception as e:
                    self.logger.warning(f"   撤销订单失败: {order.order_id} | {e}")
            
            self.logger.info(f"   共撤销 {cancelled_count} 个挂单")
            
            # 清理持仓中的订单记录
            pos.tp_order_id = None
            pos.tp_order_contracts = 0
            pos.sl_order_id = None
            
        except Exception as e:
            self.logger.error(f"❌ [取消挂单失败] {e}", exc_info=True)



    def _market_close_position(self, pos: Position, ts: pd.Timestamp,
                                price: float, reason: str) -> bool:
        """
        使用市价单强制平仓（吃单）

        Args:
            pos: 持仓对象
            ts: 当前时间
            price: 价格
            reason: 平仓原因

        Returns:
            bool: 是否成功
        """
        close_side = 'SELL' if pos.side == 'long' else 'BUY'

        self.logger.warning(
            f"🚨 [市价平仓] {close_side} @ 市价 | "
            f"数量={pos.contracts}张 | 原因={reason}"
        )

        try:
            # 先撤销可能冲突的同方向挂单
            try:
                open_orders = self.exchange.get_open_orders(config.SYMBOL)
                if open_orders:
                    for existing_order in open_orders:
                        if existing_order.side.value == close_side:
                            self.logger.info(f"🔕 [撤销冲突挂单] ID={existing_order.order_id}")
                            self.exchange.cancel_order(config.SYMBOL, existing_order.order_id)
            except Exception as e:
                self.logger.warning(f"⚠️ 检查/撤销挂单失败: {e}")

            # 🔑 关键：查询交易所实际持仓，检查方向是否一致
            try:
                position_info = self.exchange.get_position(config.SYMBOL)
                if position_info is None:
                    self.logger.warning(f"⚠️ [市价平仓] 查询持仓为空，清理本地虚假持仓 | 原因={reason}")
                    self.positions.remove(pos)
                    return True  # 返回True表示已处理
                    
                exchange_amt = float(position_info.get('position_amount', 0))
                exchange_side = 'long' if exchange_amt > 0 else 'short' if exchange_amt < 0 else None
                exchange_qty = abs(int(exchange_amt))
                
                self.logger.info(
                    f"📊 [市价平仓前检查] 交易所持仓: {exchange_side} {exchange_qty}张 | "
                    f"本地持仓: {pos.side} {pos.contracts}张"
                )
                
                if exchange_qty <= 0:
                    self.logger.warning(f"⚠️ [市价平仓] 交易所无持仓，清理本地虚假持仓 | 原因={reason}")
                    self.positions.remove(pos)
                    return True
                    
                if exchange_side != pos.side:
                    self.logger.warning(
                        f"⚠️ [市价平仓] 交易所持仓方向({exchange_side})与本地({pos.side})不符，"
                        f"清理本地虚假持仓 | 原因={reason}"
                    )
                    self.positions.remove(pos)
                    return True
                    
            except Exception as e:
                self.logger.error(f"❌ [市价平仓] 查询持仓失败: {e}")
                # 查询失败时仍然允许下单，保持原有行为

            # 使用市价单，添加reduceOnly确保是平仓而非开反向仓
            order = self.exchange.place_order(
                symbol=config.SYMBOL,
                side=close_side,
                order_type='MARKET',
                quantity=float(pos.contracts),
                price=None,
                current_time=ts,
                business_order_type='SL',  # 业务类型：止损
                trace_id=pos.trace_id,  # 使用持仓的 trace_id
                kline_close_time=str(ts),  # 使用当前K线时间
                reduceOnly=True  # 🔑 关键：确保是平仓操作，不会开反向仓
            )

            # 如果市价单返回NEW状态，轮询等待成交
            if order.status.value == 'NEW':
                self.logger.info(f"⏳ [平仓订单待成交] 订单 {order.order_id} 轮询等待...")
                poll_timeout = 10
                poll_interval = 0.5
                start_time = time.time()
                
                while time.time() - start_time < poll_timeout:
                    try:
                        queried_order = self.exchange.get_order(config.SYMBOL, order.order_id)
                        if queried_order and queried_order.status.value == 'FILLED':
                            order = queried_order
                            break
                        elif queried_order and queried_order.status.value in ['EXPIRED', 'REJECTED', 'CANCELED']:
                            order = queried_order
                            break
                    except Exception as poll_err:
                        self.logger.warning(f"轮询平仓订单状态异常: {poll_err}")
                    time.sleep(poll_interval)

            if order.status.value == 'FILLED':
                # 轮询查询真实成交价格
                actual_price = self._poll_close_order_price(
                    order.order_id,
                    fallback_price=order.avg_price if order.avg_price > 0 else price
                )
                self.logger.info(f"✅ 市价单成交 @ {actual_price:.2f}")
                self._close_position_after_sl(pos, ts, actual_price, reason, order_id=order.order_id)
                return True
            else:
                self.logger.error(f"❌ 市价单失败: {order.status.value}")
                return False

        except Exception as e:
            self.logger.error(f"❌ [市价平仓异常] {e}", exc_info=True)
            return False

    def _close_position_after_sl(self, pos: Position, ts: pd.Timestamp,
                                   price: float, reason: str,
                                   order_id: Optional[int] = None):
        """
        止损平仓后的清理工作

        Args:
            pos: 持仓对象
            ts: 平仓时间
            price: 平仓价格
            reason: 平仓原因
            order_id: 平仓订单ID，用于获取真实成交明细
        """
        # 记录止损时间和方向（用于冷却逻辑）
        self.stoploss_time = ts
        self.stoploss_side = pos.side

        # 计算盈亏
        cn = config.CONTRACT_NOTIONAL
        notional_usd = cn * pos.contracts

        if pos.side == 'long':
            gross_pnl_btc = notional_usd * (1 / pos.entry_price - 1 / price)
        else:  # short
            gross_pnl_btc = notional_usd * (1 / price - 1 / pos.entry_price)

        fee_rate = config.TAKER_FEE_RATE
        fee_btc = (notional_usd * fee_rate) / price
        net_btc = gross_pnl_btc - fee_btc

        # 更新已实现盈亏
        self.realized_pnl += net_btc

        # 记录日志
        self.record_log(
            ts,
            'STOP_LOSS',
            pos.side,
            price,
            pos.contracts,
            gross_pnl_btc,
            f"止损触发 尝试次数={pos.sl_order_attempts}",
            fee_rate,
            fee_btc * price
        )

        # 尝试获取真实的成交明细（手续费和实现盈亏）
        real_fee_btc = None
        real_pnl_btc = None
        if order_id:
            trade_details = self._get_order_trade_details(order_id)
            real_fee_btc = trade_details.get('real_fee_btc')
            real_pnl_btc = trade_details.get('real_pnl_btc')

        # 关闭持仓
        self.close_position(pos, ts, price, reason, net_btc, pnl_already_applied=True,
                           real_fee_btc=real_fee_btc, real_pnl_btc=real_pnl_btc,
                           close_order_id=str(order_id) if order_id else None)


    def check_drawdown(self, pos: Position, ts: pd.Timestamp,
                       price: float, row: Dict) -> bool:
        """
        检查止盈后的回撤平仓（使用分钟收盘价检测）

        新策略:
        1. 根据止盈级别确认的价格（tp_confirmed_price）
        2. 检测分钟收盘价是否达到回撤价格（tp_drawdown_price）
        3. 如果达到，挂市价单全平

        Args:
            pos: 持仓对象
            ts: 当前时间
            price: 当前价格
            row: K线数据

        Returns:
            bool: 是否触发回撤平仓
        """
        # 检查是否有已确认的止盈回撤价格
        if pos.tp_drawdown_price is None:
            # 兼容旧逻辑
            if (
                not pos.tp_activated or
                config.DRAWDOWN_POINTS <= 0 or
                not pos.tp_hit
            ):
                return False
            # 使用旧的 tp_hit_value 作为确认价格
            pos.tp_confirmed_price = pos.tp_hit_value
            dd = (
                config.DRAWDOWN_POINTS if config.DRAWDOWN_POINTS > 1
                else round(pos.tp_confirmed_price * config.DRAWDOWN_POINTS, 1)
            )
            if pos.side == 'long':
                pos.tp_drawdown_price = round(pos.tp_confirmed_price - dd, 1)
            else:
                pos.tp_drawdown_price = round(pos.tp_confirmed_price + dd, 1)

        # 使用分钟收盘价检测回撤
        close_price = row.get('close', price)
        cn = config.CONTRACT_NOTIONAL

        # 📊 回撤检测日志
        self.logger.debug(
            f"📊 [回撤检测] 持仓ID={pos.id} | 方向={pos.side}"
        )
        self.logger.debug(
            f"   确认价: {pos.tp_confirmed_price:.2f} | "
            f"回撤价: {pos.tp_drawdown_price:.2f} | "
            f"收盘价: {close_price:.2f}"
        )

        # 检查收盘价是否达到回撤价格
        triggered = False
        if pos.side == 'long':
            # 多头：收盘价 <= 回撤价
            if close_price <= pos.tp_drawdown_price:
                triggered = True
                self.logger.info(
                    f"📉 [回撤触发] 多头 | "
                    f"收盘价{close_price:.2f} <= 回撤价{pos.tp_drawdown_price:.2f}"
                )
        else:  # short
            # 空头：收盘价 >= 回撤价
            if close_price >= pos.tp_drawdown_price:
                triggered = True
                self.logger.info(
                    f"📉 [回撤触发] 空头 | "
                    f"收盘价{close_price:.2f} >= 回撤价{pos.tp_drawdown_price:.2f}"
                )

        if not triggered:
            return False

        # ============================================================
        # 回撤触发，市价全平
        # ============================================================
        self.logger.info("=" * 80)
        self.logger.info(f"📉 [回撤平仓] 持仓ID: {pos.id}")
        self.logger.info(f"确认价: {pos.tp_confirmed_price:.2f}")
        self.logger.info(f"回撤价: {pos.tp_drawdown_price:.2f}")
        self.logger.info(f"收盘价: {close_price:.2f}")
        self.logger.info("=" * 80)

        # 飞书止盈回撤通知
        try:
            # 计算未实现盈亏
            cn = config.CONTRACT_NOTIONAL
            if pos.side == 'long':
                unrealized_usd = (close_price - pos.entry_price) * (pos.contracts * pos.contract_size_btc / close_price)
            else:
                unrealized_usd = (pos.entry_price - close_price) * (pos.contracts * pos.contract_size_btc / close_price)

            self.feishu_bot.send_tp_pullback_notification(
                symbol=config.SYMBOL,
                side=pos.side,
                entry_price=pos.entry_price,
                current_price=close_price,
                highest_tp_level=pos.tp_level_reached,
                pullback_price=pos.tp_drawdown_price,
                unrealized_pnl=unrealized_usd,
                contracts=pos.contracts
            )
        except Exception as e:
            self.logger.warning(f"飞书止盈回撤通知发送失败: {e}")

        # 取消所有相关挂单
        self._cancel_all_related_orders(pos)

        # 🔑 关键：先查询交易所实际持仓，确认本地持仓与交易所一致
        try:
            position_info = self.exchange.get_position(config.SYMBOL)
            if position_info:
                exchange_amt = float(position_info.get('position_amount', 0))
                exchange_side = 'long' if exchange_amt > 0 else 'short' if exchange_amt < 0 else None
                exchange_qty = abs(int(exchange_amt))
                
                self.logger.info(
                    f"📊 [回撤平仓前检查] 交易所持仓: {exchange_side} {exchange_qty}张 | "
                    f"本地持仓: {pos.side} {pos.contracts}张"
                )
                
                # 如果交易所没有持仓，或者方向不一致，则清理本地状态不下单
                if exchange_qty <= 0:
                    self.logger.warning(
                        f"⚠️ [回撤平仓] 交易所无持仓，清理本地虚假持仓 {pos.id}"
                    )
                    self.positions.remove(pos)
                    return True  # 返回True表示处理完成
                
                if exchange_side != pos.side:
                    self.logger.warning(
                        f"⚠️ [回撤平仓] 交易所持仓方向({exchange_side})与本地({pos.side})不符，"
                        f"清理本地虚假持仓 {pos.id}"
                    )
                    self.positions.remove(pos)
                    return True  # 返回True表示处理完成
            else:
                self.logger.warning(f"⚠️ [回撤平仓] 查询交易所持仓为空，清理本地虚假持仓")
                self.positions.remove(pos)
                return True
        except Exception as e:
            self.logger.error(f"❌ [回撤平仓] 查询交易所持仓失败: {e}")
            # 查询失败时继续尝试平仓

        # 市价全平
        close_side = 'SELL' if pos.side == 'long' else 'BUY'

        try:
            order = self.exchange.place_order(
                symbol=config.SYMBOL,
                side=close_side,
                order_type='MARKET',
                quantity=float(pos.contracts),
                price=None,
                business_order_type='CLOSE_RETREAT',
                trace_id=pos.trace_id,
                kline_close_time=str(ts),
                reduceOnly=True  # 🔑 关键：确保是平仓操作，不会开反向仓
            )

            # 如果市价单返回NEW状态，轮询等待成交
            if order.status.value == 'NEW':
                self.logger.info(f"⏳ [回撤平仓订单待成交] 订单 {order.order_id} 轮询等待...")
                poll_timeout = 10
                poll_interval = 0.5
                start_time = time.time()
                
                while time.time() - start_time < poll_timeout:
                    try:
                        queried_order = self.exchange.get_order(config.SYMBOL, order.order_id)
                        if queried_order and queried_order.status.value == 'FILLED':
                            order = queried_order
                            break
                        elif queried_order and queried_order.status.value in ['EXPIRED', 'REJECTED', 'CANCELED']:
                            order = queried_order
                            break
                    except Exception as poll_err:
                        self.logger.warning(f"轮询回撤平仓订单状态异常: {poll_err}")
                    time.sleep(poll_interval)

            if order.status.value == 'FILLED':
                actual_price = order.avg_price if order.avg_price > 0 else close_price
                self.logger.info(f"✅ 回撤市价单成交 @ {actual_price:.2f}")

                # 计算盈亏
                notional_usd = cn * pos.contracts
                if pos.side == 'long':
                    gross_pnl_btc = notional_usd * (1 / pos.entry_price - 1 / actual_price)
                else:
                    gross_pnl_btc = notional_usd * (1 / actual_price - 1 / pos.entry_price)

                fee_rate = config.TAKER_FEE_RATE
                fee_btc = (notional_usd * fee_rate) / actual_price
                net_btc = gross_pnl_btc - fee_btc

                # 更新已实现盈亏
                self.realized_pnl += net_btc

                # 记录日志
                self.record_log(
                    ts,
                    'CLOSE_RETREAT',
                    pos.side,
                    actual_price,
                    pos.contracts,
                    gross_pnl_btc,
                    f"止盈回撤全平 确认价={pos.tp_confirmed_price:.2f} 回撤价={pos.tp_drawdown_price:.2f}",
                    fee_rate,
                    fee_btc * actual_price
                )

                # 尝试获取真实的成交明细（手续费和实现盈亏）
                real_fee_btc = None
                real_pnl_btc = None
                trade_details = self._get_order_trade_details(order.order_id)
                real_fee_btc = trade_details.get('real_fee_btc')
                real_pnl_btc = trade_details.get('real_pnl_btc')

                # 关闭持仓
                self.close_position(pos, ts, actual_price, 'drawdown_close', net_btc, pnl_already_applied=True,
                                   real_fee_btc=real_fee_btc, real_pnl_btc=real_pnl_btc,
                                   close_order_id=str(order.order_id))
                return True
            else:
                self.logger.error(f"❌ 回撤市价单失败: {order.status.value}")
                return False

        except Exception as e:
            self.logger.error(f"❌ [回撤市价平仓异常] {e}", exc_info=True)
            return False

    def check_timeout(self, pos: Position, ts: pd.Timestamp,
                      price: float) -> bool:
        """
        检查超时强制平仓

        Args:
            pos: 持仓对象
            ts: 当前时间
            price: 当前价格

        Returns:
            bool: 是否超时平仓
        """
        # 统一时区处理：将两者都转换为 naive 时间戳
        ts_naive = ts.tz_localize(None) if ts.tzinfo is not None else ts
        entry_time_naive = (
            pos.entry_time.tz_localize(None) 
            if hasattr(pos.entry_time, 'tzinfo') and pos.entry_time.tzinfo is not None 
            else pos.entry_time
        )
        minutes_in_position = (ts_naive - entry_time_naive).total_seconds() / 60

        if (
            minutes_in_position >= config.CLOSE_TIME_MINUTES and
            not pos.tp_activated
        ):
            cn = config.CONTRACT_NOTIONAL
            notional_usd = cn * pos.contracts

            if pos.side == 'long':
                gross_pnl_btc = notional_usd * (
                    1 / pos.entry_price - 1 / price
                )
                gross_btc = notional_usd * (
                    2 / pos.entry_price - 1 / price
                )
            else:
                gross_pnl_btc = notional_usd * (
                    1 / price - 1 / pos.entry_price
                )
                gross_btc = notional_usd / price

            fee_rate = 0
            self.realized_pnl += gross_btc

            self.record_log(
                ts,
                'EOD_CLOSE',
                pos.side,
                price,
                pos.contracts,
                gross_pnl_btc,
                f"超时强制平仓 持仓{minutes_in_position:.0f}分钟",
                fee_rate,
                0
            )

            self.close_position(pos, ts, price, 'timeout_close', gross_btc, pnl_already_applied=True)
            return True

        return False

    def process_tick(self, ts, row: Dict, signal=None):
        """
        处理一个tick的数据

        Args:
            ts: 时间戳(pandas.Timestamp, str, or datetime)
            row: K线数据(包含价格和指标)
            signal: 交易信号(如果有)
        """
        # 转换时间戳为pandas.Timestamp
        if not isinstance(ts, pd.Timestamp):
            if isinstance(ts, str):
                ts = pd.to_datetime(ts)
            elif isinstance(ts, datetime):
                ts = pd.Timestamp(ts)
            else:
                try:
                    ts = pd.to_datetime(ts)
                except Exception as e:
                    self.logger.error(
                        f"无法转换时间戳: {ts}, 类型: {type(ts)}, 错误: {e}"
                    )
                    return

        # 📊 调试：针对特定时间添加详细日志
        ts_str = str(ts)
        debug_mode = '03:44' in ts_str or '19:39' in ts_str or '19:44' in ts_str

        # 【核心】每次处理K线前，先从交易所同步持仓，以交易所为准
        current_price = row.get('price', row.get('close'))
        try:
            self.sync_positions_from_exchange(ts, current_price)
        except Exception as sync_err:
            self.logger.warning(f"持仓同步失败: {sync_err}")
            
        # 定期巡检远端订单（挂单状态等）
        try:
            self._maybe_sync_remote_orders(ts, current_price)
        except Exception as sync_err:
            self.logger.warning(f"远端订单巡检失败: {sync_err}")

        if debug_mode:
            self.logger.info("=" * 80)
            self.logger.info(f"🔍 [process_tick] {ts_str}")
            self.logger.info(f"🔍 [process_tick] 信号={signal}")
            if signal:
                self.logger.info(f"🔍 [process_tick] 信号类型: {signal.action if hasattr(signal, 'action') else 'N/A'}")
                self.logger.info(f"🔍 [process_tick] 信号方向: {signal.side if hasattr(signal, 'side') else 'N/A'}")
                self.logger.info(f"🔍 [process_tick] 信号原因: {signal.reason if hasattr(signal, 'reason') else 'N/A'}")
            self.logger.info(f"🔍 [process_tick] 当前持仓数={len(self.positions)}")

        price = current_price
        high = row.get('high', price)
        low = row.get('low', price)

        # 📊 调试日志: 输出当前处理的数据行(每100条输出一次,或有信号时)
        self.processed_count += 1
        should_log = (
            self.processed_count % 100 == 0 or  # 每100条输出一次
            signal or  # 有信号时输出
            len(self.positions) > 0  # 有持仓时输出
        )

        if should_log:
            self.logger.debug("-" * 80)
            self.logger.debug(f"处理K线 #{self.processed_count} | 时间: {ts}")
            self.logger.debug(f"价格: {price:.2f} | 最高: {high:.2f} | 最低: {low:.2f}")
            if signal:
                self.logger.debug(f"信号: {signal.action} {signal.side if hasattr(signal, 'side') else ''}")
            if len(self.positions) > 0:
                self.logger.debug(f"当前持仓数: {len(self.positions)}")
                for idx, pos in enumerate(self.positions):
                    self.logger.debug(
                        f"  持仓{idx+1}: {pos.side} | "
                        f"入场={pos.entry_price:.2f} | "
                        f"数量={pos.contracts}张 | "
                        f"止盈级别={pos.tp_hit}"
                    )
            self.logger.debug("-" * 80)

        # 1. 处理现有持仓(止盈、止损、回撤、超时)
        positions_to_close = []
        for pos in self.positions:
            # 检查止盈
            if self.apply_take_profit(pos, ts, price, row):
                positions_to_close.append(pos)
                continue

            # 检查止损
            if self.check_stop_loss(pos, ts, price, high, low):
                positions_to_close.append(pos)
                continue

            # 检查回撤
            if self.check_drawdown(pos, ts, price, row):
                positions_to_close.append(pos)
                continue

            # 检查超时
            if self.check_timeout(pos, ts, price):
                positions_to_close.append(pos)
                continue

        # 2. 处理新开仓信号
        
        if not positions_to_close and not self.positions and signal and signal.action == 'open':
            self.signals_count += 1
            reason = (
                signal.reason if hasattr(signal, 'reason') else 'V5'
            )

            # 📊 输出当前数据行和信号信息
            self.logger.info("=" * 80)
            self.logger.info(f"📊 检测到开仓信号 #{self.signals_count}")
            self.logger.info(f"时间: {ts}")
            self.logger.info(f"信号方向: {signal.side}")
            self.logger.info(f"信号原因: {reason}")
            self.logger.info(f"当前价格: {price:.2f}")
            self.logger.info(f"最高价: {high:.2f}")
            self.logger.info(f"最低价: {low:.2f}")
            self.logger.info(f"可用资金: {self.realized_pnl:.6f} {self.display_asset}")
            self.logger.info(f"当前持仓数: {len(self.positions)}")
            # row已经是dict对象，直接输出
            if debug_mode:
                self.logger.info(f"K线数据键: {list(row.keys())}")
            if hasattr(signal, 'indicators') and signal.indicators:
                self.logger.info(f"指标数据: {signal.indicators}")
            self.logger.info("=" * 80)

            # 飞书开仓信号检测通知（仅表示检测到信号，尚未下单/成交）
            try:
                available_capital = max(0.0, self.realized_pnl - self.locked_capital)
                self.feishu_bot.send_open_signal_detected_notification(
                    symbol=config.SYMBOL,
                    side=signal.side,
                    close_price=row.get('close', price),
                    high_price=high,
                    low_price=low,
                    available_capital=available_capital,
                    capital_asset=self.display_asset,
                    signal_name=reason,
                    ts=ts.to_pydatetime() if hasattr(ts, 'to_pydatetime') else ts
                )
            except Exception as e:
                self.logger.warning(f"飞书开仓信号通知发送失败: {e}")

            # 🔍 调用开仓并记录结果
            success = self.open_position(ts, price, row, signal.side, reason)
            if not success:
                self.logger.error(f"❌❌❌ open_position() 返回 False - 开仓失败！时间: {ts}, 方向: {signal.side}, 价格: {price:.2f}")
            else:
                self.logger.info(f"✅ open_position() 返回 True - 开仓成功！")


    # ============================================================
    # 实时价格处理（用于socket推送）
    # ============================================================
