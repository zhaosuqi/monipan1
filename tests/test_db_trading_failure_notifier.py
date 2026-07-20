import subprocess
import sys
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


def test_future_state_timestamp_suppresses_alert_for_safety(tmp_path):
    state_file = tmp_path / "state"
    state_file.write_text("2000", encoding="utf-8")

    assert notifier.should_send_alert(state_file, now=1000) is False


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
        bot=bot,
        clock=lambda: 1000,
        hostname=lambda: "trade-host",
    )

    assert sent is False
    assert bot.messages == []


def test_abnormal_exit_sends_immediately_and_records_success(tmp_path):
    state_file = tmp_path / "state"
    bot = RecordingBot(result=True)

    sent = notifier.notify_failure(
        unit="db-driven-trading.service",
        result="signal",
        exit_code="killed",
        exit_status="9",
        state_file=state_file,
        bot=bot,
        clock=lambda: 1000,
        hostname=lambda: "trade-host",
    )

    assert sent is True
    assert len(bot.messages) == 1
    assert "trade-host" in bot.messages[0]
    assert state_file.read_text(encoding="utf-8") == "1000"


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
    bot = RecordingBot(result=False)

    sent = notifier.notify_failure(
        unit="db-driven-trading.service",
        result="timeout",
        exit_code="timeout",
        exit_status="1",
        state_file=state_file,
        bot=bot,
        clock=lambda: 1000,
        hostname=lambda: "trade-host",
    )

    assert sent is False
    assert len(bot.messages) == 1
    assert state_file.exists() is False


def test_bot_exception_is_logged_and_does_not_raise_or_record(tmp_path, monkeypatch):
    state_file = tmp_path / "state"
    bot = RecordingBot(error=RuntimeError("network down"))
    logger = Mock()
    monkeypatch.setattr(notifier, "logger", logger)

    sent = notifier.notify_failure(
        unit="db-driven-trading.service",
        result="watchdog",
        exit_code="killed",
        exit_status="6",
        state_file=state_file,
        bot=bot,
        clock=lambda: 1000,
        hostname=lambda: "trade-host",
    )

    assert sent is False
    assert state_file.exists() is False
    logger.exception.assert_called_once()


def test_main_parses_arguments_instantiates_bot_and_returns_zero(
    tmp_path, monkeypatch
):
    bot = Mock()
    bot_factory = Mock(return_value=bot)
    notify = Mock(return_value=True)
    state_file = tmp_path / "state"
    monkeypatch.setattr(notifier, "FeishuBot", bot_factory)
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


def test_main_catches_unexpected_notifier_exception_and_returns_zero(monkeypatch):
    monkeypatch.setattr(notifier, "FeishuBot", Mock(side_effect=RuntimeError("boom")))
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
