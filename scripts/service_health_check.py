#!/usr/bin/env python3
"""服务健康检查：服务存活、数据新鲜度、Web 可达性，异常时合并飞书告警。

由 systemd timer 每分钟触发一次。任何异常都只记日志，退出码恒为 0，
避免 timer 因非零退出进入 failed 状态。
"""

import logging
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# scripts 目录没有 __init__.py，上面把项目根目录加入 sys.path 后可按
# 命名空间包方式 import，直接复用告警器的冷却状态判断与原子写实现。
from scripts.notify_db_trading_failure import (
    AlertState,
    inspect_alert_state,
    record_alert,
)

logger = logging.getLogger("scripts.service_health_check")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

TZ_EAST8 = timezone(timedelta(hours=8))

DEFAULT_MAX_KLINE_AGE_SECONDS = 180
DEFAULT_ALERT_COOLDOWN_SECONDS = 600
SYSTEMCTL_TIMEOUT_SECONDS = 10
HTTP_TIMEOUT_SECONDS = 5

MONITORED_UNITS = (
    "db-driven-trading.service",
    "realtime-kline-sync.service",
    "sync-macd-indicators.service",
    "kline-web.service",
)
KLINE_TABLE = "klines_1m"
INDICATOR_TABLE = "klines_1m_macd_smooth_ma"

KLINE_ITEM = "kline_freshness"
INDICATOR_ITEM = "indicator_freshness"
WEB_ITEM = "web_reachable"

_ITEM_LABELS = {
    KLINE_ITEM: "K线数据新鲜度",
    INDICATOR_ITEM: "指标数据新鲜度",
    WEB_ITEM: "Web 服务可达性",
}


def item_label(item: str) -> str:
    """返回检查项的中文显示名。"""
    if item.startswith("service:"):
        return f"服务存活 ({item.split(':', 1)[1]})"
    return _ITEM_LABELS.get(item, item)


def resolve_state_dir(env: Optional[Dict[str, str]] = None) -> Path:
    """按优先级解析冷却状态目录：HEALTH_STATE_DIR > /run 可写目录 > 项目 data 目录。"""
    environ = os.environ if env is None else env
    override = environ.get("HEALTH_STATE_DIR")
    if override:
        return Path(override)
    runtime_dir = Path("/run/service-health-check")
    try:
        if runtime_dir.is_dir() and os.access(runtime_dir, os.W_OK):
            return runtime_dir
    except OSError:
        pass
    return PROJECT_ROOT / "data" / ".health_state"


def _state_file_for(state_dir: Path, item: str) -> Path:
    safe_item = re.sub(r"[^A-Za-z0-9_.-]", "_", item) or "unknown-item"
    return Path(state_dir) / f"{safe_item}.state"


def default_systemctl_runner(unit: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl", "is-active", unit],
        capture_output=True,
        text=True,
        timeout=SYSTEMCTL_TIMEOUT_SECONDS,
        check=False,
    )


def check_services(
    systemctl_runner: Optional[Callable[[str], subprocess.CompletedProcess]] = None,
) -> Dict[str, Optional[str]]:
    """检查各 systemd 服务存活状态，返回 {检查项: 异常明细或 None}。

    systemctl 不存在（如 macOS 开发机）时跳过该项检查并记 info 日志。
    """
    if shutil.which("systemctl") is None:
        logger.info("未找到 systemctl，跳过服务存活检查（非 systemd 环境）")
        return {}
    runner = systemctl_runner or default_systemctl_runner
    results: Dict[str, Optional[str]] = {}
    for unit in MONITORED_UNITS:
        item = f"service:{unit}"
        try:
            completed = runner(unit)
            status = (completed.stdout or "").strip()
        except Exception as exc:
            results[item] = f"服务 {unit} 状态查询失败: {exc}"
            continue
        if status == "active":
            results[item] = None
        else:
            results[item] = (
                f"服务 {unit} 未运行 (systemctl is-active: {status or 'unknown'})"
            )
    return results


def parse_open_time(value: Any) -> datetime:
    """解析 open_time（支持 `T` 与空格两种分隔），朴素时间按 UTC 处理。"""
    parsed = datetime.fromisoformat(str(value).strip())
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def check_table_freshness(
    db_path: Any,
    table: str,
    max_age_seconds: int,
    now: datetime,
) -> Optional[str]:
    """检查数据表最新 open_time 的新鲜度，异常时返回明细，正常返回 None。"""
    path = Path(db_path)
    if not path.exists():
        return f"数据库文件不存在: {path}"
    try:
        with sqlite3.connect(str(path)) as conn:
            row = conn.execute(f"SELECT MAX(open_time) FROM {table}").fetchone()
    except Exception as exc:
        return f"查询 {table} 最新数据失败: {exc}"
    if not row or row[0] is None:
        return f"{table} 表为空，无数据"
    try:
        latest = parse_open_time(row[0])
    except Exception:
        return f"{table} 最新 open_time 无法解析: {row[0]!r}"
    age_seconds = (now - latest).total_seconds()
    if age_seconds > max_age_seconds:
        return (
            f"{table} 数据滞后 {age_seconds:.0f} 秒 "
            f"(最新 {row[0]}, 阈值 {max_age_seconds} 秒)"
        )
    return None


def default_http_get(url: str, timeout: int = HTTP_TIMEOUT_SECONDS) -> int:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        # 任意 HTTP 响应（含 302 登录跳转、4xx）都说明 Web 进程存活
        return exc.code


def check_web(
    url: str,
    http_getter: Optional[Callable[[str], Any]] = None,
) -> Optional[str]:
    """检查 Web 可达性，连接错误/超时返回异常明细，正常返回 None。"""
    getter = http_getter or default_http_get
    try:
        getter(url)
    except urllib.error.HTTPError:
        # 注入的 getter 直接抛 HTTPError 时同样视为存活
        return None
    except Exception as exc:
        return f"Web 服务不可达 {url}: {exc}"
    return None


def build_alert_message(
    failures: List[Tuple[str, str]],
    hostname: str,
    timestamp: str,
) -> str:
    """把多个异常项合并成一条中文告警消息。"""
    lines = [
        "服务健康检查异常",
        f"主机: {hostname}",
        f"时间: {timestamp}",
        "异常项:",
    ]
    lines.extend(f"- {detail}" for _, detail in failures)
    lines.append("请检查相关服务与数据同步状态。")
    return "\n".join(lines)


def build_recovery_message(item: str, hostname: str, timestamp: str) -> str:
    return (
        "服务健康检查恢复\n"
        f"主机: {hostname}\n"
        f"时间: {timestamp}\n"
        f"已恢复: {item_label(item)}"
    )


def _create_feishu_bot():
    from interaction_module.feishu_bot import FeishuBot

    return FeishuBot()


def run_health_checks(
    *,
    state_dir: Any,
    db_path: Any,
    web_url: str,
    max_age_seconds: int = DEFAULT_MAX_KLINE_AGE_SECONDS,
    cooldown_seconds: int = DEFAULT_ALERT_COOLDOWN_SECONDS,
    bot: Optional[Any] = None,
    clock: Callable[[], float] = time.time,
    hostname: Callable[[], str] = socket.gethostname,
    systemctl_runner: Optional[Callable[[str], subprocess.CompletedProcess]] = None,
    http_getter: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """执行全部检查并按项冷却告警，返回本轮结果摘要（供测试断言）。"""
    now = clock()
    now_dt = datetime.fromtimestamp(now, timezone.utc)
    state_dir = Path(state_dir)

    # {检查项: 异常明细或 None}
    results: Dict[str, Optional[str]] = check_services(
        systemctl_runner=systemctl_runner
    )
    results[KLINE_ITEM] = check_table_freshness(
        db_path, KLINE_TABLE, max_age_seconds, now_dt
    )
    results[INDICATOR_ITEM] = check_table_freshness(
        db_path, INDICATOR_TABLE, max_age_seconds, now_dt
    )
    results[WEB_ITEM] = check_web(web_url, http_getter=http_getter)

    pending_alerts: List[Tuple[str, str]] = []
    pending_recoveries: List[str] = []
    for item, detail in results.items():
        state_file = _state_file_for(state_dir, item)
        if detail is None:
            if state_file.exists():
                pending_recoveries.append(item)
            continue
        logger.warning("健康检查异常: %s", detail)
        state = inspect_alert_state(state_file, now, cooldown_seconds)
        if state is AlertState.COOLDOWN:
            logger.info("检查项 %s 告警处于冷却期，跳过发送", item)
            continue
        if state is AlertState.UNAVAILABLE:
            logger.error("检查项 %s 冷却状态不可读，本轮跳过告警以避免重复", item)
            continue
        pending_alerts.append((item, detail))

    summary = {
        "failures": {item: detail for item, detail in results.items() if detail},
        "alert_sent": False,
        "recoveries_sent": [],
    }
    if not pending_alerts and not pending_recoveries:
        return summary

    alert_bot = bot if bot is not None else _create_feishu_bot()
    timestamp = datetime.fromtimestamp(now, TZ_EAST8).strftime(
        "%Y-%m-%d %H:%M:%S %z"
    )
    host = hostname()

    if pending_alerts:
        message = build_alert_message(pending_alerts, host, timestamp)
        try:
            sent = alert_bot.send_message(message)
        except Exception:
            logger.exception("发送健康检查飞书告警时发生异常")
            sent = False
        if sent is True:
            summary["alert_sent"] = True
            for item, _ in pending_alerts:
                try:
                    record_alert(_state_file_for(state_dir, item), now)
                except Exception:
                    logger.exception("告警已发送，但记录检查项 %s 冷却时间失败", item)
        else:
            logger.error("健康检查飞书告警发送失败，未记录冷却时间")

    for item in pending_recoveries:
        message = build_recovery_message(item, host, timestamp)
        try:
            sent = alert_bot.send_message(message)
        except Exception:
            logger.exception("发送检查项 %s 恢复通知时发生异常", item)
            sent = False
        if sent is True:
            summary["recoveries_sent"].append(item)
            try:
                _state_file_for(state_dir, item).unlink()
            except OSError:
                logger.exception("恢复通知已发送，但删除检查项 %s 状态文件失败", item)
        else:
            logger.error("检查项 %s 恢复通知发送失败，保留下轮重试", item)

    return summary


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.error("环境变量 %s=%r 非法，使用默认值 %s", name, raw, default)
        return default


def main(argv=None) -> int:
    try:
        from core.config import config

        run_health_checks(
            state_dir=resolve_state_dir(),
            db_path=config.DB_PATH,
            web_url=f"http://127.0.0.1:{config.WEB_PORT}/",
            max_age_seconds=_env_int(
                "HEALTH_MAX_KLINE_AGE_SECONDS", DEFAULT_MAX_KLINE_AGE_SECONDS
            ),
            cooldown_seconds=_env_int(
                "HEALTH_ALERT_COOLDOWN_SECONDS", DEFAULT_ALERT_COOLDOWN_SECONDS
            ),
        )
    except Exception:
        logger.exception("服务健康检查发生未预期异常")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
