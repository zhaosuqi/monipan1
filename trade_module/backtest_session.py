#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测会话管理器 - 按时间阶段划分回测任务
支持按天/周/月进行会话划分，每个会话独立统计
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pandas as pd
import glob
import os

from core.logger import get_logger
from core.config import config


@dataclass
class BacktestSession:
    """回测会话"""
    session_id: str
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    klines: List[Dict] = field(default_factory=list)

    # 会话统计
    signals_detected: int = 0
    positions_opened: int = 0
    trades_completed: int = 0

    # 资金状态
    initial_capital: float = 0.0
    final_capital: float = 0.0
    pnl: float = 0.0

    # 会话状态
    status: str = "pending"  # pending, running, completed, failed

    def __post_init__(self):
        if not self.session_id:
            self.session_id = str(uuid.uuid4())


class BacktestSessionManager:
    """回测会话管理器"""

    def __init__(self):
        self.logger = get_logger('trade_module.session_manager')
        self.sessions: List[BacktestSession] = []
        self.current_session: Optional[BacktestSession] = None

    def clear_logs(self):
        """
        清除 ./data/logs 目录下的所有日志文件
        """
        logs_dir = os.path.join(os.getcwd(), 'data', 'logs')

        if not os.path.exists(logs_dir):
            self.logger.info(f"日志目录不存在: {logs_dir}")
            return

        # 获取所有日志文件
        log_files = glob.glob(os.path.join(logs_dir, '*.log*'))

        if not log_files:
            self.logger.info("日志目录为空，无需清理")
            return

        # 删除所有日志文件
        deleted_count = 0
        for log_file in log_files:
            try:
                os.remove(log_file)
                deleted_count += 1
                self.logger.debug(f"已删除日志文件: {os.path.basename(log_file)}")
            except Exception as e:
                self.logger.error(f"删除日志文件失败 {log_file}: {e}")

        self.logger.info(f"✓ 已清除 {deleted_count} 个日志文件")

    def split_by_day(self, klines: List[Dict]) -> List[BacktestSession]:
        """
        按天划分K线数据为多个会话

        Args:
            klines: K线数据列表

        Returns:
            List[BacktestSession]: 会话列表
        """
        # 每日运行回测时清除日志
        self.clear_logs()

        if not klines:
            return []

        # 按日期分组
        grouped = {}
        for kline in klines:
            ts = kline.get('open_time')
            if isinstance(ts, str):
                ts = pd.to_datetime(ts)

            date_key = ts.date()
            if date_key not in grouped:
                grouped[date_key] = []

            grouped[date_key].append(kline)

        # 创建会话
        sessions = []
        for date, klines_list in sorted(grouped.items()):
            session = BacktestSession(
                session_id=f"day_{date.strftime('%Y%m%d')}",
                start_time=pd.to_datetime(date),
                end_time=pd.to_datetime(date) + timedelta(days=1) - timedelta(seconds=1),
                klines=klines_list,
                status="pending"
            )
            sessions.append(session)

        self.logger.info(f"按天划分为 {len(sessions)} 个会话")
        return sessions

    def split_by_week(self, klines: List[Dict]) -> List[BacktestSession]:
        """
        按周划分K线数据为多个会话

        Args:
            klines: K线数据列表

        Returns:
            List[BacktestSession]: 会话列表
        """
        if not klines:
            return []

        # 按周分组
        grouped = {}
        for kline in klines:
            ts = kline.get('open_time')
            if isinstance(ts, str):
                ts = pd.to_datetime(ts)

            # 获取周的周一作为key
            week_start = ts - timedelta(days=ts.weekday())
            week_key = week_start.date()

            if week_key not in grouped:
                grouped[week_key] = []

            grouped[week_key].append(kline)

        # 创建会话
        sessions = []
        for week_start, klines_list in sorted(grouped.items()):
            week_end = week_start + timedelta(days=6)
            session = BacktestSession(
                session_id=f"week_{week_start.strftime('%Y%m%d')}",
                start_time=pd.to_datetime(week_start),
                end_time=pd.to_datetime(week_end) + timedelta(days=1) - timedelta(seconds=1),
                klines=klines_list,
                status="pending"
            )
            sessions.append(session)

        self.logger.info(f"按周划分为 {len(sessions)} 个会话")
        return sessions

    def split_by_month(self, klines: List[Dict]) -> List[BacktestSession]:
        """
        按月划分K线数据为多个会话

        Args:
            klines: K线数据列表

        Returns:
            List[BacktestSession]: 会话列表
        """
        if not klines:
            return []

        # 按月分组
        grouped = {}
        for kline in klines:
            ts = kline.get('open_time')
            if isinstance(ts, str):
                ts = pd.to_datetime(ts)

            month_key = (ts.year, ts.month)
            if month_key not in grouped:
                grouped[month_key] = []

            grouped[month_key].append(kline)

        # 创建会话
        sessions = []
        for (year, month), klines_list in sorted(grouped.items()):
            # 计算月份的开始和结束
            month_start = pd.to_datetime(f"{year}-{month:02d}-01")
            if month == 12:
                month_end = pd.to_datetime(f"{year+1}-01-01") - timedelta(seconds=1)
            else:
                month_end = pd.to_datetime(f"{year}-{month+1:02d}-01") - timedelta(seconds=1)

            session = BacktestSession(
                session_id=f"month_{year}{month:02d}",
                start_time=month_start,
                end_time=month_end,
                klines=klines_list,
                status="pending"
            )
            sessions.append(session)

        self.logger.info(f"按月划分为 {len(sessions)} 个会话")
        return sessions

    def split_by_custom(self, klines: List[Dict],
                       interval_hours: int = 24) -> List[BacktestSession]:
        """
        按自定义时间间隔划分K线数据

        Args:
            klines: K线数据列表
            interval_hours: 时间间隔(小时)

        Returns:
            List[BacktestSession]: 会话列表
        """
        if not klines:
            return []

        # 获取起始时间
        first_ts = klines[0].get('open_time')
        if isinstance(first_ts, str):
            first_ts = pd.to_datetime(first_ts)

        # 按时间间隔分组
        grouped = {}
        for kline in klines:
            ts = kline.get('open_time')
            if isinstance(ts, str):
                ts = pd.to_datetime(ts)

            # 计算所属的时间段
            delta = ts - first_ts
            interval_index = int(delta.total_seconds() // (interval_hours * 3600))

            if interval_index not in grouped:
                grouped[interval_index] = {
                    'start': first_ts + timedelta(hours=interval_index * interval_hours),
                    'klines': []
                }

            grouped[interval_index]['klines'].append(kline)

        # 创建会话
        sessions = []
        for interval_idx in sorted(grouped.keys()):
            info = grouped[interval_idx]
            session_start = info['start']
            session_end = session_start + timedelta(hours=interval_hours) - timedelta(seconds=1)

            session = BacktestSession(
                session_id=f"interval_{interval_idx:03d}",
                start_time=session_start,
                end_time=session_end,
                klines=info['klines'],
                status="pending"
            )
            sessions.append(session)

        self.logger.info(f"按{interval_hours}小时划分为 {len(sessions)} 个会话")
        return sessions

    def run_session(self, session: BacktestSession,
                    trade_engine,
                    signal_calculator,
                    socketio=None,
                    bot_state=None):
        """
        运行单个会话

        Args:
            session: 会话对象
            trade_engine: 交易引擎
            signal_calculator: 信号计算器
            socketio: SocketIO实例(可选)
            bot_state: 机器人状态(可选)

        Returns:
            Dict: 会话统计结果
        """
        self.current_session = session
        session.status = "running"

        self.logger.info("")
        self.logger.info("=" * 60)
        self.logger.info(f"开始会话: {session.session_id}")
        self.logger.info(f"时间范围: {session.start_time} ~ {session.end_time}")
        self.logger.info(f"K线数量: {len(session.klines)}")
        self.logger.info("=" * 60)

        # 记录会话初始资金
        session.initial_capital = trade_engine.realized_pnl

        buy_signals = 0
        sell_signals = 0

        try:
            for i, kline in enumerate(session.klines):
                # 检查是否应该停止
                if bot_state and not bot_state.get('running', True):
                    self.logger.info(f"会话 {session.session_id} 被用户停止")
                    session.status = "failed"
                    return None

                # 每100条记录一次日志
                if i % 100 == 0:
                    stats = trade_engine.get_statistics()
                    self.logger.info(
                        f"  会话 {session.session_id} | "
                        f"已处理 {i}/{len(session.klines)} | "
                        f"信号: {buy_signals}多/{sell_signals}空 | "
                        f"资金: {stats['final_capital_btc']:.6f} BTC"
                    )

                    # 更新进度到前端
                    if socketio:
                        socketio.emit('session_progress', {
                            'session_id': session.session_id,
                            'processed': i,
                            'total': len(session.klines),
                            'buy_signals': buy_signals,
                            'sell_signals': sell_signals,
                            'current_capital': stats['final_capital_btc']
                        })

                try:
                    # 计算交易信号
                    signal = signal_calculator.calculate_open_signal(kline)

                    # 发送开仓信号到前端用于图表标记
                    if signal and signal.action == 'open' and socketio:
                        signal_type = 'buy' if signal.side == 'long' else 'sell'
                        socketio.emit('trade_signal', {
                            'type': signal_type,
                            'timestamp': str(kline.get('open_time')),
                            'price': float(kline.get('close', 0)),
                            'side': signal.side
                        })

                    # 统计信号
                    if signal and signal.action == 'open':
                        session.signals_detected += 1
                        if signal.side == 'long':
                            buy_signals += 1
                        else:
                            sell_signals += 1

                    # 使用交易引擎处理tick
                    tick_data = dict(kline)
                    if 'open_time' in tick_data:
                        tick_data['ts'] = tick_data['open_time']

                    # 记录处理前的持仓数量,用于检测是否有平仓
                    positions_before = len(trade_engine.positions)

                    trade_engine.process_tick(
                        ts=tick_data.get('ts'),
                        row=tick_data,
                        signal=signal
                    )

                    # 检测是否有平仓,发送平仓信号到前端
                    positions_after = len(trade_engine.positions)
                    if positions_after < positions_before and socketio:
                        # 有平仓发生,从最近的交易日志中获取平仓信息
                        if trade_engine.trades:
                            last_trade = trade_engine.trades[-1]
                            socketio.emit('trade_signal', {
                                'type': 'close',
                                'timestamp': str(last_trade.exit_time),
                                'price': float(last_trade.exit_price),
                                'side': last_trade.side,
                                'pnl': float(last_trade.net_pnl)
                            })

                except Exception as e:
                    self.logger.error(f"处理K线失败 (索引 {i}): {e}")
                    import traceback
                    traceback.print_exc()

            # 会话完成
            session.status = "completed"
            session.final_capital = trade_engine.realized_pnl
            session.pnl = session.final_capital - session.initial_capital

            # 获取统计信息
            stats = trade_engine.get_statistics()
            session.positions_opened = stats['positions_opened'] - session.positions_opened
            session.trades_completed = stats['total_trades']

            self.logger.info("")
            self.logger.info(f"✓ 会话 {session.session_id} 完成")
            self.logger.info(f"  盈亏: {session.pnl:.6f} BTC")
            self.logger.info(f"  信号: {session.signals_detected}个")
            self.logger.info(f"  当前资金: {session.final_capital:.6f} BTC")
            self.logger.info("=" * 60)

            return {
                'session_id': session.session_id,
                'status': session.status,
                'pnl': session.pnl,
                'initial_capital': session.initial_capital,
                'final_capital': session.final_capital,
                'signals_detected': session.signals_detected,
            }

        except Exception as e:
            self.logger.error(f"会话 {session.session_id} 执行失败: {e}")
            import traceback
            traceback.print_exc()
            session.status = "failed"
            return None

        finally:
            self.current_session = None

    def run_all_sessions(self, sessions: List[BacktestSession],
                         trade_engine,
                         signal_calculator,
                         socketio=None,
                         bot_state=None):
        """
        运行所有会话

        Args:
            sessions: 会话列表
            trade_engine: 交易引擎
            signal_calculator: 信号计算器
            socketio: SocketIO实例(可选)
            bot_state: 机器人状态(可选)

        Returns:
            List[Dict]: 所有会话的统计结果
        """
        self.sessions = sessions
        results = []

        total_sessions = len(sessions)
        self.logger.info("")
        self.logger.info("=" * 60)
        self.logger.info(f"开始批量回测 - 共 {total_sessions} 个会话")
        self.logger.info("=" * 60)

        for idx, session in enumerate(sessions):
            self.logger.info(f"\n进度: [{idx+1}/{total_sessions}]")

            result = self.run_session(
                session=session,
                trade_engine=trade_engine,
                signal_calculator=signal_calculator,
                socketio=socketio,
                bot_state=bot_state
            )

            if result:
                results.append(result)

            # 检查是否应该停止
            if bot_state and not bot_state.get('running', True):
                self.logger.info("批量回测被用户停止")
                break

        # 打印总体统计
        self.logger.info("")
        self.logger.info("=" * 60)
        self.logger.info("批量回测完成")
        self.logger.info("=" * 60)

        if results:
            total_pnl = sum(r['pnl'] for r in results)
            total_signals = sum(r['signals_detected'] for r in results)
            completed_sessions = len(results)

            self.logger.info(f"完成会话: {completed_sessions}/{total_sessions}")
            self.logger.info(f"总盈亏: {total_pnl:.6f} BTC")
            self.logger.info(f"总信号: {total_signals}个")

        return results

    def print_session_summary(self, sessions: List[BacktestSession]):
        """打印会话摘要"""
        self.logger.info("")
        self.logger.info("=" * 80)
        self.logger.info("会话统计摘要")
        self.logger.info("=" * 80)

        for session in sessions:
            status_icon = {
                'pending': '○',
                'running': '◐',
                'completed': '●',
                'failed': '✗'
            }.get(session.status, '?')

            self.logger.info(
                f"{status_icon} {session.session_id} | "
                f"{session.start_time.strftime('%Y-%m-%d %H:%M')} ~ "
                f"{session.end_time.strftime('%Y-%m-%d %H:%M')} | "
                f"K线: {len(session.klines)}条 | "
                f"信号: {session.signals_detected}个 | "
                f"盈亏: {session.pnl:.6f} BTC | "
                f"状态: {session.status}"
            )

        self.logger.info("=" * 80)
