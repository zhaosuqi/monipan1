#!/usr/bin/env python3
from typing import List, Tuple
from core.logger import get_logger
from core.config import config

class TPManager:
    def __init__(self):
        self.logger = get_logger('signal_module.tp')
    
    def calculate_tp_targets(self, position) -> List[Tuple[float, float, str]]:
        """计算分级止盈目标"""
        if position.side == 'long':
            base_price = position.entry_price
            targets = []
            for i, level in enumerate(config.TP_LEVELS):
                target_price = base_price * level
                qty = position.contracts / len(config.TP_LEVELS)
                targets.append((target_price, qty, str(level)))
            return targets
        else:
            # 做空逻辑
            base_price = position.entry_price
            targets = []
            for i, level in enumerate(config.TP_LEVELS):
                target_price = base_price * (2 - level)
                qty = position.contracts / len(config.TP_LEVELS)
                targets.append((target_price, qty, str(level)))
            return targets
