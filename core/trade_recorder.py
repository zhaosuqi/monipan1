#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易记录器模块 - 统一记录所有交易行为
支持trade模块和非trade模块（交易所API、手动操作等）发起的交易
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.database import get_db
from core.logger import get_logger


@dataclass
class TradeRecord:
    """交易记录数据类"""
    trace_id: str
    side: str  # 'long' or 'short'
    action: str  # 'OPEN', 'CLOSE', 'TP', 'SL', 'PARTIAL_CLOSE', etc.
    contracts: float
    trade_time: str
    trade_id: str = None
    symbol: str = 'BTCUSD_PERP'
    entry_price: float = None
    exit_price: float = None
    position_id: str = None
    order_id: str = None
    fee_rate: float = None
    fee_usd: float = None
    gross_pnl: float = None
    net_pnl: float = None
    realized_pnl: float = None
    balance_before: float = None
    balance_after: float = None
    source: str = 'trade_engine'  # 'trade_engine', 'exchange_api', 'manual', 'sync'
    kline_open_time: str = None
    kline_close_time: str = None
    notes: str = None


@dataclass
class PositionRecord:
    """持仓记录数据类"""
    position_id: str
    trace_id: str
    symbol: str
    side: str
    entry_price: float
    entry_contracts: float
    open_time: str
    exit_price: float = None
    exit_contracts: float = 0
    close_time: str = None
    status: str = 'OPEN'  # 'OPEN', 'CLOSED', 'PARTIAL'
    total_fee_usd: float = 0
    gross_pnl: float = None
    net_pnl: float = None
    exit_reason: str = None
    entry_order_id: str = None
    exit_order_id: str = None
    tp_levels_hit: str = None


class TradeRecorder:
    """交易记录器 - 统一管理交易数据的记录和查询"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if TradeRecorder._initialized:
            return

        self.logger = get_logger('core.trade_recorder')
        self.db = get_db()

        TradeRecorder._initialized = True

    def record_trade(self, record: TradeRecord) -> bool:
        """
        记录一笔交易

        Args:
            record: 交易记录对象

        Returns:
            bool: 是否成功
        """
        try:
            # 生成trade_id（如果未提供）
            if not record.trade_id:
                record.trade_id = f"TRD-{uuid.uuid4().hex[:12].upper()}"

            with self.db.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO trade_records (
                        trace_id, trade_id, symbol, side, action,
                        entry_price, exit_price, contracts,
                        position_id, order_id,
                        fee_rate, fee_usd,
                        gross_pnl, net_pnl, realized_pnl,
                        balance_before, balance_after,
                        source,
                        kline_open_time, kline_close_time,
                        trade_time, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record.trace_id, record.trade_id, record.symbol, record.side,
                    record.action, record.entry_price, record.exit_price, record.contracts,
                    record.position_id, record.order_id,
                    record.fee_rate, record.fee_usd,
                    record.gross_pnl, record.net_pnl, record.realized_pnl,
                    record.balance_before, record.balance_after,
                    record.source,
                    record.kline_open_time, record.kline_close_time,
                    record.trade_time, record.notes
                ))
                conn.commit()

            self.logger.info(
                f"✓ 交易已记录 [{record.source}] "
                f"{record.action} {record.side} "
                f"{record.contracts}张"
                + (f" PnL={record.net_pnl:.4f}" if record.net_pnl else "")
            )
            return True

        except Exception as e:
            self.logger.error(f"❌ 记录交易失败: {e}", exc_info=True)
            return False

    def record_position_open(self, position: PositionRecord) -> bool:
        """
        记录开仓（新持仓开始）

        Args:
            position: 持仓记录对象

        Returns:
            bool: 是否成功
        """
        try:
            with self.db.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO position_records (
                        position_id, trace_id, symbol, side,
                        entry_price, entry_contracts, open_time,
                        status, entry_order_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    position.position_id, position.trace_id, position.symbol,
                    position.side, position.entry_price, position.entry_contracts,
                    position.open_time, 'OPEN', position.entry_order_id
                ))
                conn.commit()

            self.logger.info(
                f"✓ 持仓已记录 OPEN [{position.position_id}] "
                f"{position.side} {position.entry_contracts}张@{position.entry_price:.2f}"
            )
            return True

        except Exception as e:
            self.logger.error(f"❌ 记录持仓失败: {e}", exc_info=True)
            return False

    def record_position_close(
        self,
        position_id: str,
        exit_price: float,
        exit_contracts: float,
        close_time: str,
        exit_reason: str,
        total_fee: float = 0,
        gross_pnl: float = None,
        net_pnl: float = None,
        exit_order_id: str = None,
        tp_levels_hit: str = None
    ) -> bool:
        """
        记录平仓（持仓结束）

        Args:
            position_id: 持仓ID
            exit_price: 平仓价格
            exit_contracts: 平仓张数
            close_time: 平仓时间
            exit_reason: 平仓原因
            total_fee: 总手续费
            gross_pnl: 毛盈亏
            net_pnl: 净盈亏
            exit_order_id: 平仓订单ID
            tp_levels_hit: 触发的止盈级别

        Returns:
            bool: 是否成功
        """
        try:
            with self.db.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE position_records
                    SET exit_price = ?,
                        exit_contracts = ?,
                        close_time = ?,
                        status = 'CLOSED',
                        total_fee_usd = ?,
                        gross_pnl = ?,
                        net_pnl = ?,
                        exit_reason = ?,
                        exit_order_id = ?,
                        tp_levels_hit = ?,
                        updated_at = ?
                    WHERE position_id = ?
                """, (
                    exit_price, exit_contracts, close_time,
                    total_fee, gross_pnl, net_pnl,
                    exit_reason, exit_order_id, tp_levels_hit,
                    datetime.now().isoformat(), position_id
                ))
                conn.commit()

            self.logger.info(
                f"✓ 持仓已关闭 [{position_id}] "
                f"原因:{exit_reason} "
                + (f"PnL={net_pnl:.4f}" if net_pnl else "")
            )
            return True

        except Exception as e:
            self.logger.error(f"❌ 更新持仓关闭失败: {e}", exc_info=True)
            return False

    def get_trades(
        self,
        symbol: str = None,
        side: str = None,
        action: str = None,
        source: str = None,
        start_time: str = None,
        end_time: str = None,
        position_id: str = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        查询交易记录

        Args:
            symbol: 交易对
            side: 方向 'long'/'short'
            action: 动作类型
            source: 来源
            start_time: 开始时间
            end_time: 结束时间
            position_id: 持仓ID
            limit: 限制数量

        Returns:
            List[Dict]: 交易记录列表
        """
        try:
            conditions = []
            params = []

            if symbol:
                conditions.append("symbol = ?")
                params.append(symbol)
            if side:
                conditions.append("side = ?")
                params.append(side)
            if action:
                conditions.append("action = ?")
                params.append(action)
            if source:
                conditions.append("source = ?")
                params.append(source)
            if position_id:
                conditions.append("position_id = ?")
                params.append(position_id)
            if start_time:
                conditions.append("trade_time >= ?")
                params.append(start_time)
            if end_time:
                conditions.append("trade_time <= ?")
                params.append(end_time)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            sql = f"""
                SELECT * FROM trade_records
                WHERE {where_clause}
                ORDER BY trade_time DESC
                LIMIT ?
            """
            params.append(limit)

            rows = self.db.fetchall(sql, tuple(params))

            return [dict(row) for row in rows]

        except Exception as e:
            self.logger.error(f"查询交易记录失败: {e}")
            return []

    def get_positions(
        self,
        symbol: str = None,
        side: str = None,
        status: str = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        查询持仓记录

        Args:
            symbol: 交易对
            side: 方向
            status: 状态 'OPEN'/'CLOSED'/'PARTIAL'
            limit: 限制数量

        Returns:
            List[Dict]: 持仓记录列表
        """
        try:
            conditions = []
            params = []

            if symbol:
                conditions.append("symbol = ?")
                params.append(symbol)
            if side:
                conditions.append("side = ?")
                params.append(side)
            if status:
                conditions.append("status = ?")
                params.append(status)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            sql = f"""
                SELECT * FROM position_records
                WHERE {where_clause}
                ORDER BY open_time DESC
                LIMIT ?
            """
            params.append(limit)

            rows = self.db.fetchall(sql, tuple(params))

            return [dict(row) for row in rows]

        except Exception as e:
            self.logger.error(f"查询持仓记录失败: {e}")
            return []

    def get_open_positions(self, symbol: str = None) -> List[Dict[str, Any]]:
        """获取未平仓持仓"""
        return self.get_positions(symbol=symbol, status='OPEN', limit=10)

    def get_trade_summary(self, start_time: str = None, end_time: str = None) -> Dict[str, Any]:
        """
        获取交易汇总统计

        Args:
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            Dict: 统计信息
        """
        try:
            conditions = ["status = 'CLOSED'"]
            params = []

            if start_time:
                conditions.append("close_time >= ?")
                params.append(start_time)
            if end_time:
                conditions.append("close_time <= ?")
                params.append(end_time)

            where_clause = " AND ".join(conditions)

            # 总体统计
            row = self.db.fetchone(f"""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as win_count,
                    SUM(CASE WHEN net_pnl < 0 THEN 1 ELSE 0 END) as loss_count,
                    SUM(net_pnl) as total_pnl,
                    SUM(gross_pnl) as total_gross_pnl,
                    SUM(total_fee_usd) as total_fees,
                    AVG(net_pnl) as avg_pnl,
                    MAX(net_pnl) as max_pnl,
                    MIN(net_pnl) as min_pnl
                FROM position_records
                WHERE {where_clause}
            """, tuple(params))

            summary = dict(row) if row else {}

            # 按方向统计
            side_rows = self.db.fetchall(f"""
                SELECT
                    side,
                    COUNT(*) as count,
                    SUM(net_pnl) as pnl
                FROM position_records
                WHERE {where_clause}
                GROUP BY side
            """, tuple(params))

            summary['by_side'] = {r['side']: dict(r) for r in side_rows}

            return summary

        except Exception as e:
            self.logger.error(f"获取交易汇总失败: {e}")
            return {}

    def sync_from_exchange_trade(
        self,
        trade_data: Dict[str, Any],
        source: str = 'exchange_api'
    ) -> bool:
        """
        从交易所交易数据同步记录
        用于记录非trade模块发起的交易

        Args:
            trade_data: 交易所返回的交易数据
            source: 数据来源

        Returns:
            bool: 是否成功
        """
        try:
            # 解析交易所数据
            trade_id = trade_data.get('id') or trade_data.get('tradeId')
            order_id = trade_data.get('orderId')
            symbol = trade_data.get('symbol', 'BTCUSD_PERP')
            side = 'long' if trade_data.get('side') == 'BUY' else 'short'
            price = float(trade_data.get('price', 0))
            qty = float(trade_data.get('qty') or trade_data.get('quantity', 0))
            commission = float(trade_data.get('commission', 0))
            commission_asset = trade_data.get('commissionAsset', 'USDT')
            trade_time_ms = trade_data.get('time', 0)

            # 转换时间
            if trade_time_ms:
                trade_time = datetime.fromtimestamp(trade_time_ms / 1000).isoformat()
            else:
                trade_time = datetime.now().isoformat()

            # 生成trace_id（如果订单有关联的话需要查询已有trace_id）
            trace_id = self._get_trace_id_by_order(order_id) or str(uuid.uuid4())

            # 创建交易记录
            record = TradeRecord(
                trace_id=trace_id,
                trade_id=str(trade_id),
                symbol=symbol,
                side=side,
                action='OPEN' if trade_data.get('isBuyer') else 'CLOSE',
                exit_price=price,
                contracts=qty,
                order_id=str(order_id),
                fee_usd=commission if commission_asset in ['USDT', 'USD'] else 0,
                source=source,
                trade_time=trade_time,
                notes=f"Synced from {source}"
            )

            return self.record_trade(record)

        except Exception as e:
            self.logger.error(f"同步交易所交易失败: {e}", exc_info=True)
            return False

    def _get_trace_id_by_order(self, order_id: str) -> Optional[str]:
        """根据订单ID查询已有的trace_id"""
        try:
            row = self.db.fetchone(
                "SELECT trace_id FROM orders WHERE order_id = ?",
                (order_id,)
            )
            return row['trace_id'] if row else None
        except:
            return None

    def record_from_trade_engine(
        self,
        trace_id: str,
        action: str,
        side: str,
        contracts: float,
        trade_time: str,
        entry_price: float = None,
        exit_price: float = None,
        position_id: str = None,
        order_id: str = None,
        fee_rate: float = None,
        fee_usd: float = None,
        gross_pnl: float = None,
        net_pnl: float = None,
        realized_pnl: float = None,
        balance_before: float = None,
        balance_after: float = None,
        kline_close_time: str = None,
        notes: str = None
    ) -> bool:
        """
        便捷方法：从trade_engine直接记录交易
        """
        record = TradeRecord(
            trace_id=trace_id,
            side=side,
            action=action,
            contracts=contracts,
            trade_time=trade_time,
            symbol='BTCUSD_PERP',
            entry_price=entry_price,
            exit_price=exit_price,
            position_id=position_id,
            order_id=order_id,
            fee_rate=fee_rate,
            fee_usd=fee_usd,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            realized_pnl=realized_pnl,
            balance_before=balance_before,
            balance_after=balance_after,
            source='trade_engine',
            kline_close_time=kline_close_time,
            notes=notes
        )
        return self.record_trade(record)


# 全局实例
def get_trade_recorder() -> TradeRecorder:
    """获取交易记录器实例"""
    return TradeRecorder()
