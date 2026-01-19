#!/usr/bin/env python3
# 数据通知器
from typing import Dict, Any, Callable, List

from core.logger import get_logger

class DataNotifier:
    def __init__(self):
        self.logger = get_logger('data_module.notifier')
        self.subscribers: List[Callable] = []
    
    def subscribe(self, callback: Callable):
        """订阅数据更新"""
        self.subscribers.append(callback)
    
    def notify_new_data(self, data: Dict[str, Any]):
        """通知新数据"""
        for callback in self.subscribers:
            try:
                callback(data)
            except Exception as e:
                self.logger.error(f"通知失败: {e}")
