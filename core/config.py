#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块
"""

import json
import os
from pathlib import Path
from typing import Any, Dict


class Config:
    """配置管理类"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if Config._initialized:
            return

        # 基础路径
        self.base_dir = Path(__file__).parent.parent
        self.data_dir = self.base_dir / 'data'
        self.config_file = self.base_dir / 'config.json'

        # 确保数据目录存在
        self.data_dir.mkdir(exist_ok=True)

        # 加载配置
        self._load_config()
        self._load_env()

        Config._initialized = True

    def _load_config(self):
        """从JSON文件加载配置"""
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config_data = json.load(f)
        else:
            self.config_data = {}

    def _load_env(self):
        """加载环境变量"""
        # 数据库配置
        self.DB_PATH = os.getenv('DB_PATH', str(self.data_dir / 'klines.db'))
        self.HIST_DB_PATH = os.getenv('HIST_DB_PATH', str(self.data_dir / 'klines.db'))  # 历史数据也在data/klines.db
        self.HIST_TABLE = os.getenv('HIST_TABLE', 'klines_1m')
        self.SIM_LOG_TABLE = os.getenv('SIM_LOG_TABLE', 'sim_log')
        self.MACD_OUTPUT_TABLE = os.getenv('MACD_OUTPUT_TABLE', 'klines_1m_macd_calc')

        # Binance API
        # 测试网API密钥
        self.BINANCE_TESTNET_API_KEY = os.getenv(
            'BINANCE_TESTNET_API_KEY', ''
        )
        self.BINANCE_TESTNET_API_SECRET = os.getenv(
            'BINANCE_TESTNET_API_SECRET', ''
        )

        # 实盘API密钥
        self.BINANCE_LIVE_API_KEY = os.getenv(
            'BINANCE_LIVE_API_KEY', ''
        )
        self.BINANCE_LIVE_API_SECRET = os.getenv(
            'BINANCE_LIVE_API_SECRET', ''
        )

        # 当前使用的API密钥（根据BINANCE_TESTNET自动选择）
        self.BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
        self.BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', '')
        self.BINANCE_TESTNET = os.getenv('BINANCE_TESTNET', '1').lower() in ('1', 'true', 'yes')
        self.BINANCE_PROXY = os.getenv('BINANCE_PROXY', '')

        # 交易所配置 - 新增
        # 可选值: MOCK_LOCAL, BINANCE_TESTNET, BINANCE_LIVE
        # 如果不设置，则根据 REPLAY_MODE 和 BINANCE_TESTNET 自动检测
        self.EXCHANGE_TYPE = os.getenv('EXCHANGE_TYPE', '')

        # 本地虚拟币安API服务器配置
        self.MOCK_SERVER_HOST = os.getenv('MOCK_SERVER_HOST', '127.0.0.1')
        self.MOCK_SERVER_PORT = int(os.getenv('MOCK_SERVER_PORT', '8080'))
        self.MOCK_SERVER_ENABLED = os.getenv('MOCK_SERVER_ENABLED', '0').lower() in ('1', 'true', 'yes')

        # 交易对
        self.SYMBOL = os.getenv('SYMBOL', 'BTCUSD_PERP')

        # 模式
        self.REPLAY_MODE = os.getenv('REPLAY_MODE', '1').lower() in ('1', 'true', 'yes')  # 默认为回测模式
        self.DB_SIM_MODE = os.getenv('DB_SIM_MODE', '1').lower() in ('1', 'true', 'yes')  # 默认为数据库模拟
        self.REPLAY_START = os.getenv('REPLAY_START', '2024-01-01 00:00:00')
        self.REPLAY_END = os.getenv('REPLAY_END', '2024-01-03 23:59:59')
        self.REPLAY_WARM_DAYS = int(os.getenv('REPLAY_WARM_DAYS', '200'))  # 至少200天以支持1天MACD
        self.REPLAY_CHUNK = int(os.getenv('REPLAY_CHUNK', '2000'))

        # 数据获取
        self.KLINE_INTERVAL = os.getenv('KLINE_INTERVAL', '1m')
        self.KLINE_LIMIT = int(os.getenv('KLINE_LIMIT', '1000'))

        # 指标计算
        self.MACD_FAST = int(os.getenv('MACD_FAST', '12'))
        self.MACD_SLOW = int(os.getenv('MACD_SLOW', '26'))
        self.MACD_SIGNAL = int(os.getenv('MACD_SIGNAL', '9'))

        # 仓位配置
        self.POSITION_BTC = float(os.getenv('POSITION_BTC', '1.0'))
        self.CONTRACT_NOTIONAL = float(os.getenv('CONTRACT_NOTIONAL', '100'))
        self.LEVERAGE = float(os.getenv('LEVERAGE', '3'))

        # V5 T0参数 - 15分钟
        self.T0_HIST15_LIMIT = float(os.getenv('T0_HIST15_LIMIT', '9999'))
        self.T0_HIST15_LIMIT_MIN = float(os.getenv('T0_HIST15_LIMIT_MIN', '0'))
        self.T0_DIF15_LIMIT = float(os.getenv('T0_DIF15_LIMIT', '1000'))
        self.T0_DIF15_LIMIT_MIN = float(os.getenv('T0_DIF15_LIMIT_MIN', '-9999'))

        # V5 T0参数 - 1小时
        self.T0_HIST1H_LIMIT = float(os.getenv('T0_HIST1H_LIMIT', '9999'))
        self.T0_HIST1H_LIMIT_MIN = float(os.getenv('T0_HIST1H_LIMIT_MIN', '0'))
        self.T0_DIF1H_LIMIT = float(os.getenv('T0_DIF1H_LIMIT', '1000'))
        self.T0_DIF1H_LIMIT_MIN = float(os.getenv('T0_DIF1H_LIMIT_MIN', '-9999'))

        # V5 T0参数 - 4小时
        self.T0_HIST4_LIMIT = float(os.getenv('T0_HIST4_LIMIT', '9999'))
        self.T0_HIST4_LIMIT_MIN = float(os.getenv('T0_HIST4_LIMIT_MIN', '0'))
        self.T0_DIF4_LIMIT = float(os.getenv('T0_DIF4_LIMIT', '1000'))
        self.T0_DIF4_LIMIT_MIN = float(os.getenv('T0_DIF4_LIMIT_MIN', '-9999'))

        # V5 T0参数 - 1天
        self.T0_HIST1D_LIMIT = float(os.getenv('T0_HIST1D_LIMIT', '9999'))
        self.T0_HIST1D_LIMIT_MIN = float(os.getenv('T0_HIST1D_LIMIT_MIN', '-9999'))
        self.T0_DIF1D_LIMIT = float(os.getenv('T0_DIF1D_LIMIT', '9999'))
        self.T0_DIF1D_LIMIT_MIN = float(os.getenv('T0_DIF1D_LIMIT_MIN', '-9999'))

        # V5 T0参数 - J指标（多）
        self.T0_J15M_LIMIT = float(os.getenv('T0_J15M_LIMIT', '999'))
        self.T0_J1H_LIMIT = float(os.getenv('T0_J1H_LIMIT', '999'))
        self.T0_J4H_LIMIT = float(os.getenv('T0_J4H_LIMIT', '113'))

        # V5 T0参数 - J指标（空）
        self.T0_J15M_LIMIT_KONG = float(os.getenv('T0_J15M_LIMIT_KONG', '-999'))
        self.T0_J1H_LIMIT_KONG = float(os.getenv('T0_J1H_LIMIT_KONG', '-999'))
        self.T0_J4H_LIMIT_KONG = float(os.getenv('T0_J4H_LIMIT_KONG', '-13'))

        # V5 均值参数 - 第一组 (15分钟)
        self.MEANS_HIST15_COUNT = int(os.getenv('MEANS_HIST15_COUNT', '5'))
        self.HIST15_MEANS_LIMIT = float(os.getenv('HIST15_MEANS_LIMIT', '1'))
        self.MEANS_DIF15_COUNT = int(os.getenv('MEANS_DIF15_COUNT', '5'))
        self.DIF15_MEANS_LIMIT = float(os.getenv('DIF15_MEANS_LIMIT', '1'))
        self.MEANS_DEA15_COUNT = int(os.getenv('MEANS_DEA15_COUNT', '5'))
        self.DEA15_MEANS_LIMIT = float(os.getenv('DEA15_MEANS_LIMIT', '1'))

        # V5 均值参数 - 第一组 (1小时)
        self.MEANS_HIST1H_COUNT = int(os.getenv('MEANS_HIST1H_COUNT', '5'))
        self.HIST1H_MEANS_LIMIT = float(os.getenv('HIST1H_MEANS_LIMIT', '1'))
        self.MEANS_DIF1H_COUNT = int(os.getenv('MEANS_DIF1H_COUNT', '5'))
        self.DIF1H_MEANS_LIMIT = float(os.getenv('DIF1H_MEANS_LIMIT', '1'))
        self.MEANS_DEA1H_COUNT = int(os.getenv('MEANS_DEA1H_COUNT', '5'))
        self.DEA1H_MEANS_LIMIT = float(os.getenv('DEA1H_MEANS_LIMIT', '1'))

        # V5 均值参数 - 第一组 (4小时)
        self.MEANS_HIST4_COUNT = int(os.getenv('MEANS_HIST4_COUNT', '5'))
        self.HIST4_MEANS_LIMIT = float(os.getenv('HIST4_MEANS_LIMIT', '1'))
        self.MEANS_DIF4_COUNT = int(os.getenv('MEANS_DIF4_COUNT', '5'))
        self.DIF4_MEANS_LIMIT = float(os.getenv('DIF4_MEANS_LIMIT', '1'))
        self.MEANS_DEA4_COUNT = int(os.getenv('MEANS_DEA4_COUNT', '5'))
        self.DEA4_MEANS_LIMIT = float(os.getenv('DEA4_MEANS_LIMIT', '1'))

        # V5 均值参数 - 第一组 (1天)
        self.MEANS_HIST1D_COUNT = int(os.getenv('MEANS_HIST1D_COUNT', '360'))
        self.HIST1D_MEANS_LIMIT = float(os.getenv('HIST1D_MEANS_LIMIT', '0'))
        self.MEANS_DIF1D_COUNT = int(os.getenv('MEANS_DIF1D_COUNT', '0'))
        self.DIF1D_MEANS_LIMIT = float(os.getenv('DIF1D_MEANS_LIMIT', '0'))
        self.MEANS_DEA1D_COUNT = int(os.getenv('MEANS_DEA1D_COUNT', '0'))
        self.DEA1D_MEANS_LIMIT = float(os.getenv('DEA1D_MEANS_LIMIT', '0'))

        # V5 均值参数 - 第二组 (15分钟)
        self.MEANS_HIST15_COUNT_2 = int(os.getenv('MEANS_HIST15_COUNT_2', '10'))
        self.HIST15_MEANS_LIMIT_2 = float(os.getenv('HIST15_MEANS_LIMIT_2', '1'))
        self.MEANS_DIF15_COUNT_2 = int(os.getenv('MEANS_DIF15_COUNT_2', '30'))
        self.DIF15_MEANS_LIMIT_2 = float(os.getenv('DIF15_MEANS_LIMIT_2', '1'))
        self.MEANS_DEA15_COUNT_2 = int(os.getenv('MEANS_DEA15_COUNT_2', '10'))
        self.DEA15_MEANS_LIMIT_2 = float(os.getenv('DEA15_MEANS_LIMIT_2', '1'))

        # V5 均值参数 - 第二组 (1小时)
        self.MEANS_HIST1H_COUNT_2 = int(os.getenv('MEANS_HIST1H_COUNT_2', '10'))
        self.HIST1H_MEANS_LIMIT_2 = float(os.getenv('HIST1H_MEANS_LIMIT_2', '1'))
        self.MEANS_DIF1H_COUNT_2 = int(os.getenv('MEANS_DIF1H_COUNT_2', '10'))
        self.DIF1H_MEANS_LIMIT_2 = float(os.getenv('DIF1H_MEANS_LIMIT_2', '1'))
        self.MEANS_DEA1H_COUNT_2 = int(os.getenv('MEANS_DEA1H_COUNT_2', '15'))
        self.DEA1H_MEANS_LIMIT_2 = float(os.getenv('DEA1H_MEANS_LIMIT_2', '1'))

        # V5 均值参数 - 第二组 (4小时)
        self.MEANS_HIST4_COUNT_2 = int(os.getenv('MEANS_HIST4_COUNT_2', '10'))
        self.HIST4_MEANS_LIMIT_2 = float(os.getenv('HIST4_MEANS_LIMIT_2', '1'))
        self.MEANS_DIF4_COUNT_2 = int(os.getenv('MEANS_DIF4_COUNT_2', '10'))
        self.DIF4_MEANS_LIMIT_2 = float(os.getenv('DIF4_MEANS_LIMIT_2', '1'))
        self.MEANS_DEA4_COUNT_2 = int(os.getenv('MEANS_DEA4_COUNT_2', '10'))
        self.DEA4_MEANS_LIMIT_2 = float(os.getenv('DEA4_MEANS_LIMIT_2', '-3'))

        # V5 均值参数 - 第二组 (1天)
        self.MEANS_HIST1D_COUNT_2 = int(os.getenv('MEANS_HIST1D_COUNT_2', '0'))
        self.HIST1D_MEANS_LIMIT_2 = float(os.getenv('HIST1D_MEANS_LIMIT_2', '0'))
        self.MEANS_DIF1D_COUNT_2 = int(os.getenv('MEANS_DIF1D_COUNT_2', '120'))
        self.DIF1D_MEANS_LIMIT_2 = float(os.getenv('DIF1D_MEANS_LIMIT_2', '0'))
        self.MEANS_DEA1D_COUNT_2 = int(os.getenv('MEANS_DEA1D_COUNT_2', '0'))
        self.DEA1D_MEANS_LIMIT_2 = float(os.getenv('DEA1D_MEANS_LIMIT_2', '0'))

        # ========== V5.0 完整参数集 ==========

        # T1参数 (T0变体)
        self.T1_T0_HIST_CHANGE = float(os.getenv('T1_T0_HIST_CHANGE', '15'))
        self.T1_T0_DIF_CHANGE = float(os.getenv('T1_T0_DIF_CHANGE', '15'))
        self.T1_T0_DEA_CHANGE = float(os.getenv('T1_T0_DEA_CHANGE', '-9999'))
        self.T1_T0_HIST_LIMIT = float(os.getenv('T1_T0_HIST_LIMIT', '-9999'))
        self.T1_HIST15_LIMIT = float(os.getenv('T1_HIST15_LIMIT', '30'))
        self.T1_HIST15_MAX = float(os.getenv('T1_HIST15_MAX', '50'))
        self.T1_DIF4_LIMIT = float(os.getenv('T1_DIF4_LIMIT', '1200'))
        self.T0_DEA4_LIMIT = float(os.getenv('T0_DEA4_LIMIT', '-9999'))
        self.T0_HIST15_COUNT = int(os.getenv('T0_HIST15_COUNT', '7'))
        self.T0_HIST15_LIMIT_MAX = float(os.getenv('T0_HIST15_LIMIT_MAX', '-9999'))

        # 价格变化参数
        self.PRICE_CHANGE_LIMIT = float(os.getenv('PRICE_CHANGE_LIMIT', '0.02'))
        self.PRICE_CHANGE_COUNT = int(os.getenv('PRICE_CHANGE_COUNT', '5'))
        self.PRICE_CHANGE_LIMIT_B = float(os.getenv('PRICE_CHANGE_LIMIT_B', '0.025'))
        self.PRICE_CHANGE_COUNT_B = int(os.getenv('PRICE_CHANGE_COUNT_B', '10'))
        self.PRICE_CHANGE_LIMIT_C = float(os.getenv('PRICE_CHANGE_LIMIT_C', '0.03'))
        self.PRICE_CHANGE_COUNT_C = int(os.getenv('PRICE_CHANGE_COUNT_C', '60'))
        self.PRICE_CHANGE_LIMIT_D = float(os.getenv('PRICE_CHANGE_LIMIT_D', '0.01'))
        self.PRICE_CHANGE_COUNT_D = int(os.getenv('PRICE_CHANGE_COUNT_D', '0'))
        self.PRICE_CHANGE_LIMIT_E = float(os.getenv('PRICE_CHANGE_LIMIT_E', '0.01'))
        self.PRICE_CHANGE_COUNT_E = int(os.getenv('PRICE_CHANGE_COUNT_E', '0'))
        self.M_PRICE_CHANGE = float(os.getenv('M_PRICE_CHANGE', '0.0025'))
        self.M_PRICE_CHANGE_MINUTES = int(os.getenv('M_PRICE_CHANGE_MINUTES', '1'))    # A组回溯分钟数，1=前一分钟，2=前两分钟，以此类推
        self.M_PRICE_CHANGE_B = float(os.getenv('M_PRICE_CHANGE_B', '0.013'))        # B组: 分钟前后价格变化率，防止插针。
        self.M_PRICE_CHANGE_MINUTES_B = int(os.getenv('M_PRICE_CHANGE_MINUTES_B', '5'))  # B组回溯分钟数
        self.M_PRICE_CHANGE_C = float(os.getenv('M_PRICE_CHANGE_C', '0.007'))        # C组: 分钟前后价格变化率，防止插针。
        self.M_PRICE_CHANGE_MINUTES_C = int(os.getenv('M_PRICE_CHANGE_MINUTES_C', '3'))  # C组回溯分钟数
        self.M_PRICE_CHANGE_D = float(os.getenv('M_PRICE_CHANGE_D', '0.9999'))        # D组: 分钟前后价格变化率
        self.M_PRICE_CHANGE_MINUTES_D = int(os.getenv('M_PRICE_CHANGE_MINUTES_D', '30'))  # D组回溯分钟数
        self.M_PRICE_CHANGE_E = float(os.getenv('M_PRICE_CHANGE_E', '0.9999'))        # E组: 分钟前后价格变化率
        self.M_PRICE_CHANGE_MINUTES_E = int(os.getenv('M_PRICE_CHANGE_MINUTES_E', '60'))  # E组回溯分钟数

        # 4H特殊参数
        self.HIST4_EXTREME_LIMIT = float(os.getenv('HIST4_EXTREME_LIMIT', '9999'))
        self.HIST4_NEUTRAL_BAND = float(os.getenv('HIST4_NEUTRAL_BAND', '0'))
        self.DIF4_T0_MIN_CHANGE = float(os.getenv('DIF4_T0_MIN_CHANGE', '9999'))

        # MA5/MA10开关
        self.ENABLE_MA5_MA10 = os.getenv('ENABLE_MA5_MA10', 'false').lower() in ('1', 'true', 'yes')

        # 止损持仓时间
        self.STOP_LOSS_HOLD_TIME = int(os.getenv('STOP_LOSS_HOLD_TIME', '0'))

        # T0锁仓
        self.T0_LOCK_ENABLED = os.getenv('T0_LOCK_ENABLED', 'false').lower() in ('1', 'true', 'yes')

        # 仓位限制
        self.NO_LIMIT_POS = os.getenv('NO_LIMIT_POS', 'false').lower() in ('1', 'true', 'yes')
        self.POSITION_NOMINAL = float(os.getenv('POSITION_NOMINAL', '10000.0'))

        # 订单类型
        self.OPEN_TAKER_OR_MAKER = os.getenv('OPEN_TAKER_OR_MAKER', 'TAKER')
        self.OPEN_MAKER_PRICE_RATIO = float(os.getenv('OPEN_MAKER_PRICE_RATIO', '0.0'))
        self.OPEN_MAKER_DURATION_MINUTES = int(os.getenv('OPEN_MAKER_DURATION_MINUTES', '3'))

        # 手续费率
        self.MAKER_FEE_RATE = float(os.getenv('MAKER_FEE_RATE', '0.0002'))
        self.TAKER_FEE_RATE = float(os.getenv('TAKER_FEE_RATE', '0.0006'))
        self.FEE_RATE = float(os.getenv('FEE_RATE', '0.0004'))

        # 回测时间范围
        self.DATE_FROM = os.getenv('DATE_FROM', '2024-1-1 00:00:00')
        self.DATE_TO = os.getenv('DATE_TO', '2024-1-10 23:59:59')

        # 止损止盈 (更新默认值)
        self.STOP_LOSS_POINTS = float(os.getenv('STOP_LOSS_POINTS', '0.02'))
        self.TP_LEVELS = json.loads(os.getenv('TP_LEVELS', '[1.006, 1.012, 1.018, 1.024, 1.03]'))
        self.TP_RATIO_PER_LEVEL = float(os.getenv('TP_RATIO_PER_LEVEL', '0.0'))
        self.DRAWDOWN_POINTS = float(os.getenv('DRAWDOWN_POINTS', '0.0002'))
        self.CLOSE_TIME_MINUTES = float(os.getenv('CLOSE_TIME_MINUTES', '9999'))
        self.CLOSE_DECAY_POINTS = float(os.getenv('CLOSE_DECAY_POINTS', '9999'))
        self.TIMEOUT_CLOSE_RATIO = float(os.getenv('TIMEOUT_CLOSE_RATIO', '0.0001'))

        # T0 特殊参数
        self.T0_HIST_1D_LIMIT = float(os.getenv('T0_HIST_1D_LIMIT', '-999'))

        # 版本标识
        self.VERSION = os.getenv('VERSION', 'V5.0')

        # 订单巡检与反向同步
        self.ORDER_SYNC_INTERVAL = int(os.getenv('ORDER_SYNC_INTERVAL', '120'))
        self.ORDER_SYNC_LOG_LIMIT = int(os.getenv('ORDER_SYNC_LOG_LIMIT', '5'))

        # 飞书机器人
        self.FEISHU_WEBHOOK = os.getenv('FEISHU_WEBHOOK', '')
        self.FEISHU_ENABLED = os.getenv('FEISHU_ENABLED', '0').lower() in ('1', 'true', 'yes')
        # 交易历史报告发送间隔（分钟），0表示禁用
        self.TRADE_HISTORY_REPORT_INTERVAL = int(os.getenv('TRADE_HISTORY_REPORT_INTERVAL', '0'))
        # 交易历史报告显示最近几次交易
        self.TRADE_HISTORY_REPORT_COUNT = int(os.getenv('TRADE_HISTORY_REPORT_COUNT', '10'))

        # Web服务
        self.WEB_HOST = os.getenv('WEB_HOST', '0.0.0.0')
        self.WEB_PORT = int(os.getenv('WEB_PORT', '8076'))
        self.WEB_ENABLED = os.getenv('WEB_ENABLED', '1').lower() in ('1', 'true', 'yes')

        # 登录白名单（逗号分隔的手机号列表）
        self.ALLOWED_PHONES = [
            phone.strip()
            for phone in os.getenv('ALLOWED_PHONES', '18600028001').split(',')
            if phone.strip()
        ]

        # 日志文件路径（用于Web日志页面）
        self.TRADING_LOG_PATH = os.getenv('TRADING_LOG_PATH', str(self.base_dir / 'trading.log'))

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self.config_data.get(key, default)

    def set(self, key: str, value: Any):
        """设置配置值"""
        self.config_data[key] = value
        self.save()

    def save(self):
        """保存配置到文件"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config_data, f, indent=2, ensure_ascii=False)

    def reload(self):
        """重新加载配置"""
        self._load_config()
        self._load_env()


# 全局配置实例
config = Config()
