#!/usr/bin/env python3
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from core.logger import get_logger

@dataclass
class Position:
    id: str
    symbol: str
    side: str
    entry_price: float
    contracts: float
    entry_time: str
    benchmark_price: float = 0.0
    tp_activated: bool = False
    tp_hit: List = field(default_factory=list)

class PositionManager:
    def __init__(self):
        self.logger = get_logger('signal_module.position')
        self.positions: Dict[str, Position] = {}
    
    def add_position(self, position: Position):
        """添加持仓"""
        self.positions[position.id] = position
        self.logger.info(f"添加持仓: {position.side} {position.contracts}@{position.entry_price}")
    
    def get_position(self, position_id: str) -> Optional[Position]:
        """获取持仓"""
        return self.positions.get(position_id)
    
    def get_all_positions(self) -> List[Position]:
        """获取所有持仓"""
        return list(self.positions.values())
    
    def close_position(self, position_id: str):
        """关闭持仓"""
        if position_id in self.positions:
            pos = self.positions.pop(position_id)
            self.logger.info(f"关闭持仓: {pos.side} {pos.contracts}@{pos.entry_price}")
            return pos
        return None
    
    def update_position(self, position_id: str, **kwargs):
        """更新持仓"""
        if position_id in self.positions:
            pos = self.positions[position_id]
            for key, value in kwargs.items():
                if hasattr(pos, key):
                    setattr(pos, key, value)
