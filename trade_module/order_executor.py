#!/usr/bin/env python3
import uuid
from datetime import datetime
from typing import Optional

from core.logger import get_logger
from core.config import config
from trade_module.local_order import Order, LocalOrderManager
from trade_module.account_tracker import AccountTracker

class OrderExecutor:
    def __init__(self):
        self.logger = get_logger('trade_module.executor')
        self.order_manager = LocalOrderManager()
        self.account_tracker = AccountTracker()
    
    def execute_open_order(self, signal, trace_id: str) -> Optional[Order]:
        """执行开仓订单"""
        # 计算合约数量
        contracts = int((config.POSITION_BTC * 43000) / config.CONTRACT_NOTIONAL)
        
        order = Order(
            order_id=str(uuid.uuid4()),
            trace_id=trace_id,
            side=signal.side,
            order_type='OPEN',
            price=43000.0,  # 实际应该从行情获取
            contracts=contracts
        )
        
        if self.order_manager.create_order(order):
            self.order_manager.update_order_status(
                order.order_id, 'FILLED',
                filled_contracts=contracts,
                avg_fill_price=order.price
            )
            self.logger.info(f"开仓订单执行成功: {signal.side} {contracts}张")
            return order
        
        return None
    
    def execute_tp_order(self, position, level: str, price: float) -> Optional[Order]:
        """执行止盈订单"""
        order = Order(
            order_id=str(uuid.uuid4()),
            trace_id=position.id,
            side=position.side,
            order_type='TP',
            price=price,
            contracts=position.contracts / len(config.TP_LEVELS)
        )

        tp_contracts = order.contracts
        if self.order_manager.create_order(order):
            self.order_manager.update_order_status(
                order.order_id, 'FILLED',
                filled_contracts=tp_contracts,
                avg_fill_price=price
            )
            return order

        return None
    
    def execute_sl_order(self, position, price: float) -> Optional[Order]:
        """执行止损订单"""
        order = Order(
            order_id=str(uuid.uuid4()),
            trace_id=position.id,
            side=position.side,
            order_type='SL',
            price=price,
            contracts=position.contracts
        )

        sl_contracts = order.contracts
        if self.order_manager.create_order(order):
            self.order_manager.update_order_status(
                order.order_id, 'FILLED',
                filled_contracts=sl_contracts,
                avg_fill_price=price
            )
            return order

        return None
