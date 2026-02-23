#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
币安交易数据同步脚本
从币安获取历史成交记录并同步到本地数据库
支持历史数据同步、断点续传
"""

import os
import sys
import time
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

from core.config import config
from core.logger import get_logger
from core.trade_recorder import get_trade_recorder, TradeRecord, PositionRecord
from core.database import get_db
from exchange_layer.exchange_factory import create_exchange

logger = get_logger('sync_trades')


class BinanceTradeSync:
    """币安交易数据同步器"""

    def __init__(self, exchange_type: str = None):
        """
        初始化同步器

        Args:
            exchange_type: 交易所类型，可选 'testnet'(模拟盘) 或 'live'(正式盘)
                           为None时从环境变量自动检测
        """
        from exchange_layer.exchange_factory import ExchangeType

        if exchange_type == 'testnet':
            self.exchange = create_exchange(ExchangeType.BINANCE_TESTNET)
            logger.info("使用币安模拟盘(Testnet)")
        elif exchange_type == 'live':
            self.exchange = create_exchange(ExchangeType.BINANCE_LIVE)
            logger.info("使用币安正式盘(Live)")
        else:
            self.exchange = create_exchange()
            logger.info(f"根据配置自动选择交易所: {self.exchange.__class__.__name__}")

        self.recorder = get_trade_recorder()
        self.db = get_db()
        self.symbol = config.SYMBOL

        # 同步状态文件
        self.sync_state_file = Path(__file__).parent.parent / 'data' / '.sync_state.json'
        self.sync_state = self._load_sync_state()

    def _load_sync_state(self) -> Dict[str, Any]:
        """加载同步状态（用于断点续传）"""
        if self.sync_state_file.exists():
            try:
                with open(self.sync_state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载同步状态失败: {e}")
        return {}

    def _save_sync_state(self):
        """保存同步状态"""
        try:
            self.sync_state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.sync_state_file, 'w') as f:
                json.dump(self.sync_state, f, indent=2)
        except Exception as e:
            logger.warning(f"保存同步状态失败: {e}")

    def sync_positions(self) -> Dict[str, Any]:
        """
        同步当前持仓信息从币安到本地数据库

        包括：
        1. 获取币安当前持仓
        2. 对比本地持仓状态
        3. 更新或创建本地持仓记录

        Returns:
            同步结果统计
        """
        try:
            # 确保已连接
            if not self.exchange.is_connected():
                if not self.exchange.connect():
                    logger.error("无法连接到币安交易所")
                    return {'success': False, 'error': '连接失败'}

            # 获取当前持仓
            position = self.exchange.get_position(self.symbol)

            if not position:
                logger.info("币安账户当前无持仓")
                # 检查本地是否有未关闭的持仓，标记为已关闭
                return self._check_and_close_local_positions()

            logger.info(f"获取到币安持仓: {position}")

            # 同步持仓到本地
            return self._sync_position_to_local(position)

        except Exception as e:
            logger.error(f"同步持仓失败: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _sync_position_to_local(self, position: Dict[str, Any]) -> Dict[str, Any]:
        """
        将币安持仓同步到本地数据库

        Args:
            position: 币安持仓信息

        Returns:
            同步结果
        """
        from core.trade_recorder import PositionRecord

        try:
            symbol = position.get('symbol', self.symbol)
            position_amount = float(position.get('position_amount', 0))

            if position_amount == 0:
                return {'success': True, 'synced': 0, 'updated': 0, 'closed': 0}

            # 确定持仓方向
            side = 'long' if position_amount > 0 else 'short'
            entry_price = float(position.get('entry_price', 0))
            contracts = abs(position_amount)

            # 生成 position_id（基于 symbol + side）
            position_id = f"{symbol}_{side}_BINANCE"

            # 检查本地是否已存在该持仓
            existing = self.recorder.get_positions(symbol=symbol, status='OPEN')
            existing_position = None
            for pos in existing:
                if pos.get('side') == side:
                    existing_position = pos
                    break

            # 构建 trace_id
            trace_id = f"BINANCE_SYNC_{position_id}_{int(datetime.now().timestamp())}"

            if existing_position:
                # 更新现有持仓
                position_record = PositionRecord(
                    position_id=existing_position.get('position_id', position_id),
                    trace_id=existing_position.get('trace_id', trace_id),
                    symbol=symbol,
                    side=side,
                    entry_price=entry_price,
                    entry_contracts=contracts,
                    open_time=existing_position.get('open_time', datetime.now().isoformat()),
                    status='OPEN'
                )

                # 更新持仓记录
                self._update_position_record(position_record)

                return {
                    'success': True,
                    'synced': 0,
                    'updated': 1,
                    'closed': 0,
                    'position_id': position_id
                }
            else:
                # 创建新持仓记录
                position_record = PositionRecord(
                    position_id=position_id,
                    trace_id=trace_id,
                    symbol=symbol,
                    side=side,
                    entry_price=entry_price,
                    entry_contracts=contracts,
                    open_time=datetime.now().isoformat(),
                    status='OPEN'
                )

                # 记录新持仓
                self.recorder.record_position_open(position_record)

                return {
                    'success': True,
                    'synced': 1,
                    'updated': 0,
                    'closed': 0,
                    'position_id': position_id
                }

        except Exception as e:
            logger.error(f"同步持仓到本地失败: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _check_and_close_local_positions(self) -> Dict[str, Any]:
        """
        检查本地未关闭的持仓，标记为已关闭
        （当币安账户无持仓时调用）

        Returns:
            关闭的持仓数量
        """
        try:
            # 获取本地所有未关闭的持仓
            open_positions = self.recorder.get_positions(symbol=self.symbol, status='OPEN')

            closed_count = 0
            for pos in open_positions:
                position_id = pos.get('position_id')
                if position_id:
                    # 标记为已关闭
                    self.recorder.record_position_close(
                        position_id=position_id,
                        exit_price=None,
                        exit_contracts=pos.get('entry_contracts', 0),
                        gross_pnl=None,
                        net_pnl=None,
                        exit_reason='SYNC_CLOSE'
                    )
                    closed_count += 1
                    logger.info(f"持仓已标记为关闭: {position_id}")

            return {
                'success': True,
                'synced': 0,
                'updated': 0,
                'closed': closed_count
            }

        except Exception as e:
            logger.error(f"检查并关闭本地持仓失败: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _update_position_record(self, position: PositionRecord):
        """
        更新本地持仓记录

        Args:
            position: 持仓记录对象
        """
        try:
            # 先删除旧记录
            self.db.execute(
                "DELETE FROM position_records WHERE position_id = ?",
                (position.position_id,)
            )

            # 插入新记录
            self.recorder.record_position_open(position)

        except Exception as e:
            logger.error(f"更新持仓记录失败: {e}")

    def sync_trades(self, start_time: datetime = None, end_time: datetime = None,
                    force_full: bool = False) -> Dict[str, Any]:
        """
        同步币安交易数据到本地

        Args:
            start_time: 开始时间
            end_time: 结束时间，默认现在
            force_full: 强制全量同步（忽略断点状态）

        Returns:
            同步结果统计
        """
        if not self.exchange.connect():
            logger.error("无法连接到币安交易所")
            return {'success': False, 'error': '连接失败'}

        # 默认时间范围
        if end_time is None:
            end_time = datetime.now()
        if start_time is None:
            # 如果是断点续传，从上次的进度开始
            if not force_full and self.sync_state.get('last_sync_time'):
                last_sync = datetime.fromisoformat(self.sync_state['last_sync_time'])
                start_time = last_sync - timedelta(hours=1)  # 多同步1小时确保不遗漏
                logger.info(f"断点续传: 从上次同步时间 {start_time} 开始")
            else:
                # 默认同步最近7天
                start_time = end_time - timedelta(days=7)

        logger.info(f"开始同步交易数据: {start_time} ~ {end_time}")

        try:
            # 1. 同步当前持仓信息
            position_result = self.sync_positions()
            if position_result.get('success'):
                logger.info(
                    f"持仓同步完成: 新增 {position_result.get('synced', 0)} 条, "
                    f"更新 {position_result.get('updated', 0)} 条, "
                    f"关闭 {position_result.get('closed', 0)} 条"
                )

            # 2. 分批获取交易数据（币安API限制，需要分批）
            all_trades = self._fetch_trades_batch(start_time, end_time)

            if not all_trades:
                logger.info("没有新的交易数据需要同步")
                # 更新同步状态
                self.sync_state['last_sync_time'] = end_time.isoformat()
                self.sync_state['last_sync_count'] = 0
                self._save_sync_state()
                return {'success': True, 'synced': 0, 'skipped': 0, 'total': 0}

            # 同步到本地数据库
            result = self._sync_to_local(all_trades)

            # 更新同步状态
            self.sync_state['last_sync_time'] = end_time.isoformat()
            self.sync_state['last_sync_count'] = result['synced']
            self.sync_state['total_synced'] = self.sync_state.get('total_synced', 0) + result['synced']
            self._save_sync_state()

            logger.info(
                f"同步完成: 新增 {result['synced']} 条, "
                f"跳过重复 {result['skipped']} 条, "
                f"总计获取 {len(all_trades)} 条"
            )

            return {
                'success': True,
                'synced': result['synced'],
                'skipped': result['skipped'],
                'total': len(all_trades),
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'positions': {
                    'synced': position_result.get('synced', 0),
                    'updated': position_result.get('updated', 0),
                    'closed': position_result.get('closed', 0)
                }
            }

        except Exception as e:
            logger.error(f"同步失败: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def sync_year_trades(self, year: int = 2026) -> Dict[str, Any]:
        """
        同步指定年份的所有交易数据

        Args:
            year: 年份，默认2026年

        Returns:
            同步结果统计
        """
        start_time = datetime(year, 1, 1, 0, 0, 0)
        end_time = datetime.now()

        # 如果今年还没结束，只同步到当前时间
        if year > datetime.now().year:
            logger.error(f"无法同步未来年份: {year}")
            return {'success': False, 'error': '不能同步未来年份'}

        logger.info(f"开始同步 {year} 年全年交易数据: {start_time} ~ {end_time}")

        # 币安 API 限制：每次最多返回 7 天的数据，最多 1000 条
        # 需要按时间段分批获取
        all_results = {
            'success': True,
            'synced': 0,
            'skipped': 0,
            'total': 0,
            'batches': []
        }

        current_start = start_time
        batch_size = timedelta(days=7)  # 币安API限制

        batch_num = 0
        while current_start < end_time:
            batch_num += 1
            current_end = min(current_start + batch_size, end_time)

            logger.info(f"=" * 60)
            logger.info(f"批次 {batch_num}: {current_start} ~ {current_end}")
            logger.info(f"=" * 60)

            try:
                result = self.sync_trades(current_start, current_end, force_full=True)
                all_results['batches'].append({
                    'batch': batch_num,
                    'start': current_start.isoformat(),
                    'end': current_end.isoformat(),
                    'result': result
                })

                if result['success']:
                    all_results['synced'] += result.get('synced', 0)
                    all_results['skipped'] += result.get('skipped', 0)
                    all_results['total'] += result.get('total', 0)
                else:
                    logger.error(f"批次 {batch_num} 同步失败: {result.get('error')}")
                    all_results['success'] = False

            except Exception as e:
                logger.error(f"批次 {batch_num} 异常: {e}")
                all_results['success'] = False

            # 移动到下一个时间段
            current_start = current_end

            # 避免触发API频率限制
            time.sleep(0.5)

        logger.info(f"=" * 60)
        logger.info(f"{year}年数据同步完成!")
        logger.info(f"  总新增: {all_results['synced']} 条")
        logger.info(f"  总跳过: {all_results['skipped']} 条")
        logger.info(f"  总处理: {all_results['total']} 条")
        logger.info(f"=" * 60)

        return all_results

    def _fetch_trades_batch(self, start_time: datetime, end_time: datetime) -> List[Dict]:
        """
        分批获取交易数据

        币安API限制:
        - 每次最多返回1000条
        - 时间范围建议不超过7天
        """
        all_trades = []

        try:
            # 使用 exchange 层的 get_user_trades 方法
            if hasattr(self.exchange, 'get_user_trades'):
                # 币安API限制最多1000条，如果数据量大需要分页
                limit = 1000
                from_id = None

                while True:
                    params = {
                        'symbol': self.symbol,
                        'limit': limit
                    }
                    if from_id:
                        params['fromId'] = from_id

                    trades = self.exchange.get_user_trades(**params)

                    if not trades:
                        break

                    # 过滤时间范围
                    for trade in trades:
                        trade_time_ms = trade.get('time', 0)
                        trade_time = datetime.fromtimestamp(trade_time_ms / 1000)

                        if start_time <= trade_time <= end_time:
                            all_trades.append(trade)
                        elif trade_time < start_time:
                            # 已经超出时间范围（按时间倒序）
                            return all_trades

                    # 如果返回数量不足limit，说明没有更多数据了
                    if len(trades) < limit:
                        break

                    # 使用最后一条的ID作为下一次的起始
                    from_id = trades[-1].get('id')
                    if not from_id:
                        break

                    # 避免触发频率限制
                    time.sleep(0.1)

            else:
                logger.error("交易所接口不支持 get_user_trades 方法")

        except Exception as e:
            logger.error(f"获取交易数据失败: {e}", exc_info=True)

        return all_trades

    def _sync_to_local(self, trades: List[Dict]) -> Dict[str, int]:
        """
        将币安交易数据同步到本地数据库

        优化：根据 realizedPnl 字段判断是开仓还是平仓
        - realizedPnl == 0: 开仓
        - realizedPnl != 0: 平仓（会产生盈亏）
        """
        synced = 0
        skipped = 0

        # 按订单ID分组，用于判断开仓/平仓
        order_trades: Dict[str, List[Dict]] = {}
        for trade in trades:
            order_id = str(trade.get('orderId', ''))
            if order_id not in order_trades:
                order_trades[order_id] = []
            order_trades[order_id].append(trade)

        for order_id, order_trade_list in order_trades.items():
            try:
                # 计算该订单的总实现盈亏
                total_realized_pnl = sum(
                    float(t.get('realizedPnl', 0) or 0)
                    for t in order_trade_list
                )

                # 判断是开仓还是平仓
                if total_realized_pnl == 0:
                    action = 'OPEN'
                    position_status = 'OPEN'
                else:
                    # 平仓时可能有多个成交记录
                    action = 'CLOSE'
                    position_status = 'CLOSED'

                # 处理该订单的所有成交
                for trade in order_trade_list:
                    record = self._convert_trade_format(trade, action)

                    if not record:
                        continue

                    # 写入数据库
                    if self.recorder.record_trade(record):
                        synced += 1
                    else:
                        skipped += 1

                # 如果是平仓，更新持仓记录
                if action == 'CLOSE' and order_trade_list:
                    self._update_position_close(order_trade_list, total_realized_pnl)

            except Exception as e:
                logger.warning(f"同步订单 {order_id} 失败: {e}")
                skipped += 1

        return {'synced': synced, 'skipped': skipped}

    def _convert_trade_format(self, trade: Dict, action: str = None) -> Optional[TradeRecord]:
        """
        将币安交易数据转换为本地格式

        Args:
            trade: 币安交易数据
            action: 动作类型（OPEN/CLOSE/TP/SL），如果为None则自动判断
        """
        try:
            # 解析时间
            trade_time_ms = trade.get('time', 0)
            trade_time = datetime.fromtimestamp(trade_time_ms / 1000).isoformat()

            # 确定交易方向
            is_buyer = trade.get('buyer', False)
            side = 'long' if is_buyer else 'short'

            # 确定动作类型
            if action is None:
                realized_pnl = float(trade.get('realizedPnl', 0) or 0)
                action = 'CLOSE' if realized_pnl != 0 else 'OPEN'

            # 确定具体的平仓原因
            if action == 'CLOSE':
                realized_pnl = float(trade.get('realizedPnl', 0) or 0)
                # 可以通过其他字段进一步判断是 TP/SL/手动平仓
                # 这里简化处理
                if realized_pnl > 0:
                    action = 'TP'
                elif realized_pnl < 0:
                    action = 'SL'

            # 计算手续费（USD）
            commission = float(trade.get('commission', 0))
            commission_asset = trade.get('commissionAsset', '')
            price = float(trade.get('price', 0))

            # 手续费转换
            if commission_asset in ['USD', 'USDT']:
                fee_usd = commission
            elif commission_asset == 'BTC':
                fee_usd = commission * price
            else:
                fee_usd = commission  # 默认直接使用

            # 盈亏信息
            realized_pnl = float(trade.get('realizedPnl', 0) or 0)

            return TradeRecord(
                trace_id=f"BINANCE_SYNC_{trade.get('orderId', '')}_{trade.get('id', '')}",
                trade_id=str(trade.get('id')),
                symbol=self.symbol,
                side=side,
                action=action,
                entry_price=price if action == 'OPEN' else None,
                exit_price=price if action != 'OPEN' else None,
                contracts=float(trade.get('qty', 0)),
                position_id=None,  # 需要通过订单关联查询
                order_id=str(trade.get('orderId', '')),
                fee_rate=None,  # 可以从 commission 反推
                fee_usd=fee_usd,
                gross_pnl=realized_pnl + fee_usd if realized_pnl != 0 else None,
                net_pnl=realized_pnl if realized_pnl != 0 else None,
                realized_pnl=realized_pnl if realized_pnl != 0 else None,
                source='exchange_api',
                trade_time=trade_time,
                notes=f"Synced from Binance API - Order:{trade.get('orderId', '')}"
            )

        except Exception as e:
            logger.warning(f"转换交易数据失败: {e}")
            return None

    def _update_position_close(self, trades: List[Dict], total_pnl: float):
        """
        更新持仓记录为关闭状态

        注意：这是简化实现，实际应该根据订单关联到对应的持仓
        """
        try:
            if not trades:
                return

            # 获取订单ID
            order_id = str(trades[0].get('orderId', ''))

            # 尝试找到对应的持仓
            # 简化处理：查找相同方向的最后一个未平仓持仓
            # 实际应该通过订单关联关系找到准确的持仓

            # 获取交易方向
            is_buyer = trades[0].get('buyer', False)
            side = 'long' if is_buyer else 'short'

            # 计算平仓信息
            total_qty = sum(float(t.get('qty', 0)) for t in trades)
            avg_price = sum(float(t.get('price', 0)) * float(t.get('qty', 0)) for t in trades) / total_qty if total_qty > 0 else 0

            # 记录平仓信息到 notes
            logger.info(
                f"检测到平仓 - 订单:{order_id}, "
                f"方向:{side}, 数量:{total_qty}, "
                f"均价:{avg_price:.2f}, 盈亏:{total_pnl:.8f}"
            )

        except Exception as e:
            logger.warning(f"更新持仓关闭状态失败: {e}")

    def sync_recent_trades(self, hours: int = 24) -> Dict[str, Any]:
        """同步最近N小时的交易"""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        return self.sync_trades(start_time, end_time)

    def auto_sync_loop(self, interval_minutes: int = 5):
        """
        自动同步循环

        Args:
            interval_minutes: 同步间隔（分钟）
        """
        logger.info(f"启动自动同步，间隔 {interval_minutes} 分钟")
        logger.info(f"同步交易对: {self.symbol}")

        while True:
            try:
                result = self.sync_recent_trades(hours=1)  # 同步最近1小时

                if result.get('success'):
                    logger.info(
                        f"自动同步完成: 新增 {result.get('synced', 0)} 条, "
                        f"跳过 {result.get('skipped', 0)} 条"
                    )
                else:
                    logger.error(f"自动同步失败: {result.get('error')}")

            except Exception as e:
                logger.error(f"自动同步异常: {e}")

            # 等待下一次同步
            time.sleep(interval_minutes * 60)

    def get_sync_summary(self) -> Dict[str, Any]:
        """获取同步汇总信息"""
        try:
            # 从数据库查询
            rows = self.db.fetchall("""
                SELECT
                    COUNT(*) as total_count,
                    SUM(CASE WHEN source = 'exchange_api' THEN 1 ELSE 0 END) as api_count,
                    SUM(CASE WHEN source = 'trade_engine' THEN 1 ELSE 0 END) as engine_count,
                    MAX(trade_time) as latest_trade
                FROM trade_records
            """)

            if rows:
                row = rows[0]
                return {
                    'total_trades': row['total_count'],
                    'from_api': row['api_count'],
                    'from_engine': row['engine_count'],
                    'latest_trade': row['latest_trade'],
                    'last_sync': self.sync_state.get('last_sync_time'),
                    'total_synced': self.sync_state.get('total_synced', 0)
                }
        except Exception as e:
            logger.warning(f"获取同步汇总失败: {e}")

        return {
            'total_trades': 0,
            'from_api': 0,
            'from_engine': 0,
            'latest_trade': None,
            'last_sync': self.sync_state.get('last_sync_time'),
            'total_synced': self.sync_state.get('total_synced', 0)
        }


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='币安交易数据同步工具')
    parser.add_argument('--start', type=str, help='开始时间 (YYYY-MM-DD HH:MM:SS)')
    parser.add_argument('--end', type=str, help='结束时间 (YYYY-MM-DD HH:MM:SS)')
    parser.add_argument('--hours', type=int, default=24, help='同步最近N小时')
    parser.add_argument('--year', type=int, help='同步指定年份的所有数据 (如: 2026)')
    parser.add_argument('--daemon', action='store_true', help='后台自动同步模式')
    parser.add_argument('--interval', type=int, default=5, help='自动同步间隔（分钟）')
    parser.add_argument('--summary', action='store_true', help='显示同步汇总信息')
    parser.add_argument('--force-full', action='store_true', help='强制全量同步（忽略断点）')
    parser.add_argument('--testnet', action='store_true', help='使用币安模拟盘(Testnet)')
    parser.add_argument('--live', action='store_true', help='使用币安正式盘(Live)')
    parser.add_argument('--sync-positions', action='store_true',
                        help='仅同步持仓信息，不同步交易记录')

    args = parser.parse_args()

    # 确定交易所类型
    exchange_type = None
    if args.testnet and args.live:
        logger.error("不能同时使用 --testnet 和 --live，请选择一个")
        sys.exit(1)
    elif args.testnet:
        exchange_type = 'testnet'
    elif args.live:
        exchange_type = 'live'

    sync = BinanceTradeSync(exchange_type=exchange_type)

    if args.summary:
        # 显示汇总信息
        summary = sync.get_sync_summary()
        print("\n===== 交易数据同步汇总 =====")
        print(f"数据库总记录数: {summary['total_trades']}")
        print(f"  - 来自API同步: {summary['from_api']}")
        print(f"  - 来自交易引擎: {summary['from_engine']}")
        print(f"最新交易时间: {summary['latest_trade'] or 'N/A'}")
        print(f"上次同步时间: {summary['last_sync'] or 'N/A'}")
        print(f"累计同步数量: {summary['total_synced']}")
        print("=" * 30)
        return

    if args.daemon:
        # 后台自动同步模式
        sync.auto_sync_loop(interval_minutes=args.interval)
    elif args.year:
        # 同步整年数据
        result = sync.sync_year_trades(year=args.year)

        print(f"\n{'='*60}")
        print(f"{args.year}年数据同步结果:")
        print(f"{'='*60}")
        print(f"成功: {'是' if result['success'] else '否'}")
        print(f"总新增: {result.get('synced', 0)} 条")
        print(f"总跳过: {result.get('skipped', 0)} 条")
        print(f"总处理: {result.get('total', 0)} 条")
        print(f"批次数: {len(result.get('batches', []))}")
        print(f"{'='*60}")

        if not result['success']:
            sys.exit(1)
    elif args.sync_positions:
        # 仅同步持仓信息
        result = sync.sync_positions()

        print(f"\n{'='*40}")
        if result['success']:
            print("持仓同步成功!")
            print(f"  新增: {result.get('synced', 0)} 条")
            print(f"  更新: {result.get('updated', 0)} 条")
            print(f"  关闭: {result.get('closed', 0)} 条")
            if result.get('position_id'):
                print(f"  持仓ID: {result['position_id']}")
        else:
            print(f"持仓同步失败: {result.get('error')}")
            sys.exit(1)
        print(f"{'='*40}")
    else:
        # 单次同步模式
        if args.start and args.end:
            start = datetime.strptime(args.start, '%Y-%m-%d %H:%M:%S')
            end = datetime.strptime(args.end, '%Y-%m-%d %H:%M:%S')
            result = sync.sync_trades(start, end, force_full=args.force_full)
        else:
            result = sync.sync_recent_trades(hours=args.hours)

        # 打印结果
        print(f"\n{'='*40}")
        if result['success']:
            print("同步成功!")
            print(f"  新增: {result.get('synced', 0)} 条")
            print(f"  跳过: {result.get('skipped', 0)} 条")
            print(f"  总计: {result.get('total', 0)} 条")
            if 'start_time' in result:
                print(f"  时间: {result['start_time']} ~ {result['end_time']}")
        else:
            print(f"同步失败: {result.get('error')}")
            sys.exit(1)
        print(f"{'='*40}")


if __name__ == '__main__':
    main()
