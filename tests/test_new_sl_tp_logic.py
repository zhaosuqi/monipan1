#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试新的止损止盈逻辑

测试场景：
1. 止损：实时价格触发止损 → 取消所有挂单 → 市价平仓
2. 止盈级别：非最后级别 → 只记录，标定回撤价格
3. 止盈级别：最后级别 → 市价平仓
4. 止盈回撤：分钟收盘价达到回撤价格 → 市价平仓
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from trade_module.trade_engine import Position, TradeEngine


class MockExchange:
    """模拟交易所"""
    def __init__(self):
        self.connected = True
        self.orders = []
        self.open_orders = []
        
    def connect(self):
        pass
    
    def place_order(self, **kwargs):
        order = MagicMock()
        order.order_id = f"order_{len(self.orders)}"
        order.status = MagicMock()
        order.status.value = 'FILLED'
        order.avg_price = kwargs.get('price') or 100000
        self.orders.append(order)
        return order
    
    def get_open_orders(self, symbol):
        return self.open_orders
    
    def cancel_order(self, symbol, order_id):
        self.open_orders = [o for o in self.open_orders if o.order_id != order_id]
    
    def get_order(self, symbol, order_id):
        for o in self.orders:
            if o.order_id == order_id:
                return o
        return None
    
    def get_position(self, symbol):
        return None


class TestStopLossLogic(unittest.TestCase):
    """测试止损逻辑"""
    
    def setUp(self):
        """设置测试环境"""
        self.exchange = MockExchange()
        
        with patch('trade_module.trade_engine.create_exchange', return_value=self.exchange):
            self.engine = TradeEngine(exchange=self.exchange)
        
    def test_realtime_stop_loss_long(self):
        """测试多头实时止损"""
        # 创建一个多头持仓
        pos = Position(
            id="test_pos_1",
            side="long",
            entry_price=100000,
            entry_time=pd.Timestamp.now(),
            contracts=10,
            entry_contracts=10,
            contract_size_btc=0.001,
            trace_id="trace_1"
        )
        self.engine.positions.append(pos)
        
        ts = pd.Timestamp.now()
        
        # 触发止损 (假设 STOP_LOSS_POINTS = 0.0165, 止损价约 98350)
        # 使用一个很低的价格触发止损
        realtime_price = 98000
        
        result = self.engine.check_stop_loss_realtime(pos, ts, realtime_price)
        
        # 应该触发止损
        self.assertTrue(result or pos.sl_triggered)
        
    def test_realtime_stop_loss_short(self):
        """测试空头实时止损"""
        pos = Position(
            id="test_pos_2",
            side="short",
            entry_price=100000,
            entry_time=pd.Timestamp.now(),
            contracts=10,
            entry_contracts=10,
            contract_size_btc=0.001,
            trace_id="trace_2"
        )
        self.engine.positions.append(pos)
        
        ts = pd.Timestamp.now()
        
        # 触发止损
        realtime_price = 102000  # 高于入场价触发空头止损
        
        result = self.engine.check_stop_loss_realtime(pos, ts, realtime_price)
        
        # 应该触发止损
        self.assertTrue(result or pos.sl_triggered)


class TestTakeProfitLogic(unittest.TestCase):
    """测试止盈逻辑"""
    
    def setUp(self):
        """设置测试环境"""
        self.exchange = MockExchange()
        
        with patch('trade_module.trade_engine.create_exchange', return_value=self.exchange):
            self.engine = TradeEngine(exchange=self.exchange)
    
    def test_non_last_level_tp_no_close(self):
        """测试非最后级别止盈不平仓"""
        pos = Position(
            id="test_pos_3",
            side="long",
            entry_price=100000,
            entry_time=pd.Timestamp.now(),
            contracts=10,
            entry_contracts=10,
            contract_size_btc=0.001,
            trace_id="trace_3"
        )
        self.engine.positions.append(pos)
        
        ts = pd.Timestamp.now()
        
        # 假设第一级止盈是 1.0065，目标价约 100650
        realtime_price = 100700  # 触发第一级止盈
        
        result = self.engine.apply_take_profit_realtime(pos, ts, realtime_price)
        
        # 非最后级别不应该平仓
        self.assertFalse(result)
        # 但应该记录止盈级别
        self.assertTrue(pos.tp_activated)
        self.assertIsNotNone(pos.tp_drawdown_price)
        
    def test_last_level_tp_close(self):
        """测试最后级别止盈平仓"""
        pos = Position(
            id="test_pos_4",
            side="long",
            entry_price=100000,
            entry_time=pd.Timestamp.now(),
            contracts=10,
            entry_contracts=10,
            contract_size_btc=0.001,
            trace_id="trace_4"
        )
        
        # 预先标记前面的级别为已触发
        # TP_LEVELS 默认为 [1.0065, 1.012, 1.018, 1.024, 1.03]
        pos.tp_hit = [1.0065, 1.012, 1.018, 1.024]  # 前4级已触发
        pos.tp_activated = True
        
        self.engine.positions.append(pos)
        
        ts = pd.Timestamp.now()
        
        # 最后一级止盈是 1.03，目标价约 103000
        realtime_price = 104000  # 触发最后级别止盈
        
        result = self.engine.apply_take_profit_realtime(pos, ts, realtime_price)
        
        # 最后级别应该平仓
        self.assertTrue(result)


class TestDrawdownLogic(unittest.TestCase):
    """测试止盈回撤逻辑"""
    
    def setUp(self):
        """设置测试环境"""
        self.exchange = MockExchange()
        
        with patch('trade_module.trade_engine.create_exchange', return_value=self.exchange):
            self.engine = TradeEngine(exchange=self.exchange)
    
    def test_drawdown_trigger_with_close_price(self):
        """测试分钟收盘价触发回撤"""
        pos = Position(
            id="test_pos_5",
            side="long",
            entry_price=100000,
            entry_time=pd.Timestamp.now(),
            contracts=10,
            entry_contracts=10,
            contract_size_btc=0.001,
            trace_id="trace_5"
        )
        
        # 设置已确认的止盈价格和回撤价格
        pos.tp_activated = True
        pos.tp_confirmed_price = 100650
        pos.tp_drawdown_price = 100630  # 假设回撤20点
        pos.tp_hit = [1.0065]
        
        self.engine.positions.append(pos)
        
        ts = pd.Timestamp.now()
        row = {'close': 100620}  # 收盘价低于回撤价
        
        result = self.engine.check_drawdown(pos, ts, row['close'], row)
        
        # 应该触发回撤平仓
        self.assertTrue(result)


class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.exchange = MockExchange()
        
        with patch('trade_module.trade_engine.create_exchange', return_value=self.exchange):
            self.engine = TradeEngine(exchange=self.exchange)
    
    def test_on_realtime_price_method(self):
        """测试实时价格处理方法"""
        pos = Position(
            id="test_pos_6",
            side="long",
            entry_price=100000,
            entry_time=pd.Timestamp.now(),
            contracts=10,
            entry_contracts=10,
            contract_size_btc=0.001,
            trace_id="trace_6"
        )
        self.engine.positions.append(pos)
        
        # 正常价格，不应该触发止损
        closed = self.engine.on_realtime_price(100500)
        self.assertEqual(len(closed), 0)
        
    def test_on_kline_close_method(self):
        """测试K线收盘处理方法"""
        pos = Position(
            id="test_pos_7",
            side="long",
            entry_price=100000,
            entry_time=pd.Timestamp.now(),
            contracts=10,
            entry_contracts=10,
            contract_size_btc=0.001,
            trace_id="trace_7"
        )
        self.engine.positions.append(pos)
        
        ts = pd.Timestamp.now()
        row = {'close': 100500, 'high': 100600, 'low': 100400}
        
        # 正常K线，不应该触发回撤
        closed = self.engine.on_kline_close(ts, row)
        self.assertEqual(len(closed), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
