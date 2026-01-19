#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志管理模块
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime


class Logger:
    """日志管理类"""

    _instance = None
    _loggers = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return

        from .config import config

        self.log_dir = config.data_dir / 'logs'
        self.log_dir.mkdir(exist_ok=True)

        self._initialized = True

    def get_logger(self, name: str) -> logging.Logger:
        """获取logger实例"""
        if name in self._loggers:
            return self._loggers[name]

        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)

        # 避免重复添加handler
        if logger.handlers:
            return logger

        # 格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 控制台handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # 文件handler
        log_file = self.log_dir / f'{name}_{datetime.now().strftime("%Y%m%d")}.log'
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        self._loggers[name] = logger
        return logger

    def get_module_logger(self, module_name: str):
        """获取模块logger"""
        return self.get_logger(f'monipan.{module_name}')


# 全局logger实例
logger_manager = Logger()


def get_logger(name: str) -> logging.Logger:
    """获取logger的便捷函数"""
    return logger_manager.get_logger(name)


def get_module_logger(module_name: str) -> logging.Logger:
    """获取模块logger的便捷函数"""
    return logger_manager.get_module_logger(module_name)
