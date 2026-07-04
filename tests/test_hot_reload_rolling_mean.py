#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config_hot_reload import ConfigHotReloader
from core.config import config
from signal_module import time_rolling_mean
from signal_module.signal_calculator import SignalCalculator


def test_hot_reload_updates_existing_dea1d_mean_2_window():
    time_rolling_mean._tracker_instance = time_rolling_mean.TimeRollingMean()
    tracker = time_rolling_mean.get_time_rolling_mean_tracker()

    tracker.update("dea1d_2", pd.Timestamp("2026-07-01 14:17:00"), -2331.68)
    assert tracker.data["dea1d_2"]["window_minutes"] == 60

    reloader = ConfigHotReloader.__new__(ConfigHotReloader)

    reloader._apply_params({"means_dea1d_count_2": 120})

    assert tracker.data["dea1d_2"]["window_minutes"] == 120


def test_signal_calculation_resyncs_stale_dea1d_mean_2_window(monkeypatch):
    time_rolling_mean._tracker_instance = time_rolling_mean.TimeRollingMean()
    tracker = time_rolling_mean.get_time_rolling_mean_tracker()

    monkeypatch.setattr(config, "MEANS_DEA1D_COUNT_2", 120)
    calc = SignalCalculator()

    tracker.data["dea1d_2"]["window_minutes"] = 60
    row = {
        "open_time": "2026-07-01 14:17:00",
        "close_time": "2026-07-01 14:17:59",
        "close": 59969.7,
        "macd15m": 0.0,
        "dif15m": 0.0,
        "dea15m": 0.0,
        "macd1h": 0.0,
        "dif1h": 0.0,
        "dea1h": 0.0,
        "macd4h": 0.0,
        "dif4h": 0.0,
        "dea4h": 0.0,
        "macd1d": 0.0,
        "dif1d": 0.0,
        "dea1d": -2331.68,
        "j_15": 0.0,
        "j_1h": 0.0,
        "j_4h": 0.0,
    }

    calc.calculate_open_signal(row)

    assert tracker.data["dea1d_2"]["window_minutes"] == 120
