#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config_hot_reload import ConfigHotReloader
from signal_module import time_rolling_mean


def test_hot_reload_updates_existing_dea1d_mean_2_window():
    time_rolling_mean._tracker_instance = time_rolling_mean.TimeRollingMean()
    tracker = time_rolling_mean.get_time_rolling_mean_tracker()

    tracker.update("dea1d_2", pd.Timestamp("2026-07-01 14:17:00"), -2331.68)
    assert tracker.data["dea1d_2"]["window_minutes"] == 60

    reloader = ConfigHotReloader.__new__(ConfigHotReloader)

    reloader._apply_params({"means_dea1d_count_2": 120})

    assert tracker.data["dea1d_2"]["window_minutes"] == 120

