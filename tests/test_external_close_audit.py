#!/usr/bin/env python3
# 简单集成测试: 模拟外部平仓并验证 trades_audit 写入

import time
from datetime import datetime

import pandas as pd

from core.database import get_db
from exchange_layer.binance_exchange import BinanceExchange
from trade_module.local_order import LocalOrderManager
from trade_module.trade_engine import Position, TradeEngine


class MockExchange(BinanceExchange):
    def __init__(self):
        # 不调用父类 connect
        super().__init__(api_key='', api_secret='', testnet=True)
        self._pos = {'position_amount': 5, 'entryPrice': 90000, 'markPrice': 90500}
        self._trades = []

    def get_position(self, symbol: str):
        return self._pos

    def get_user_trades(self, symbol: str, order_id: int = None, limit: int = 500):
        return self._trades

    def get_open_orders(self, symbol: str = None):
        return []


def run_test():
    db = get_db()

    # 清空 trades_audit 表
    db.execute("DELETE FROM trades_audit")

    # 初始化 Engine，注入 MockExchange
    mock_ex = MockExchange()
    engine = TradeEngine(exchange=mock_ex)

    # 创建一个本地持仓: 10 张, entry_price 90000
    pos = Position(
        id='pos-test-1',
        side='long',
        entry_price=90000.0,
        entry_time=pd.Timestamp.utcnow(),
        contracts=10,
        entry_contracts=10,
        contract_size_btc=0.001,
        tp_hit=[],
        tp_activated=False,
        tp_hit_value=0.0,
        trace_id='trace-test-1',
        benchmark_price=90000.0,
    )

    engine.positions.append(pos)

    # 模拟交易所持仓变为 6（外部平仓 4 张），并准备 user_trades
    mock_ex._pos = {'position_amount': 6, 'entryPrice': 90000, 'markPrice': 90400}

    # 准备 trades: 2 笔各2张，价格 90200, 90300
    now_ms = int(time.time() * 1000)
    mock_ex._trades = [
        {'id': 't1', 'orderId': 'o1', 'price': '90200', 'qty': '2', 'commission': '0.0001', 'commissionAsset': 'BTC', 'isBuyer': False, 'time': now_ms - 2000},
        {'id': 't2', 'orderId': 'o2', 'price': '90300', 'qty': '2', 'commission': '0.00012', 'commissionAsset': 'BTC', 'isBuyer': False, 'time': now_ms - 1000},
    ]

    # 执行同步
    engine.sync_external_fills()

    # 检查 trades_audit 表
    rows = db.fetchall("SELECT trade_id, order_id, price, qty FROM trades_audit ORDER BY id")
    print('trades_audit rows:', [(r['trade_id'], r['order_id'], r['price'], r['qty']) for r in rows])

    # 检查本地持仓数量
    print('remaining pos contracts:', engine.positions[0].contracts if engine.positions else 'none')


if __name__ == '__main__':
    run_test()
