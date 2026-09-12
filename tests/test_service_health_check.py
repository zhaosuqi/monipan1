import sqlite3
import subprocess
import sys
import textwrap
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "service_health_check.py"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import service_health_check as health


UTC = timezone.utc
BASE = datetime(2026, 7, 21, 4, 0, 0, tzinfo=UTC)
BASE_TS = BASE.timestamp()


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


def write_db(db_path, kline_open_time, indicator_open_time=None):
    if indicator_open_time is None:
        indicator_open_time = kline_open_time
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("DROP TABLE IF EXISTS klines_1m")
        conn.execute("DROP TABLE IF EXISTS klines_1m_macd_smooth_ma")
        conn.execute("CREATE TABLE klines_1m (open_time TEXT)")
        conn.execute("CREATE TABLE klines_1m_macd_smooth_ma (open_time TEXT)")
        if kline_open_time is not None:
            conn.execute(
                "INSERT INTO klines_1m VALUES (?)", (kline_open_time,)
            )
        if indicator_open_time is not None:
            conn.execute(
                "INSERT INTO klines_1m_macd_smooth_ma VALUES (?)",
                (indicator_open_time,),
            )


def run_check(tmp_path, bot, now, db_path, monkeypatch, **overrides):
    monkeypatch.setattr(health, "check_services", lambda **kwargs: {})
    params = dict(
        state_dir=tmp_path / "state",
        db_path=db_path,
        web_url="http://127.0.0.1:8076/",
        bot=bot,
        clock=lambda: now,
        hostname=lambda: "test-host",
        http_getter=lambda url: 200,
    )
    params.update(overrides)
    return health.run_health_checks(**params)


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
        spec = importlib.util.spec_from_file_location("health_probe", {str(SCRIPT_PATH)!r})
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


# ---------------- 数据新鲜度 ----------------


def test_fresh_data_passes(tmp_path):
    db_path = tmp_path / "klines.db"
    write_db(db_path, "2026-07-21T03:59:00")

    assert health.check_table_freshness(db_path, "klines_1m", 180, BASE) is None


def test_stale_data_fails(tmp_path):
    db_path = tmp_path / "klines.db"
    write_db(db_path, "2026-07-21T03:00:00")

    detail = health.check_table_freshness(db_path, "klines_1m", 180, BASE)

    assert detail is not None
    assert "klines_1m" in detail
    assert "3600" in detail


def test_empty_table_fails(tmp_path):
    db_path = tmp_path / "klines.db"
    write_db(db_path, None, None)

    detail = health.check_table_freshness(db_path, "klines_1m", 180, BASE)

    assert detail is not None
    assert "为空" in detail


def test_invalid_time_format_fails(tmp_path):
    db_path = tmp_path / "klines.db"
    write_db(db_path, "not-a-time")

    detail = health.check_table_freshness(db_path, "klines_1m", 180, BASE)

    assert detail is not None
    assert "无法解析" in detail


def test_missing_db_file_fails(tmp_path):
    detail = health.check_table_freshness(
        tmp_path / "missing.db", "klines_1m", 180, BASE
    )

    assert detail is not None
    assert "不存在" in detail


@pytest.mark.parametrize(
    "open_time", ["2026-07-21T03:59:00", "2026-07-21 03:59:00"]
)
def test_both_open_time_formats_parse(tmp_path, open_time):
    db_path = tmp_path / "klines.db"
    write_db(db_path, open_time)

    assert health.check_table_freshness(db_path, "klines_1m", 180, BASE) is None


# ---------------- 服务存活 ----------------


def test_missing_systemctl_skips_service_check(monkeypatch):
    monkeypatch.setattr(health.shutil, "which", lambda name: None)
    logger = Mock()
    monkeypatch.setattr(health, "logger", logger)

    assert health.check_services() == {}
    logger.info.assert_called_once()


def test_active_services_pass(monkeypatch):
    monkeypatch.setattr(health.shutil, "which", lambda name: "/usr/bin/systemctl")
    runner = lambda unit: subprocess.CompletedProcess(
        [], 0, stdout="active\n", stderr=""
    )

    results = health.check_services(systemctl_runner=runner)

    assert len(results) == len(health.MONITORED_UNITS)
    assert all(detail is None for detail in results.values())


@pytest.mark.parametrize("status", ["inactive", "activating", "failed"])
def test_non_active_service_is_failure(monkeypatch, status):
    monkeypatch.setattr(health.shutil, "which", lambda name: "/usr/bin/systemctl")
    runner = lambda unit: subprocess.CompletedProcess(
        [], 3, stdout=f"{status}\n", stderr=""
    )

    results = health.check_services(systemctl_runner=runner)

    assert len(results) == len(health.MONITORED_UNITS)
    for unit, detail in zip(health.MONITORED_UNITS, results.values()):
        assert detail is not None
        assert unit in detail
        assert status in detail


# ---------------- Web 可达 ----------------


@pytest.mark.parametrize("status", [200, 302])
def test_successful_http_response_means_alive(status):
    assert health.check_web("http://x/", http_getter=lambda url: status) is None


def test_http_error_response_means_alive():
    def getter(url):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    assert health.check_web("http://x/", http_getter=getter) is None


def test_connection_refused_is_failure():
    def getter(url):
        raise urllib.error.URLError("Connection refused")

    detail = health.check_web("http://127.0.0.1:8076/", http_getter=getter)

    assert detail is not None
    assert "不可达" in detail


# ---------------- 冷却与告警 ----------------


def test_abnormal_items_send_one_merged_alert(tmp_path, monkeypatch):
    db_path = tmp_path / "klines.db"
    write_db(db_path, "2026-07-21T03:00:00")
    bot = RecordingBot()

    summary = run_check(tmp_path, bot, BASE_TS, db_path, monkeypatch)

    assert summary["alert_sent"] is True
    assert len(bot.messages) == 1
    message = bot.messages[0]
    assert "test-host" in message
    assert "klines_1m" in message
    assert "klines_1m_macd_smooth_ma" in message


def test_alert_inside_cooldown_is_suppressed(tmp_path, monkeypatch):
    db_path = tmp_path / "klines.db"
    write_db(db_path, "2026-07-21T03:00:00")
    bot = RecordingBot()

    run_check(tmp_path, bot, BASE_TS, db_path, monkeypatch)
    summary = run_check(tmp_path, bot, BASE_TS + 599.999, db_path, monkeypatch)

    assert summary["alert_sent"] is False
    assert len(bot.messages) == 1


def test_alert_at_exact_cooldown_boundary_sends_again(tmp_path, monkeypatch):
    db_path = tmp_path / "klines.db"
    write_db(db_path, "2026-07-21T03:00:00")
    bot = RecordingBot()

    run_check(tmp_path, bot, BASE_TS, db_path, monkeypatch)
    summary = run_check(tmp_path, bot, BASE_TS + 600, db_path, monkeypatch)

    assert summary["alert_sent"] is True
    assert len(bot.messages) == 2


def test_alert_after_cooldown_sends_again(tmp_path, monkeypatch):
    db_path = tmp_path / "klines.db"
    write_db(db_path, "2026-07-21T03:00:00")
    bot = RecordingBot()

    run_check(tmp_path, bot, BASE_TS, db_path, monkeypatch)
    run_check(tmp_path, bot, BASE_TS + 700, db_path, monkeypatch)

    assert len(bot.messages) == 2


def test_failed_send_does_not_record_cooldown(tmp_path, monkeypatch):
    db_path = tmp_path / "klines.db"
    write_db(db_path, "2026-07-21T03:00:00")
    bot = RecordingBot(result=False)

    first = run_check(tmp_path, bot, BASE_TS, db_path, monkeypatch)

    assert first["alert_sent"] is False
    assert list((tmp_path / "state").glob("*.state")) == []

    bot.result = True
    second = run_check(tmp_path, bot, BASE_TS + 1, db_path, monkeypatch)

    assert second["alert_sent"] is True
    assert len(bot.messages) == 2


def test_healthy_run_without_prior_alert_is_silent(tmp_path, monkeypatch):
    db_path = tmp_path / "klines.db"
    write_db(db_path, "2026-07-21T03:59:00")
    bot = RecordingBot()

    summary = run_check(tmp_path, bot, BASE_TS, db_path, monkeypatch)

    assert summary["alert_sent"] is False
    assert summary["recoveries_sent"] == []
    assert bot.messages == []


# ---------------- 恢复通知 ----------------


def test_recovery_sends_one_notification_and_clears_state(tmp_path, monkeypatch):
    db_path = tmp_path / "klines.db"
    write_db(db_path, "2026-07-21T03:00:00")
    bot = RecordingBot()
    run_check(tmp_path, bot, BASE_TS, db_path, monkeypatch)
    assert len(bot.messages) == 1

    write_db(db_path, "2026-07-21T03:59:00")
    summary = run_check(tmp_path, bot, BASE_TS + 60, db_path, monkeypatch)

    assert set(summary["recoveries_sent"]) == {
        health.KLINE_ITEM,
        health.INDICATOR_ITEM,
    }
    assert len(bot.messages) == 3
    assert "已恢复" in bot.messages[1]
    assert "已恢复" in bot.messages[2]
    assert list((tmp_path / "state").glob("*.state")) == []

    followup = run_check(tmp_path, bot, BASE_TS + 120, db_path, monkeypatch)
    assert followup["recoveries_sent"] == []
    assert len(bot.messages) == 3


def test_alert_works_again_after_recovery(tmp_path, monkeypatch):
    db_path = tmp_path / "klines.db"
    write_db(db_path, "2026-07-21T03:00:00")
    bot = RecordingBot()
    run_check(tmp_path, bot, BASE_TS, db_path, monkeypatch)

    write_db(db_path, "2026-07-21T03:59:00")
    run_check(tmp_path, bot, BASE_TS + 60, db_path, monkeypatch)

    write_db(db_path, "2026-07-21T03:00:00")
    summary = run_check(tmp_path, bot, BASE_TS + 120, db_path, monkeypatch)

    assert summary["alert_sent"] is True
    assert len(bot.messages) == 4


# ---------------- main ----------------


def test_main_catches_unexpected_exception_and_returns_zero(monkeypatch):
    monkeypatch.setattr(
        health,
        "run_health_checks",
        Mock(side_effect=RuntimeError("boom")),
    )
    logger = Mock()
    monkeypatch.setattr(health, "logger", logger)

    assert health.main() == 0
    logger.exception.assert_called_once()


def test_script_contains_no_credentials_or_webhook_values():
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "BINANCE_LIVE_API_KEY" not in source
    assert "BINANCE_LIVE_API_SECRET" not in source
    assert "FEISHU_WEBHOOK=" not in source
