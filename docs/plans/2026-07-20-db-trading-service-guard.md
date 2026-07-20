# DB Trading Service Guard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add startup-only Feishu suppression, abnormal-exit alerting, and systemd supervision for the live DB-driven trading process.

**Architecture:** Keep trading notifications enabled and apply silence only at the three startup call sites. Let systemd own restart policy and invoke a small Python notifier after process termination; the notifier classifies abnormal exits and persists a cooldown timestamp. Generate the production unit from a repository template so paths, user, and Python interpreter are explicit and secrets remain in `.env`.

**Tech Stack:** Python 3, pytest, Bash, systemd, existing `FeishuBot` and logging modules.

---

### Task 1: Add startup-only silent mode

**Files:**
- Create: `tests/test_db_driven_trading_startup.py`
- Modify: `data/db_driven_trading.py:65-520`
- Modify: `core/config_hot_reload.py:298-334`

**Step 1: Write failing CLI and parameter-report tests**

Add tests that import the trading module and verify the desired public behavior:

```python
from data import db_driven_trading
from core.config_hot_reload import ConfigHotReloader


class FakeBot:
    def __init__(self):
        self.messages = []

    def send_message(self, message):
        self.messages.append(message)
        return True


def test_parse_args_accepts_silent_startup():
    args = db_driven_trading.parse_args(["--live", "--silent-startup"])
    assert args.live is True
    assert args.silent_startup is True


def test_full_parameter_report_can_skip_feishu(caplog):
    reloader = ConfigHotReloader.__new__(ConfigHotReloader)
    reloader.last_params = {"means_dea1d_count_2": 120}
    reloader.feishu_bot = FakeBot()
    reloader.logger = db_driven_trading.logger

    reloader.report_all_params(notify_feishu=False)

    assert reloader.feishu_bot.messages == []
    assert "means_dea1d_count_2 = 120" in caplog.text
```

**Step 2: Run the tests and verify RED**

Run:

```bash
pytest -q tests/test_db_driven_trading_startup.py::test_parse_args_accepts_silent_startup \
  tests/test_db_driven_trading_startup.py::test_full_parameter_report_can_skip_feishu
```

Expected: FAIL because `parse_args` and `notify_feishu` do not exist.

**Step 3: Add startup-report behavior tests**

Construct `DBDrivenTrader` with `__new__` so the test does not connect to an exchange:

```python
from unittest.mock import Mock


def make_trader(silent_startup):
    trader = db_driven_trading.DBDrivenTrader.__new__(
        db_driven_trading.DBDrivenTrader
    )
    trader.logger = Mock()
    trader.silent_startup = silent_startup
    trader.use_testnet = False
    trader.feishu_bot = Mock()
    trader.trade_engine = Mock()
    trader.config_reloader = Mock()
    return trader


def test_silent_startup_skips_startup_feishu_reports():
    trader = make_trader(True)
    trader._send_startup_notifications()
    trader._report_startup_params()
    trader.feishu_bot.send_system_startup_notification.assert_not_called()
    trader.trade_engine._send_trade_history_report.assert_not_called()
    trader.config_reloader.report_all_params.assert_called_once_with(
        notify_feishu=False
    )


def test_normal_startup_keeps_startup_feishu_reports():
    trader = make_trader(False)
    trader._send_startup_notifications()
    trader._report_startup_params()
    trader.feishu_bot.send_system_startup_notification.assert_called_once()
    trader.trade_engine._send_trade_history_report.assert_called_once()
    trader.config_reloader.report_all_params.assert_called_once_with(
        notify_feishu=True
    )
```

**Step 4: Run the startup tests and verify RED**

Run:

```bash
pytest -q tests/test_db_driven_trading_startup.py
```

Expected: FAIL because the startup helpers and silent state do not exist.

**Step 5: Implement the minimal silent-startup behavior**

In `ConfigHotReloader`, change the method signature and Feishu guard:

```python
def report_all_params(self, notify_feishu: bool = True):
    # Existing log output remains unchanged.
    if not notify_feishu or not self.feishu_bot:
        return
    # Existing Feishu send block remains unchanged.
```

In `DBDrivenTrader.__init__`, accept and store the option:

```python
def __init__(self, use_testnet: bool = True, silent_startup: bool = False):
    self.silent_startup = silent_startup
```

Extract the existing notification calls into `_send_startup_notifications()` and
skip both startup-only sends when silent. Extract the first parameter report call:

```python
def _report_startup_params(self):
    self.config_reloader.report_all_params(
        notify_feishu=not self.silent_startup
    )
```

Keep `_params_reported` as the one-shot guard in `process_new_data()` and call the
new helper from there.

Extract argument parsing and pass the value through:

```python
def parse_args(argv=None):
    parser = argparse.ArgumentParser(...)
    # Existing --live and --preload options.
    parser.add_argument(
        "--silent-startup",
        action="store_true",
        help="启动时不发送飞书消息，正常交易通知不受影响",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    trader = DBDrivenTrader(
        use_testnet=not args.live,
        silent_startup=args.silent_startup,
    )
    try:
        trader.run()
    except Exception:
        logger.exception("交易系统异常退出")
        raise
```

**Step 6: Run focused and existing hot-reload tests**

Run:

```bash
pytest -q tests/test_db_driven_trading_startup.py \
  tests/test_hot_reload_rolling_mean.py
```

Expected: PASS.

**Step 7: Commit**

```bash
git add data/db_driven_trading.py core/config_hot_reload.py \
  tests/test_db_driven_trading_startup.py
git commit -m "feat: add silent trading service startup"
```

### Task 2: Add abnormal-exit Feishu notifier

**Files:**
- Create: `scripts/notify_db_trading_failure.py`
- Create: `tests/test_db_trading_failure_notifier.py`

**Step 1: Write failing exit-classification tests**

```python
from scripts.notify_db_trading_failure import is_abnormal_exit


def test_successful_exit_is_not_abnormal():
    assert is_abnormal_exit("success") is False


def test_non_success_service_result_is_abnormal():
    assert is_abnormal_exit("exit-code") is True
    assert is_abnormal_exit("signal") is True
    assert is_abnormal_exit("timeout") is True
```

**Step 2: Run classification tests and verify RED**

Run:

```bash
pytest -q tests/test_db_trading_failure_notifier.py
```

Expected: collection ERROR because the notifier module does not exist.

**Step 3: Implement exit classification**

Create the script with a pure helper:

```python
def is_abnormal_exit(service_result: str) -> bool:
    return bool(service_result) and service_result != "success"
```

**Step 4: Run classification tests and verify GREEN**

Run:

```bash
pytest -q tests/test_db_trading_failure_notifier.py
```

Expected: PASS.

**Step 5: Write failing cooldown tests**

```python
def test_first_alert_is_allowed(tmp_path):
    state_file = tmp_path / "last-alert"
    assert should_send_alert(state_file, now=1000, cooldown_seconds=600)


def test_alert_inside_cooldown_is_suppressed(tmp_path):
    state_file = tmp_path / "last-alert"
    state_file.write_text("1000", encoding="utf-8")
    assert not should_send_alert(state_file, now=1599, cooldown_seconds=600)


def test_alert_after_cooldown_is_allowed(tmp_path):
    state_file = tmp_path / "last-alert"
    state_file.write_text("1000", encoding="utf-8")
    assert should_send_alert(state_file, now=1600, cooldown_seconds=600)
```

**Step 6: Run cooldown tests and verify RED**

Expected: FAIL because `should_send_alert` does not exist.

**Step 7: Implement cooldown and alert message composition**

Add helpers that read invalid/missing timestamps as no prior alert and atomically
replace the state file after a successful send:

```python
def should_send_alert(state_file, now, cooldown_seconds=600):
    try:
        last_sent = float(state_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return True
    return now - last_sent >= cooldown_seconds


def record_alert(state_file, now):
    state_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_file.with_suffix(state_file.suffix + ".tmp")
    temporary.write_text(str(now), encoding="utf-8")
    temporary.replace(state_file)
```

Add `build_alert_message()` with unit, host, result, exit code, exit status, and
East-8 timestamp. Add `main(argv=None)` that returns zero for normal exits and
cooldown suppression, sends via `FeishuBot`, and records cooldown only after a
successful send.

**Step 8: Test the main notification flow**

Inject a fake bot into a `notify_failure(args, bot, now)` function and assert:

- Abnormal exit sends exactly one message.
- Successful exit sends nothing.
- Cooldown suppresses the second abnormal exit.
- Failed Feishu send does not record cooldown.

Run:

```bash
pytest -q tests/test_db_trading_failure_notifier.py
```

Expected: PASS.

**Step 9: Commit**

```bash
git add scripts/notify_db_trading_failure.py \
  tests/test_db_trading_failure_notifier.py
git commit -m "feat: alert on trading service failure"
```

### Task 3: Add systemd service and installer

**Files:**
- Create: `deploy/systemd/db-driven-trading.service.in`
- Create: `scripts/install_db_trading_service.sh`
- Create: `tests/test_db_trading_systemd_files.py`

**Step 1: Write failing repository-contract tests**

Read the unit template and installer as text and assert the required safety and
runtime settings:

```python
def test_service_has_restart_and_silent_startup():
    unit = UNIT_TEMPLATE.read_text(encoding="utf-8")
    assert "Restart=always" in unit
    assert "RestartSec=5" in unit
    assert "KillSignal=SIGINT" in unit
    assert "--live --silent-startup" in unit
    assert "ExecStopPost=" in unit
    assert "EnvironmentFile=-@PROJECT_ROOT@/.env" in unit


def test_service_template_contains_no_credentials():
    unit = UNIT_TEMPLATE.read_text(encoding="utf-8")
    assert "BINANCE_LIVE_API_KEY=" not in unit
    assert "BINANCE_LIVE_API_SECRET=" not in unit
```

Also assert the installer runs `systemctl daemon-reload`, `enable`, and `restart`,
and resolves an absolute Python interpreter.

**Step 2: Run repository-contract tests and verify RED**

Run:

```bash
pytest -q tests/test_db_trading_systemd_files.py
```

Expected: FAIL because the unit and installer do not exist.

**Step 3: Add the unit template**

Create:

```ini
[Unit]
Description=DB-driven live trading service
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=@SERVICE_USER@
WorkingDirectory=@PROJECT_ROOT@
EnvironmentFile=-@PROJECT_ROOT@/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=@PYTHON_BIN@ @PROJECT_ROOT@/data/db_driven_trading.py --live --silent-startup
ExecStopPost=@PYTHON_BIN@ @PROJECT_ROOT@/scripts/notify_db_trading_failure.py --unit db-driven-trading.service --result ${SERVICE_RESULT} --exit-code ${EXIT_CODE} --exit-status ${EXIT_STATUS} --state-file @PROJECT_ROOT@/data/.db_trading_failure_alert
Restart=always
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=60
NoNewPrivileges=true
PrivateTmp=true
UMask=0077

[Install]
WantedBy=multi-user.target
```

**Step 4: Add the installer**

The installer must:

1. Require root through `sudo` only for installation and systemctl operations.
2. Infer project root from the script location.
3. Resolve `python3` with `command -v` so a selected virtual environment is retained.
4. Default service user to `SUDO_USER`, then current user, with an optional first argument override.
5. Replace template placeholders into a `mktemp` file.
6. Install `/etc/systemd/system/db-driven-trading.service` with mode `0644`.
7. Run `systemctl daemon-reload`, `enable`, and `restart`.
8. Print `systemctl status` and `journalctl` inspection commands.

Do not source `.env` or print any secret value in the installer.

**Step 5: Run contract and shell syntax tests**

Run:

```bash
pytest -q tests/test_db_trading_systemd_files.py
bash -n scripts/install_db_trading_service.sh
```

Expected: PASS.

On a Linux host with systemd, also run:

```bash
systemd-analyze verify /etc/systemd/system/db-driven-trading.service
```

Expected: no errors.

**Step 6: Commit**

```bash
git add deploy/systemd/db-driven-trading.service.in \
  scripts/install_db_trading_service.sh tests/test_db_trading_systemd_files.py
git commit -m "ops: supervise db trading with systemd"
```

### Task 4: Document operations and complete verification

**Files:**
- Create: `docs/DB_TRADING_SYSTEMD.md`
- Modify: `start_db_trading.sh`

**Step 1: Replace unsafe production-script guidance**

Keep `start_db_trading.sh` useful for foreground testnet use, but add a clear note
that production is managed by systemd. Do not embed or print live credentials.

The operations document must include:

```bash
# Install or update service
bash scripts/install_db_trading_service.sh

# Inspect and control
sudo systemctl status db-driven-trading
sudo systemctl restart db-driven-trading
sudo systemctl stop db-driven-trading
journalctl -u db-driven-trading -n 200 --no-pager
journalctl -u db-driven-trading -f
```

Document required `.env` keys without values, immediate credential rotation, alert
cooldown behavior, start-limit recovery with `systemctl reset-failed`, and a manual
failure drill using a test process or temporary non-secret configuration error.

**Step 2: Run all verification commands**

Run:

```bash
pytest -q
bash -n start_db_trading.sh scripts/install_db_trading_service.sh
git diff --check
rg -n "BINANCE_LIVE_API_(KEY|SECRET)=" \
  start_db_trading.sh scripts deploy docs/DB_TRADING_SYSTEMD.md
```

Expected:

- Full pytest suite passes.
- Shell syntax checks pass.
- `git diff --check` reports no whitespace errors.
- Credential scan finds no hard-coded live key or secret assignments in changed
  operational files.

**Step 3: Review service behavior**

Confirm from the final diff:

- Silent startup affects only startup messages.
- TradeEngine notification construction is untouched.
- Runtime hot-reload change notifications are untouched.
- Manual stop/restart produces `SERVICE_RESULT=success` and no alert.
- Abnormal exit sends once and restarts after five seconds.

**Step 4: Commit**

```bash
git add docs/DB_TRADING_SYSTEMD.md start_db_trading.sh
git commit -m "docs: add trading service operations guide"
```

**Step 5: Production deployment checklist**

On the server:

```bash
git pull
# Put newly rotated credentials only in .env.
bash scripts/install_db_trading_service.sh
sudo systemctl status db-driven-trading
journalctl -u db-driven-trading -n 100 --no-pager
```

Verify that startup creates no Feishu startup/history/parameter message, then perform
one controlled failure drill and confirm one Feishu alert plus automatic restart.
