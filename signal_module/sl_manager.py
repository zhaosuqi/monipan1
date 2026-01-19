#!/usr/bin/env python3
from core.logger import get_logger
from core.config import config

class SLManager:
    def __init__(self):
        self.logger = get_logger('signal_module.sl')
    
    def calculate_sl_price(self, position) -> float:
        """计算止损价格"""
        if position.side == 'long':
            return position.entry_price * (1 - config.STOP_LOSS_POINTS)
        else:
            return position.entry_price * (1 + config.STOP_LOSS_POINTS)
