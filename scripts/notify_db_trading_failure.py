#!/usr/bin/env python3
"""Send a rate-limited Feishu alert after an abnormal systemd service exit."""

import argparse
import logging
import math
import os
import re
import socket
import stat
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger("scripts.notify_db_trading_failure")
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


class AlertState(Enum):
    ALLOWED = "allowed"
    COOLDOWN = "cooldown"
    UNAVAILABLE = "unavailable"


def is_abnormal_exit(service_result: Optional[str]) -> bool:
    """Return whether a systemd SERVICE_RESULT represents an abnormal exit."""
    normalized = (service_result or "").strip().lower()
    return normalized not in ("", "success")


def inspect_alert_state(
    state_file: Path,
    now: float,
    cooldown_seconds: int = 600,
) -> AlertState:
    """Inspect one cooldown state without collapsing I/O failure into cooldown."""
    try:
        last_sent = float(state_file.read_text(encoding="utf-8").strip())
    except FileNotFoundError:
        return AlertState.ALLOWED
    except OSError:
        logger.exception("读取告警冷却状态失败: %s", state_file)
        return AlertState.UNAVAILABLE
    except ValueError:
        return AlertState.ALLOWED

    if not math.isfinite(last_sent):
        return AlertState.ALLOWED
    if last_sent > now:
        if last_sent - now > cooldown_seconds:
            return AlertState.ALLOWED
        return AlertState.COOLDOWN
    if now - last_sent >= cooldown_seconds:
        return AlertState.ALLOWED
    return AlertState.COOLDOWN


def should_send_alert(
    state_file: Path,
    now: float,
    cooldown_seconds: int = 600,
) -> bool:
    """Return whether one readable cooldown state permits notification."""
    return (
        inspect_alert_state(state_file, now, cooldown_seconds)
        is AlertState.ALLOWED
    )


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


def resolve_fallback_state_file(
    unit: str,
    *,
    uid: Optional[int] = None,
    runtime_root: Path = Path("/run/user"),
    temp_root: Optional[Path] = None,
) -> Path:
    """Return a deterministic, user-owned fallback cooldown state path."""
    resolved_uid = os.getuid() if uid is None else uid
    safe_unit = re.sub(r"[^A-Za-z0-9_.-]", "_", unit) or "unknown-service"
    state_name = f".{safe_unit}.failure-alert"
    runtime_directory = Path(runtime_root) / str(resolved_uid)

    try:
        runtime_info = runtime_directory.stat()
    except OSError:
        runtime_info = None
    if (
        runtime_info is not None
        and stat.S_ISDIR(runtime_info.st_mode)
        and runtime_info.st_uid == resolved_uid
        and os.access(runtime_directory, os.W_OK | os.X_OK)
    ):
        return runtime_directory / state_name

    temporary_root = Path(temp_root) if temp_root is not None else Path(
        tempfile.gettempdir()
    )
    private_directory = temporary_root / f"db-trading-failure-alert-{resolved_uid}"
    private_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_info = private_directory.lstat()
    if not stat.S_ISDIR(private_info.st_mode) or private_info.st_uid != resolved_uid:
        raise PermissionError(f"不安全的备用告警状态目录: {private_directory}")
    private_directory.chmod(0o700)
    return private_directory / state_name


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


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是正整数")
    return parsed


def notify_failure(
    unit: str,
    result: Optional[str],
    exit_code: str,
    exit_status: str,
    state_file: Path,
    cooldown_seconds: int = 600,
    *,
    fallback_state_file: Optional[Path] = None,
    bot: Optional[Any] = None,
    clock: Callable[[], float] = time.time,
    hostname: Callable[[], str] = socket.gethostname,
) -> bool:
    """Send one abnormal-exit alert when permitted by the cooldown."""
    if (
        isinstance(cooldown_seconds, bool)
        or not isinstance(cooldown_seconds, int)
        or cooldown_seconds <= 0
    ):
        logger.error("告警冷却秒数必须为正整数: %r", cooldown_seconds)
        return False

    if not is_abnormal_exit(result):
        logger.info("服务正常停止，不发送飞书告警: unit=%s result=%s", unit, result)
        return False

    now = clock()
    state_file = Path(state_file)
    primary_state = inspect_alert_state(state_file, now, cooldown_seconds)
    if primary_state is AlertState.COOLDOWN:
        logger.warning(
            "异常退出告警处于冷却期，跳过发送: unit=%s result=%s",
            unit,
            result,
        )
        return False

    resolved_fallback_state_file = None
    try:
        resolved_fallback_state_file = (
            Path(fallback_state_file)
            if fallback_state_file is not None
            else resolve_fallback_state_file(unit)
        )
    except Exception:
        logger.exception("无法准备备用告警冷却状态")
        fallback_state = AlertState.UNAVAILABLE
    else:
        if resolved_fallback_state_file == state_file:
            fallback_state = primary_state
        else:
            fallback_state = inspect_alert_state(
                resolved_fallback_state_file,
                now,
                cooldown_seconds,
            )

    if fallback_state is AlertState.COOLDOWN:
        logger.warning(
            "备用异常退出告警处于冷却期，跳过发送: unit=%s result=%s",
            unit,
            result,
        )
        return False
    if (
        primary_state is AlertState.UNAVAILABLE
        and fallback_state is AlertState.UNAVAILABLE
    ):
        logger.error("主告警和备用告警状态均不可用，停止发送以避免重复告警")
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

    alert_bot = bot if bot is not None else _create_feishu_bot()
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
        logger.exception("飞书告警已发送，但记录主告警冷却时间失败")
    if (
        resolved_fallback_state_file is not None
        and resolved_fallback_state_file != state_file
    ):
        try:
            record_alert(resolved_fallback_state_file, now)
        except Exception:
            logger.exception("飞书告警已发送，但记录备用告警冷却时间失败")
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
        type=_positive_int,
        default=600,
        help="同类告警冷却秒数，默认 600",
    )
    return parser.parse_args(argv)


def _create_feishu_bot():
    from interaction_module.feishu_bot import FeishuBot

    return FeishuBot()


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
            bot=_create_feishu_bot(),
        )
    except Exception:
        logger.exception("交易服务退出告警程序发生未预期异常")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
