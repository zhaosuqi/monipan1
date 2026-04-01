#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易参数热加载模块

每分钟检测 core/trading_params.json 是否有变化，
有变化时自动应用到运行中的 config，并通过飞书发送变更通知。

用法：
    from core.config_hot_reload import ConfigHotReloader

    reloader = ConfigHotReloader(feishu_bot=feishu_bot)
    # 在主循环中每分钟调用
    reloader.check_and_reload()
"""

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import config
from core.logger import get_logger

logger = get_logger('core.config_hot_reload')

# 检查间隔（秒）
CHECK_INTERVAL = 60

# 东八区时区
TZ_EAST8 = timezone(timedelta(hours=8))


class ConfigHotReloader:
    """交易参数 JSON 热加载器"""

    def __init__(self, feishu_bot=None):
        """
        初始化热加载器

        Args:
            feishu_bot: FeishuBot 实例，用于发送变更通知（可选）
        """
        self.logger = logger
        self.feishu_bot = feishu_bot

        # JSON 文件路径
        self.json_path = Path(__file__).parent / 'trading_params.json'

        # 上次文件修改时间
        self.last_mtime: float = 0
        # 上次检查时间
        self.last_check_time: float = 0
        # 当前已加载的参数快照
        self.last_params: Dict[str, Any] = {}

        # 初始加载
        self._load_initial()

    def _load_initial(self):
        """初始加载 JSON 参数并应用到 config"""
        if not self.json_path.exists():
            self.logger.warning(f"交易参数文件不存在: {self.json_path}")
            return

        try:
            self.last_mtime = self.json_path.stat().st_mtime
            with open(self.json_path, 'r', encoding='utf-8') as f:
                self.last_params = json.load(f)

            # 初始加载时应用所有参数
            applied = self._apply_params(self.last_params)
            self.logger.info(f"初始加载交易参数完成，共 {applied} 个参数已应用")
            self.last_check_time = time.time()

        except Exception as e:
            self.logger.error(f"初始加载交易参数失败: {e}", exc_info=True)

    def check_and_reload(self) -> bool:
        """
        检查 JSON 文件是否有变化，有变化则重新加载并通知。
        应在主循环中调用，内部自带 60 秒节流。

        Returns:
            bool: 如果参数发生了实际变更并重载成功返回 True，否则返回 False
        """
        now = time.time()

        # 节流：不到检查间隔则跳过
        if now - self.last_check_time < CHECK_INTERVAL:
            return False

        self.last_check_time = now

        if not self.json_path.exists():
            return False

        try:
            current_mtime = self.json_path.stat().st_mtime

            # 文件未修改
            if current_mtime <= self.last_mtime:
                return False

            self.logger.info("检测到交易参数文件变更，开始重新加载...")

            # 读取新参数
            with open(self.json_path, 'r', encoding='utf-8') as f:
                new_params = json.load(f)

            # 比较差异
            changes = self._diff_params(self.last_params, new_params)

            reloaded = False
            if changes:
                # 应用新参数
                self._apply_params(new_params)

                # 记录变更日志
                self._log_changes(changes)

                # 发送飞书通知
                self._notify_changes(changes)

                self.logger.info(f"交易参数热加载完成，{len(changes)} 个参数已更新")
                reloaded = True
            else:
                self.logger.info("文件已修改但参数值无变化")

            # 更新快照
            self.last_mtime = current_mtime
            self.last_params = new_params

            return reloaded

        except json.JSONDecodeError as e:
            self.logger.error(f"交易参数 JSON 格式错误: {e}")
            return False
        except Exception as e:
            self.logger.error(f"交易参数热加载异常: {e}", exc_info=True)
            return False

    def _diff_params(self, old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        对比新旧参数，返回变更项

        Returns:
            {param_key: {'old': old_value, 'new': new_value}, ...}
        """
        changes = {}

        for key, new_val in new.items():
            old_val = old.get(key)
            if old_val != new_val:
                changes[key] = {'old': old_val, 'new': new_val}

        # 检查被删除的参数
        for key in old:
            if key not in new:
                changes[key] = {'old': old[key], 'new': '(已删除)'}

        return changes

    def _apply_params(self, params: Dict[str, Any]) -> int:
        """
        将参数应用到 config 单例

        JSON key (小写蛇形) 通过 .upper() 转换为 config 属性名（大写蛇形）

        Returns:
            成功应用的参数数量
        """
        applied = 0

        for key, value in params.items():
            attr_name = key.upper()

            try:
                setattr(config, attr_name, value)
                applied += 1
            except Exception as e:
                self.logger.warning(f"设置参数 {attr_name}={value} 失败: {e}")

        return applied

    def _log_changes(self, changes: Dict[str, Dict[str, Any]]):
        """将变更记录到日志"""
        self.logger.info("=" * 50)
        self.logger.info("交易参数变更明细：")
        for key, detail in changes.items():
            old_val = detail['old']
            new_val = detail['new']
            self.logger.info(f"  {key}: {old_val} → {new_val}")
        self.logger.info("=" * 50)

    def _notify_changes(self, changes: Dict[str, Dict[str, Any]]):
        """通过飞书发送参数变更通知"""
        if not self.feishu_bot:
            self.logger.debug("未配置飞书机器人，跳过变更通知")
            return

        try:
            now_str = datetime.now(TZ_EAST8).strftime("%Y-%m-%d %H:%M:%S")

            # 构建变更消息
            lines = [
                f"⚙️ 交易参数热更新通知",
                f"时间：{now_str}",
                f"变更数量：{len(changes)} 个参数",
                f"{'─' * 30}",
            ]

            for key, detail in changes.items():
                old_val = detail['old']
                new_val = detail['new']
                # 格式化值，避免过长
                old_str = self._format_value(old_val)
                new_str = self._format_value(new_val)
                lines.append(f"• {key}: {old_str} → {new_str}")

            lines.append(f"{'─' * 30}")
            lines.append(f"参数文件：trading_params.json")

            message = "\n".join(lines)
            self.feishu_bot.send_message(message)
            self.logger.info("飞书参数变更通知已发送")

        except Exception as e:
            self.logger.error(f"发送飞书参数变更通知失败: {e}")

    @staticmethod
    def _format_value(value: Any) -> str:
        """格式化参数值用于显示"""
        if isinstance(value, list):
            return json.dumps(value)
        if isinstance(value, float):
            # 保持精度但去除不必要的零
            return f"{value:g}"
        if value is None:
            return "(无)"
        return str(value)

    def report_all_params(self):
        """
        一次性输出所有当前参数到日志和飞书。
        适合在系统启动后首次运行信号判断时调用。
        """
        params = self.last_params
        if not params:
            self.logger.warning("无可用交易参数")
            return

        # 输出到日志
        self.logger.info("=" * 55)
        self.logger.info(f"当前交易参数一览（共 {len(params)} 个）：")
        for key in sorted(params.keys()):
            self.logger.info(f"  {key} = {self._format_value(params[key])}")
        self.logger.info("=" * 55)

        # 发送飞书
        if not self.feishu_bot:
            return

        try:
            now_str = datetime.now(TZ_EAST8).strftime("%Y-%m-%d %H:%M:%S")
            lines = [
                f"📋 交易参数全量报告",
                f"时间：{now_str}",
                f"参数数量：{len(params)} 个",
                f"{'─' * 30}",
            ]
            for key in sorted(params.keys()):
                lines.append(f"• {key} = {self._format_value(params[key])}")
            lines.append(f"{'─' * 30}")
            lines.append(f"参数文件：trading_params.json")

            message = "\n".join(lines)
            self.feishu_bot.send_message(message)
            self.logger.info("飞书全量参数报告已发送")
        except Exception as e:
            self.logger.error(f"发送飞书全量参数报告失败: {e}")

    def get_current_params(self) -> Dict[str, Any]:
        """获取当前已加载的参数快照（只读副本）"""
        return dict(self.last_params)

    def force_reload(self):
        """强制重新加载（忽略时间间隔和 mtime 检查）"""
        if not self.json_path.exists():
            self.logger.warning(f"交易参数文件不存在: {self.json_path}")
            return

        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                new_params = json.load(f)

            changes = self._diff_params(self.last_params, new_params)

            self._apply_params(new_params)

            if changes:
                self._log_changes(changes)
                self._notify_changes(changes)

            self.last_mtime = self.json_path.stat().st_mtime
            self.last_params = new_params
            self.logger.info(f"强制重载完成，共 {len(new_params)} 个参数")

        except Exception as e:
            self.logger.error(f"强制重载失败: {e}", exc_info=True)
