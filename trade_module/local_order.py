#!/usr/bin/env python3
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.database import get_db
from core.logger import get_logger


@dataclass
class Order:
    """订单数据类"""
    order_id: str
    trace_id: str
    side: str  # 'long' or 'short'
    order_type: str  # 'OPEN', 'TP', 'SL', 'CLOSE_RETREAT', etc.
    price: float
    contracts: float
    status: str = 'PENDING'  # 'PENDING', 'FILLED', 'PARTIALLY_FILLED', 'CANCELED', 'EXPIRED'
    created_time: str = ''
    updated_time: str = ''
    filled_time: str = ''
    filled_contracts: float = 0.0
    avg_fill_price: float = 0.0
    parent_order_id: str = None
    position_id: str = None
    tp_level: str = None
    sl_trigger_price: float = None
    fee_rate: float = None
    fee_usd: float = None
    notes: str = None
    kline_close_time: str = None  # 对应K线的收盘时间

class LocalOrderManager:
    def __init__(self):
        self.logger = get_logger('trade_module.order')
        self.db = get_db()
        self.orders: Dict[str, Order] = {}
    
    def create_order(self, order: Order) -> bool:
        """创建订单并写入数据库"""
        now = datetime.now().isoformat()
        order.created_time = now
        order.updated_time = now
        self.orders[order.order_id] = order

        # 写入数据库
        try:
            with self.db.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO orders (
                        order_id, trace_id, symbol, side, order_type,
                        status, price, contracts, filled_contracts, avg_fill_price,
                        created_time, updated_time, filled_time,
                        parent_order_id, position_id, tp_level,
                        sl_trigger_price, fee_rate, fee_usd, notes, kline_close_time
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    order.order_id, order.trace_id, 'BTCUSD_PERP',
                    order.side, order.order_type, order.status,
                    order.price, order.contracts, order.filled_contracts,
                    order.avg_fill_price, order.created_time, order.updated_time,
                    order.filled_time, order.parent_order_id, order.position_id,
                    order.tp_level, order.sl_trigger_price, order.fee_rate,
                    order.fee_usd, order.notes, order.kline_close_time
                ))
                conn.commit()

            self.logger.info(
                f"✓ 订单已创建并写入数据库: "
                f"{order.order_type} {order.side} {order.contracts}张@{order.price}"
            )
            return True
        except Exception as e:
            self.logger.error(f"❌ 创建订单失败: {e}", exc_info=True)
            return False
    
    def update_order_status(self, order_id: str, status: str,
                           filled_contracts: float = None,
                           avg_fill_price: float = None) -> bool:
        """更新订单状态"""
        if order_id not in self.orders:
            self.logger.warning(f"订单不存在: {order_id}")
            return False

        order = self.orders[order_id]
        order.status = status

        if status == 'FILLED':
            order.filled_time = datetime.now().isoformat()

        try:
            with self.db.transaction() as conn:
                cursor = conn.cursor()

                # 更新订单状态
                update_fields = {
                    'status': status,
                    'updated_time': datetime.now().isoformat()
                }

                if order.filled_time:
                    update_fields['filled_time'] = order.filled_time

                if filled_contracts is not None:
                    update_fields['filled_contracts'] = filled_contracts

                if avg_fill_price is not None:
                    update_fields['avg_fill_price'] = avg_fill_price

                # 构建UPDATE语句
                set_clause = ', '.join([f"{k} = ?" for k in update_fields.keys()])
                values = list(update_fields.values()) + [order_id]

                cursor.execute(f"""
                    UPDATE orders
                    SET {set_clause}
                    WHERE order_id = ?
                """, values)

                conn.commit()

                # 记录订单状态历史
                old_status = self.orders[order_id].status if order_id in self.orders else None
                if old_status and old_status != status:
                    self._record_order_status_history(
                        conn, order_id, old_status, status
                    )

            self.logger.info(
                f"✓ 订单状态已更新: {order_id} -> {status}"
                + (f" 成交{filled_contracts}张@{avg_fill_price}" if filled_contracts else "")
            )
            return True
        except Exception as e:
            self.logger.error(f"❌ 更新订单状态失败: {e}", exc_info=True)
            return False
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """获取订单"""
        return self.orders.get(order_id)

    def _record_order_status_history(self, conn, order_id: str,
                                     old_status: str, new_status: str,
                                     reason: str = None):
        """记录订单状态变更历史"""
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO order_status_history (
                    order_id, old_status, new_status, change_time, reason
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                order_id, old_status, new_status,
                datetime.now().isoformat(), reason
            ))
            conn.commit()
        except Exception as e:
            self.logger.warning(f"记录订单状态历史失败: {e}")

    def get_all_orders(self) -> List[Order]:
        """获取所有订单"""
        return list(self.orders.values())

    def get_orders_by_status(self, status: str) -> List[Order]:
        """根据状态获取订单"""
        return [order for order in self.orders.values() if order.status == status]

    def get_orders_by_trace_id(self, trace_id: str) -> List[Order]:
        """根据trace_id获取订单"""
        return [order for order in self.orders.values() if order.trace_id == trace_id]

    def record_user_trade(self, trade: Dict[str, Any]) -> bool:
        """
        将交易所返回的单笔成交（user_trade）持久化到本地表，用于审计

        要求 trade 包含字段: id, orderId, price, qty, commission, commissionAsset, time, isBuyer
        """
        try:
            now = datetime.now().isoformat()
            with self.db.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO trades_audit (
                        trade_id, order_id, price, qty, commission, commission_asset,
                        is_buyer, trade_time, created_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(trade.get('id') or trade.get('tradeId') or ''),
                    str(trade.get('orderId') or ''),
                    float(trade.get('price') or trade.get('price', 0)),
                    float(trade.get('qty') or trade.get('quantity') or 0),
                    float(trade.get('commission') or 0),
                    trade.get('commissionAsset') or '',
                    1 if trade.get('isBuyer') or trade.get('isBuyerMaker') else 0,
                    datetime.fromtimestamp(int(trade.get('time', 0)) / 1000).isoformat() if trade.get('time') else None,
                    now
                ))
                conn.commit()

            self.logger.info(f"✓ 已记录 user_trade 审计: order={trade.get('orderId')} trade_id={trade.get('id')}")
            return True
        except Exception as e:
            self.logger.warning(f"记录 user_trade 审计失败: {e}", exc_info=True)
            return False

