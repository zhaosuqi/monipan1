# DB Trading Service Guard Design

## Goals

- Add a silent startup mode that suppresses startup-only Feishu messages.
- Keep normal trading notifications and runtime parameter-change notifications enabled.
- Let systemd restart `db_driven_trading` after an unexpected exit.
- Send one immediate Feishu alert for abnormal exits, with a 10-minute cooldown.
- Improve shutdown behavior and preserve useful failure diagnostics.

## Silent Startup

`data/db_driven_trading.py` will accept `--silent-startup` and pass the value to
`DBDrivenTrader`.

When enabled, it suppresses these startup-only messages:

1. System startup notification.
2. Startup trade-history report.
3. The Feishu copy of the first full runtime-parameter report.

The full parameter report remains in the application log. Trading event
notifications and later hot-reload parameter-change notifications are unchanged.

`ConfigHotReloader.report_all_params()` will accept an explicit notification flag
so startup code can suppress only the Feishu copy without disabling the reloader's
normal notifications.

## Process Supervision

The application will run as a systemd service with:

- `--live --silent-startup` arguments.
- Project `.env` loaded through `EnvironmentFile`.
- `Restart=always` and a five-second restart delay.
- A five-minute start-limit window with five attempts.
- `SIGINT` as the stop signal so Python follows its existing graceful shutdown path.
- Journal output for durable exit status and traceback inspection.

An installation script will generate absolute project and Python paths for the
unit, install it, reload systemd, and enable the service. API credentials must not
appear in scripts or unit files.

## Failure Alerting

The main unit will call an independent notifier from `ExecStopPost`. Systemd passes
the service result, exit code, and exit status to it.

The notifier sends an alert only for abnormal termination. A normal exit or a
manual `systemctl stop/restart` does not alert. The alert includes the host name,
unit name, result, exit code, exit status, and timestamp.

A timestamp state file provides a 10-minute cooldown so a crash loop does not flood
Feishu. Notification failures are logged but never interfere with service restart.

## Failure Diagnostics

Unexpected top-level exceptions are logged with their full traceback and then
allowed to produce a non-zero process exit. Systemd remains responsible for restart
policy rather than an internal infinite restart loop.

Operational checks will use:

- `systemctl status db-driven-trading`
- `journalctl -u db-driven-trading`
- systemd exit metadata included in Feishu alerts

## Testing

Automated tests will cover:

- CLI parsing for silent startup.
- Suppression of all three startup-only Feishu paths.
- Continued logging of the full parameter snapshot in silent mode.
- Continued runtime parameter-change notifications.
- Abnormal-exit classification.
- Normal/manual-stop classification.
- Ten-minute alert cooldown behavior.

The relevant focused tests, complete test suite, shell syntax checks, and systemd
unit verification will run before completion.

## Future Hardening

A later change can add a K-line heartbeat and freshness monitor. That detects a
process that is still running but no longer processing data, which ordinary process
supervision cannot detect.
