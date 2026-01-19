#!/usr/bin/env python3
import requests
from typing import Dict

from core.logger import get_logger
from core.config import config

class FeishuBot:
    def __init__(self):
        self.logger = get_logger('interaction_module.feishu')
        self.webhook = config.FEISHU_WEBHOOK
        self.enabled = config.FEISHU_ENABLED
    
    def send_message(self, message: str) -> bool:
        """发送消息"""
        if not self.enabled or not self.webhook:
            return False
        
        try:
            data = {
                "msg_type": "text",
                "content": {"text": message}
            }
            
            response = requests.post(self.webhook, json=data, timeout=5)
            
            if response.status_code == 200:
                self.logger.debug(f"飞书消息发送成功: {message[:50]}")
                return True
            else:
                self.logger.error(f"飞书消息发送失败: {response.status_code}")
                return False
        
        except Exception as e:
            self.logger.error(f"飞书消息发送异常: {e}")
            return False
    
    def send_trade_notification(self, signal: Dict) -> bool:
        """发送交易通知"""
        message = f"交易信号: {signal.get('action')} {signal.get('side')}\n原因: {signal.get('reason')}"
        return self.send_message(message)
