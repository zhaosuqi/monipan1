import os
import subprocess
import stat
import sys
import textwrap
from pathlib import Path
from unittest.mock import Mock

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "notify_db_trading_failure.py"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import notify_db_trading_failure as notifier


class RecordingBot:
    def __init__(self, result=True, error=None):
        self.result = result
        self.error = error
        self.messages = []

    def send_message(self, message):
        self.messages.append(message)
        if self.error:
            raise self.error
        return self.result


def test_module_import_does_not_depend_on_project_logger():
    probe = textwrap.dedent(
        f"""
        import builtins
        import importlib.util

        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "core.logger":
                raise RuntimeError("project logger unavailable")
            return original_import(name, *args, **kwargs)

        builtins.__import__ = guarded_import
        spec = importlib.util.spec_from_file_location("notifier_probe", {str(SCRIPT_PATH)!r})
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("result", [None, "", "success"])
def test_successful_or_empty_result_is_not_abnormal(result):
    assert notifier.is_abnormal_exit(result) is False


@pytest.mark.parametrize(
    "result",
    ["exit-code", "signal", "timeout", "watchdog", "core-dump", "resources"],
)
def test_systemd_failure_results_are_abnormal(result):
    assert notifier.is_abnormal_exit(result) is True


def test_first_alert_is_allowed_when_state_is_missing(tmp_path):
    assert notifier.should_send_alert(tmp_path / "missing", now=1000) is True


@pytest.mark.parametrize("content", ["invalid", "", "nan", "inf"])
def test_invalid_state_allows_alert_without_crashing(tmp_path, content):
    state_file = tmp_path / "state"
    state_file.write_text(content, encoding="utf-8")

    assert notifier.should_send_alert(state_file, now=1000) is True


def test_alert_inside_cooldown_is_suppressed(tmp_path):
    state_file = tmp_path / "state"
    state_file.write_text("1000", encoding="utf-8")

    assert notifier.should_send_alert(state_file, now=1599.999) is False


def test_alert_at_exact_cooldown_boundary_is_allowed(tmp_path):
    state_file = tmp_path / "state"
    state_file.write_text("1000", encoding="utf-8")

    assert notifier.should_send_alert(state_file, now=1600) is True


def test_future_state_timestamp_within_cooldown_suppresses_alert(tmp_path):
    state_file = tmp_path / "state"
    state_file.write_text("1600", encoding="utf-8")

    assert notifier.should_send_alert(state_file, now=1000) is False


def test_future_state_timestamp_beyond_cooldown_is_treated_as_corrupt(tmp_path):
    state_file = tmp_path / "state"
    state_file.write_text("1600.001", encoding="utf-8")

    assert notifier.should_send_alert(state_file, now=1000) is True


def test_state_read_io_error_is_reported_as_unavailable(tmp_path, monkeypatch):
    state_file = tmp_path / "state-as-directory"
    state_file.mkdir()
    logger = Mock()
    monkeypatch.setattr(notifier, "logger", logger)

    state = notifier.inspect_alert_state(state_file, now=1000)

    assert state is notifier.AlertState.UNAVAILABLE
    logger.exception.assert_called_once()


def test_record_alert_creates_parent_and_replaces_state_without_temp_files(tmp_path):
    state_file = tmp_path / "nested" / "last-alert"

    notifier.record_alert(state_file, now=1234.5)

    assert state_file.read_text(encoding="utf-8") == "1234.5"
    assert list(state_file.parent.iterdir()) == [state_file]


def test_build_alert_message_contains_all_diagnostics_and_restart_note():
    message = notifier.build_alert_message(
        unit="db-driven-trading.service",
        result="exit-code",
        exit_code="exited",
        exit_status="1",
        hostname="trade-host-01",
        timestamp="2026-07-20 12:34:56 +08:00",
    )

    for value in (
        "db-driven-trading.service",
        "exit-code",
        "exited",
        "1",
        "trade-host-01",
        "2026-07-20 12:34:56 +08:00",
    ):
        assert value in message
    assert "systemd" in message
    assert "重启" in message


@pytest.mark.parametrize("result", [None, "", "success"])
def test_notify_failure_does_not_send_for_normal_result(tmp_path, result):
    bot = RecordingBot()

    sent = notifier.notify_failure(
        unit="db-driven-trading.service",
        result=result,
        exit_code="exited",
        exit_status="0",
        state_file=tmp_path / "state",
        fallback_state_file=tmp_path / "fallback",
        bot=bot,
        clock=lambda: 1000,
        hostname=lambda: "trade-host",
    )

    assert sent is False
    assert bot.messages == []


@pytest.mark.parametrize("cooldown_seconds", [0, -1, 1.5, "600", True])
def test_notify_failure_rejects_invalid_direct_cooldown(
    tmp_path, monkeypatch, cooldown_seconds
):
    state_file = tmp_path / "state"
    fallback_state_file = tmp_path / "fallback"
    bot = RecordingBot()
    logger = Mock()
    monkeypatch.setattr(notifier, "logger", logger)

    sent = notifier.notify_failure(
        unit="db-driven-trading.service",
        result="exit-code",
        exit_code="exited",
        exit_status="1",
        state_file=state_file,
        fallback_state_file=fallback_state_file,
        cooldown_seconds=cooldown_seconds,
        bot=bot,
        clock=lambda: 1000,
        hostname=lambda: "trade-host",
    )

    assert sent is False
    assert bot.messages == []
    assert state_file.exists() is False
    assert fallback_state_file.exists() is False
    logger.error.assert_called_once_with(
        "告警冷却秒数必须为正整数: %r", cooldown_seconds
    )


def test_abnormal_exit_sends_immediately_and_records_success(tmp_path):
    state_file = tmp_path / "state"
    fallback_state_file = tmp_path / "fallback"
    bot = RecordingBot(result=True)

    sent = notifier.notify_failure(
        unit="db-driven-trading.service",
        result="signal",
        exit_code="killed",
        exit_status="9",
        state_file=state_file,
        fallback_state_file=fallback_state_file,
        bot=bot,
        clock=lambda: 1000,
        hostname=lambda: "trade-host",
    )

    assert sent is True
    assert len(bot.messages) == 1
    assert "trade-host" in bot.messages[0]
    assert state_file.read_text(encoding="utf-8") == "1000"
    assert fallback_state_file.read_text(encoding="utf-8") == "1000"


def test_cooldown_suppresses_repeat_abnormal_exit(tmp_path):
    state_file = tmp_path / "state"
    state_file.write_text("1000", encoding="utf-8")
    bot = RecordingBot()

    sent = notifier.notify_failure(
        unit="db-driven-trading.service",
        result="exit-code",
        exit_code="exited",
        exit_status="1",
        state_file=state_file,
        fallback_state_file=tmp_path / "fallback",
        cooldown_seconds=600,
        bot=bot,
        clock=lambda: 1599,
        hostname=lambda: "trade-host",
    )

    assert sent is False
    assert bot.messages == []
    assert state_file.read_text(encoding="utf-8") == "1000"


def test_failed_send_does_not_record_cooldown(tmp_path):
    state_file = tmp_path / "state"
    fallback_state_file = tmp_path / "fallback"
    bot = RecordingBot(result=False)

    sent = notifier.notify_failure(
        unit="db-driven-trading.service",
        result="timeout",
        exit_code="timeout",
        exit_status="1",
        state_file=state_file,
        fallback_state_file=fallback_state_file,
        bot=bot,
        clock=lambda: 1000,
        hostname=lambda: "trade-host",
    )

    assert sent is False
    assert len(bot.messages) == 1
    assert state_file.exists() is False
    assert fallback_state_file.exists() is False


def test_bot_exception_is_logged_and_does_not_raise_or_record(tmp_path, monkeypatch):
    state_file = tmp_path / "state"
    fallback_state_file = tmp_path / "fallback"
    bot = RecordingBot(error=RuntimeError("network down"))
    logger = Mock()
    monkeypatch.setattr(notifier, "logger", logger)

    sent = notifier.notify_failure(
        unit="db-driven-trading.service",
        result="watchdog",
        exit_code="killed",
        exit_status="6",
        state_file=state_file,
        fallback_state_file=fallback_state_file,
        bot=bot,
        clock=lambda: 1000,
        hostname=lambda: "trade-host",
    )

    assert sent is False
    assert state_file.exists() is False
    assert fallback_state_file.exists() is False
    logger.exception.assert_called_once()


def test_fallback_cooldown_suppresses_when_primary_state_is_missing(tmp_path):
    fallback_state_file = tmp_path / "fallback"
    fallback_state_file.write_text("1000", encoding="utf-8")
    bot = RecordingBot()

    sent = notifier.notify_failure(
        unit="db-driven-trading.service",
        result="exit-code",
        exit_code="exited",
        exit_status="1",
        state_file=tmp_path / "missing-primary",
        fallback_state_file=fallback_state_file,
        bot=bot,
        clock=lambda: 1200,
        hostname=lambda: "trade-host",
    )

    assert sent is False
    assert bot.messages == []


def test_primary_write_failure_uses_fallback_to_suppress_repeat(
    tmp_path, monkeypatch
):
    primary_state_file = tmp_path / "primary"
    fallback_state_file = tmp_path / "fallback"
    real_record_alert = notifier.record_alert

    def record_with_primary_failure(state_file, now):
        if state_file == primary_state_file:
            raise PermissionError("primary is read-only")
        real_record_alert(state_file, now)

    monkeypatch.setattr(notifier, "record_alert", record_with_primary_failure)
    monkeypatch.setattr(notifier, "logger", Mock())
    first_bot = RecordingBot()

    first_sent = notifier.notify_failure(
        unit="db-driven-trading.service",
        result="signal",
        exit_code="killed",
        exit_status="9",
        state_file=primary_state_file,
        fallback_state_file=fallback_state_file,
        bot=first_bot,
        clock=lambda: 1000,
        hostname=lambda: "trade-host",
    )

    second_bot = RecordingBot()
    second_sent = notifier.notify_failure(
        unit="db-driven-trading.service",
        result="signal",
        exit_code="killed",
        exit_status="9",
        state_file=primary_state_file,
        fallback_state_file=fallback_state_file,
        bot=second_bot,
        clock=lambda: 1100,
        hostname=lambda: "trade-host",
    )

    assert first_sent is True
    assert len(first_bot.messages) == 1
    assert primary_state_file.exists() is False
    assert fallback_state_file.read_text(encoding="utf-8") == "1000"
    assert second_sent is False
    assert second_bot.messages == []


def test_primary_unavailable_uses_allowed_fallback_and_sends(
    tmp_path, monkeypatch
):
    primary_state_file = tmp_path / "primary-as-directory"
    primary_state_file.mkdir()
    fallback_state_file = tmp_path / "fallback"
    bot = RecordingBot()
    logger = Mock()
    monkeypatch.setattr(notifier, "logger", logger)

    sent = notifier.notify_failure(
        unit="db-driven-trading.service",
        result="resources",
        exit_code="exited",
        exit_status="1",
        state_file=primary_state_file,
        fallback_state_file=fallback_state_file,
        bot=bot,
        clock=lambda: 1000,
        hostname=lambda: "trade-host",
    )

    assert sent is True
    assert len(bot.messages) == 1
    assert fallback_state_file.read_text(encoding="utf-8") == "1000"
    assert logger.exception.call_count == 2


def test_primary_unavailable_obeys_fallback_cooldown(tmp_path, monkeypatch):
    primary_state_file = tmp_path / "primary-as-directory"
    primary_state_file.mkdir()
    fallback_state_file = tmp_path / "fallback"
    fallback_state_file.write_text("1000", encoding="utf-8")
    bot = RecordingBot()
    logger = Mock()
    monkeypatch.setattr(notifier, "logger", logger)

    sent = notifier.notify_failure(
        unit="db-driven-trading.service",
        result="resources",
        exit_code="exited",
        exit_status="1",
        state_file=primary_state_file,
        fallback_state_file=fallback_state_file,
        bot=bot,
        clock=lambda: 1200,
        hostname=lambda: "trade-host",
    )

    assert sent is False
    assert bot.messages == []
    logger.warning.assert_called_once_with(
        "备用异常退出告警处于冷却期，跳过发送: unit=%s result=%s",
        "db-driven-trading.service",
        "resources",
    )


def test_both_primary_and_fallback_unavailable_fail_closed(tmp_path, monkeypatch):
    primary_state_file = tmp_path / "primary-as-directory"
    primary_state_file.mkdir()
    fallback_state_file = tmp_path / "fallback-as-directory"
    fallback_state_file.mkdir()
    bot = RecordingBot()
    logger = Mock()
    monkeypatch.setattr(notifier, "logger", logger)

    sent = notifier.notify_failure(
        unit="db-driven-trading.service",
        result="resources",
        exit_code="exited",
        exit_status="1",
        state_file=primary_state_file,
        fallback_state_file=fallback_state_file,
        bot=bot,
        clock=lambda: 1000,
        hostname=lambda: "trade-host",
    )

    assert sent is False
    assert bot.messages == []
    assert logger.exception.call_count == 2
    logger.error.assert_called_once_with(
        "主告警和备用告警状态均不可用，停止发送以避免重复告警"
    )


def test_default_fallback_prefers_writable_run_user_directory(tmp_path):
    uid = os.getuid()
    runtime_root = tmp_path / "run" / "user"
    runtime_directory = runtime_root / str(uid)
    runtime_directory.mkdir(parents=True)

    first = notifier.resolve_fallback_state_file(
        "db-driven-trading.service",
        uid=uid,
        runtime_root=runtime_root,
        temp_root=tmp_path / "tmp",
    )
    second = notifier.resolve_fallback_state_file(
        "db-driven-trading.service",
        uid=uid,
        runtime_root=runtime_root,
        temp_root=tmp_path / "tmp",
    )

    assert first == second
    assert first.parent == runtime_directory


def test_default_fallback_uses_secure_per_uid_temp_directory(tmp_path):
    uid = os.getuid()
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()

    state_file = notifier.resolve_fallback_state_file(
        "db-driven-trading.service",
        uid=uid,
        runtime_root=tmp_path / "missing-run-user",
        temp_root=temp_root,
    )

    assert state_file.parent.parent == temp_root
    assert str(uid) in state_file.parent.name
    assert stat.S_IMODE(state_file.parent.stat().st_mode) == 0o700


def test_main_parses_arguments_instantiates_bot_and_returns_zero(
    tmp_path, monkeypatch
):
    bot = Mock()
    bot_factory = Mock(return_value=bot)
    notify = Mock(return_value=True)
    state_file = tmp_path / "state"
    monkeypatch.setattr(notifier, "_create_feishu_bot", bot_factory)
    monkeypatch.setattr(notifier, "notify_failure", notify)

    exit_code = notifier.main(
        [
            "--unit",
            "db-driven-trading.service",
            "--result",
            "exit-code",
            "--exit-code",
            "exited",
            "--exit-status",
            "1",
            "--state-file",
            str(state_file),
            "--cooldown-seconds",
            "300",
        ]
    )

    assert exit_code == 0
    bot_factory.assert_called_once_with()
    notify.assert_called_once_with(
        unit="db-driven-trading.service",
        result="exit-code",
        exit_code="exited",
        exit_status="1",
        state_file=state_file,
        cooldown_seconds=300,
        bot=bot,
    )


@pytest.mark.parametrize("value", ["0", "-1"])
def test_parse_args_rejects_non_positive_cooldown(tmp_path, value):
    with pytest.raises(SystemExit):
        notifier.parse_args(
            [
                "--unit",
                "db-driven-trading.service",
                "--result",
                "exit-code",
                "--exit-code",
                "exited",
                "--exit-status",
                "1",
                "--state-file",
                str(tmp_path / "state"),
                "--cooldown-seconds",
                value,
            ]
        )


def test_main_catches_unexpected_notifier_exception_and_returns_zero(monkeypatch):
    monkeypatch.setattr(
        notifier,
        "_create_feishu_bot",
        Mock(side_effect=RuntimeError("boom")),
    )
    logger = Mock()
    monkeypatch.setattr(notifier, "logger", logger)

    exit_code = notifier.main(
        [
            "--unit",
            "db-driven-trading.service",
            "--result",
            "signal",
            "--exit-code",
            "killed",
            "--exit-status",
            "9",
            "--state-file",
            "/tmp/db-trading-alert-test",
        ]
    )

    assert exit_code == 0
    logger.exception.assert_called_once()


def test_script_runs_by_absolute_path_outside_project(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--cooldown-seconds" in result.stdout


def test_script_contains_no_credentials_or_webhook_values():
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "BINANCE_LIVE_API_KEY" not in source
    assert "BINANCE_LIVE_API_SECRET" not in source
    assert "FEISHU_WEBHOOK=" not in source
