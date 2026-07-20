#!/usr/bin/env python3
"""Send a rate-limited Feishu alert after an abnormal systemd service exit."""

import argparse
import math
import os
import socket
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.logger import get_logger
from interaction_module.feishu_bot import FeishuBot


logger = get_logger("scripts.notify_db_trading_failure")
TZ_EAST8 = timezone(timedelta(hours=8))


def is_abnormal_exit(service_result: Optional[str]) -> bool:
    """Return whether a systemd SERVICE_RESULT represents an abnormal exit."""
    normalized = (service_result or "").strip().lower()
    return normalized not in ("", "success")


def should_send_alert(
    state_file: Path,
    now: float,
    cooldown_seconds: int = 600,
) -> bool:
    """Return whether the alert cooldown permits a new notification."""
    try:
        last_sent = float(state_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return True

    if not math.isfinite(last_sent):
        return True
    if last_sent > now:
        return False
    return now - last_sent >= cooldown_seconds


def record_alert(state_file: Path, now: float) -> None:
    """Atomically persist the timestamp of a successfully sent alert."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(state_file.parent),
            prefix=f".{state_file.name}.",
            delete=False,
        ) as temporary:
            temporary.write(str(now))
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, state_file)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def build_alert_message(
    unit: str,
    result: str,
    exit_code: str,
    exit_status: str,
    hostname: str,
    timestamp: str,
) -> str:
    """Build a Chinese alert containing systemd exit diagnostics."""
    return (
        "交易服务异常退出\n"
        f"服务: {unit}\n"
        f"主机: {hostname}\n"
        f"systemd 结果: {result}\n"
        f"退出类型: {exit_code}\n"
        f"退出状态: {exit_status}\n"
        f"时间: {timestamp}\n"
        "systemd 将尝试自动重启该服务。"
    )


def notify_failure(
    unit: str,
    result: Optional[str],
    exit_code: str,
    exit_status: str,
    state_file: Path,
    cooldown_seconds: int = 600,
    *,
    bot: Optional[FeishuBot] = None,
    clock: Callable[[], float] = time.time,
    hostname: Callable[[], str] = socket.gethostname,
) -> bool:
    """Send one abnormal-exit alert when permitted by the cooldown."""
    if not is_abnormal_exit(result):
        logger.info("服务正常停止，不发送飞书告警: unit=%s result=%s", unit, result)
        return False

    now = clock()
    state_file = Path(state_file)
    if not should_send_alert(state_file, now, cooldown_seconds):
        logger.warning(
            "异常退出告警处于冷却期，跳过发送: unit=%s result=%s",
            unit,
            result,
        )
        return False

    timestamp = datetime.fromtimestamp(now, TZ_EAST8).strftime(
        "%Y-%m-%d %H:%M:%S %z"
    )
    message = build_alert_message(
        unit=unit,
        result=result or "",
        exit_code=exit_code,
        exit_status=exit_status,
        hostname=hostname(),
        timestamp=timestamp,
    )

    alert_bot = bot if bot is not None else FeishuBot()
    try:
        sent = alert_bot.send_message(message)
    except Exception:
        logger.exception("发送交易服务异常退出飞书告警时发生异常")
        return False

    if sent is not True:
        logger.error("交易服务异常退出飞书告警发送失败，未记录冷却时间")
        return False

    try:
        record_alert(state_file, now)
    except Exception:
        logger.exception("飞书告警已发送，但记录告警冷却时间失败")
    return True


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="发送交易服务异常退出飞书告警")
    parser.add_argument("--unit", required=True, help="systemd 服务名称")
    parser.add_argument("--result", required=True, help="systemd SERVICE_RESULT")
    parser.add_argument("--exit-code", required=True, help="systemd EXIT_CODE")
    parser.add_argument("--exit-status", required=True, help="systemd EXIT_STATUS")
    parser.add_argument("--state-file", required=True, type=Path, help="告警冷却状态文件")
    parser.add_argument(
        "--cooldown-seconds",
        type=int,
        default=600,
        help="同类告警冷却秒数，默认 600",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        notify_failure(
            unit=args.unit,
            result=args.result,
            exit_code=args.exit_code,
            exit_status=args.exit_status,
            state_file=args.state_file,
            cooldown_seconds=args.cooldown_seconds,
            bot=FeishuBot(),
        )
    except Exception:
        logger.exception("交易服务退出告警程序发生未预期异常")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
