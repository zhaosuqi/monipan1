#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主程序入口 - 模块化架构
"""

import sys
import time
import signal
import threading
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from core.config import config
from core.database import get_db
from core.logger import get_logger

# 导入各模块
from data_module import KlineFetcher, IndicatorCalculator, DataWriter, DataNotifier
from signal_module import SignalCalculator, PositionManager, TPManager, SLManager
from trade_module import OrderExecutor, AccountTracker
from interaction_module import WebInterface, FeishuBot

logger = get_logger('main')


class TradingBot:
    """交易机器人主类"""

    def __init__(self):
        logger.info("=" * 80)
        logger.info("交易机器人启动")
        logger.info("=" * 80)

        # 初始化配置
        logger.info(f"模式: {'回测模式' if config.REPLAY_MODE else '实盘模式'}")
        logger.info(f"交易对: {config.SYMBOL}")
        logger.info(f"仓位大小: {config.POSITION_BTC} BTC")

        # 初始化数据库
        self.db = get_db()

        # 初始化各模块
        self._init_modules()

        # 运行标志
        self.running = False
        self.web_thread = None

        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _init_modules(self):
        """初始化所有模块"""
        logger.info("初始化模块...")

        # 模块1: 数据获取与计算
        self.kline_fetcher = KlineFetcher()
        self.indicator_calculator = IndicatorCalculator()
        self.data_writer = DataWriter()
        self.data_notifier = DataNotifier()
        logger.info("  ✓ 数据模块")

        # 模块2: 信号计算
        self.signal_calculator = SignalCalculator()
        self.position_manager = PositionManager()
        self.tp_manager = TPManager()
        self.sl_manager = SLManager()
        logger.info("  ✓ 信号模块")

        # 模块3: 交易执行
        self.order_executor = OrderExecutor()
        logger.info("  ✓ 交易模块")

        # 模块4: 交互
        self.feishu_bot = FeishuBot()
        logger.info("  ✓ 交互模块")

        # 订阅数据更新通知
        self.data_notifier.subscribe(self.on_new_data)

        logger.info("所有模块初始化完成")

    def _signal_handler(self, signum, frame):
        """信号处理器"""
        logger.info(f"收到信号 {signum}，准备退出...")
        self.running = False

    def on_new_data(self, data):
        """处理新数据"""
        try:
            # 计算信号
            signal = self.signal_calculator.calculate_open_signal(data)

            if signal:
                logger.info(f"产生信号: {signal.action} {signal.side} - {signal.reason}")

                # 执行订单
                trace_id = f"trace-{int(time.time())}"
                order = self.order_executor.execute_open_order(signal, trace_id)

                if order:
                    # 发送通知
                    self.feishu_bot.send_trade_notification({
                        'action': signal.action,
                        'side': signal.side,
                        'reason': signal.reason
                    })
        except Exception as e:
            logger.error(f"处理数据失败: {e}", exc_info=True)

    def run_data_loop(self):
        """数据采集循环"""
        logger.info("启动数据采集循环")

        while self.running:
            try:
                # 1. 获取K线
                klines = self.kline_fetcher.fetch_latest_klines(limit=1000)

                if not klines:
                    logger.warning("未获取到K线数据")
                    time.sleep(60)
                    continue

                # 2. 计算指标
                indicators = self.indicator_calculator.calculate_all(klines)

                # 3. 写入数据库
                self.data_writer.write_klines(klines)
                self.data_writer.write_indicators(indicators)

                # 4. 通知订阅者
                self.data_notifier.notify_new_data(indicators)

                # 5. 休眠
                time.sleep(60)

            except Exception as e:
                logger.error(f"数据循环错误: {e}", exc_info=True)
                time.sleep(60)

    def run_web_server(self):
        """运行Web服务器"""
        try:
            web = WebInterface()
            web.run()
        except Exception as e:
            logger.error(f"Web服务器错误: {e}", exc_info=True)

    def run(self):
        """主循环"""
        logger.info("进入主循环")
        self.running = True

        try:
            # 启动Web服务器（在独立线程）
            if config.WEB_ENABLED:
                self.web_thread = threading.Thread(
                    target=self.run_web_server,
                    daemon=True
                )
                self.web_thread.start()
                logger.info(f"Web服务已启动: http://{config.WEB_HOST}:{config.WEB_PORT}")

            # 运行数据采集循环
            self.run_data_loop()

        except Exception as e:
            logger.error(f"主循环错误: {e}", exc_info=True)

        finally:
            self.shutdown()

    def shutdown(self):
        """关闭机器人"""
        logger.info("关闭机器人...")

        # 等待Web线程结束
        if self.web_thread and self.web_thread.is_alive():
            logger.info("等待Web服务关闭...")
            self.web_thread.join(timeout=5)

        # 关闭数据库连接
        self.db.close()

        logger.info("机器人已停止")


def main():
    """主函数"""
    try:
        # 创建并启动机器人
        bot = TradingBot()
        bot.run()

    except Exception as e:
        logger.error(f"程序异常: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
