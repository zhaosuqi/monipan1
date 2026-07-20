import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config_hot_reload import ConfigHotReloader
from data import db_driven_trading
from data.db_driven_trading import DBDrivenTrader


def make_trader(*, silent_startup: bool) -> DBDrivenTrader:
    trader = DBDrivenTrader.__new__(DBDrivenTrader)
    trader.silent_startup = silent_startup
    trader.use_testnet = True
    trader.logger = Mock()
    trader.feishu_bot = Mock()
    trader.trade_engine = Mock()
    trader.config_reloader = Mock()
    return trader


def test_parse_args_supports_existing_and_silent_startup_options():
    args = db_driven_trading.parse_args(
        ["--live", "--preload", "250", "--silent-startup"]
    )

    assert args.live is True
    assert args.preload == 250
    assert args.silent_startup is True


def test_parse_args_keeps_existing_defaults():
    args = db_driven_trading.parse_args([])

    assert args.live is False
    assert args.preload == 1000
    assert args.silent_startup is False


def test_constructor_stores_silent_startup(monkeypatch):
    monkeypatch.setattr(DBDrivenTrader, "_get_engine", Mock(return_value=Mock()))
    monkeypatch.setattr(DBDrivenTrader, "_init_exchange", Mock())
    monkeypatch.setattr(db_driven_trading, "SignalCalculator", Mock())
    monkeypatch.setattr(db_driven_trading, "TradeEngine", Mock())
    monkeypatch.setattr(db_driven_trading, "FeishuBot", Mock())
    monkeypatch.setattr(db_driven_trading, "ConfigHotReloader", Mock())
    monkeypatch.setattr(DBDrivenTrader, "_send_startup_notifications", Mock())

    trader = DBDrivenTrader(silent_startup=True)

    assert trader.silent_startup is True


def test_normal_startup_sends_system_and_trade_history_notifications():
    trader = make_trader(silent_startup=False)

    trader._send_startup_notifications()

    trader.feishu_bot.send_system_startup_notification.assert_called_once()
    trader.trade_engine._send_trade_history_report.assert_called_once_with()


def test_silent_startup_skips_system_and_trade_history_notifications():
    trader = make_trader(silent_startup=True)

    trader._send_startup_notifications()

    trader.feishu_bot.send_system_startup_notification.assert_not_called()
    trader.trade_engine._send_trade_history_report.assert_not_called()


@pytest.mark.parametrize(
    ("silent_startup", "notify_feishu"),
    [(False, True), (True, False)],
)
def test_startup_parameter_report_controls_only_feishu_copy(
    silent_startup, notify_feishu
):
    trader = make_trader(silent_startup=silent_startup)

    trader._report_startup_params()

    trader.config_reloader.report_all_params.assert_called_once_with(
        notify_feishu=notify_feishu
    )


def test_report_all_params_logs_but_does_not_send_when_feishu_disabled():
    reloader = ConfigHotReloader.__new__(ConfigHotReloader)
    reloader.logger = Mock()
    reloader.feishu_bot = Mock()
    reloader.last_params = {"means_dea1d_count_2": 120}

    reloader.report_all_params(notify_feishu=False)

    reloader.logger.info.assert_any_call("  means_dea1d_count_2 = 120")
    reloader.feishu_bot.send_message.assert_not_called()


def test_report_all_params_sends_feishu_by_default():
    reloader = ConfigHotReloader.__new__(ConfigHotReloader)
    reloader.logger = Mock()
    reloader.feishu_bot = Mock()
    reloader.last_params = {"means_dea1d_count_2": 120}

    reloader.report_all_params()

    reloader.feishu_bot.send_message.assert_called_once()


def test_process_new_data_reports_startup_params_only_once():
    trader = make_trader(silent_startup=True)
    trader._params_reported = False
    trader._report_startup_params = Mock()
    trader.price_history = []
    trader.max_price_history = 100
    trader.prev_row = None
    trader.rowList = []
    trader.signal_calculator = Mock()
    trader.signal_calculator.calculate_open_signal.return_value = None
    trader.trade_engine.process_tick = Mock()
    row = {
        "open_time": "2026-07-20 12:00:00",
        "close": 60000.0,
    }

    trader.process_new_data(row)
    trader.process_new_data(row)

    trader._report_startup_params.assert_called_once_with()
    assert trader._params_reported is True


def test_main_passes_silent_startup_to_trader_and_runs(monkeypatch):
    trader = Mock()
    trader_factory = Mock(return_value=trader)
    monkeypatch.setattr(db_driven_trading, "DBDrivenTrader", trader_factory)

    db_driven_trading.main(["--live", "--preload", "250", "--silent-startup"])

    trader_factory.assert_called_once_with(
        use_testnet=False,
        silent_startup=True,
    )
    trader.run.assert_called_once_with()
    assert db_driven_trading.PRELOAD_COUNT == 250


def test_main_logs_traceback_and_reraises_unhandled_run_exception(monkeypatch):
    error = RuntimeError("boom")
    trader = SimpleNamespace(run=Mock(side_effect=error))
    monkeypatch.setattr(db_driven_trading, "DBDrivenTrader", Mock(return_value=trader))
    logger = Mock()
    monkeypatch.setattr(db_driven_trading, "logger", logger)

    with pytest.raises(RuntimeError, match="boom"):
        db_driven_trading.main([])

    logger.exception.assert_called_once_with("交易系统异常退出")
