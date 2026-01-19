#!/usr/bin/env python3
from dataclasses import dataclass
from typing import Dict

from core.logger import get_logger
from core.config import config

@dataclass
class AccountInfo:
    total_balance: float  # BTC
    available_balance: float  # BTC
    unrealized_pnl: float  # USD
    realized_pnl: float  # USD

class AccountTracker:
    def __init__(self):
        self.logger = get_logger('trade_module.account')
        self.balance_btc = config.POSITION_BTC
        self.realized_pnl = 0.0
    
    def update_balance(self, balance: float):
        """更新余额"""
        self.balance_btc = balance
        self.logger.info(f"更新余额: {balance} BTC")
    
    def add_pnl(self, pnl: float):
        """添加盈亏"""
        self.realized_pnl += pnl
        self.logger.info(f"实现盈亏: {pnl:.2f} USD, 总计: {self.realized_pnl:.2f} USD")
    
    def get_account_info(self) -> AccountInfo:
        """获取账户信息"""
        return AccountInfo(
            total_balance=self.balance_btc,
            available_balance=self.balance_btc,
            unrealized_pnl=0.0,
            realized_pnl=self.realized_pnl
        )
