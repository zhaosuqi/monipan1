import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = PROJECT_ROOT / "scripts/install_services.sh"
TEMPLATE_DIR = PROJECT_ROOT / "deploy" / "systemd"

UNIT_NAMES = [
    "realtime-kline-sync.service",
    "sync-macd-indicators.service",
    "kline-web.service",
    "service-health-check.service",
    "service-health-check.timer",
]
LONG_RUNNING_SERVICES = [
    "realtime-kline-sync.service",
    "sync-macd-indicators.service",
    "kline-web.service",
]
BASE_PLACEHOLDERS = {"@SERVICE_USER@", "@PROJECT_ROOT@", "@PYTHON_BIN@"}


def read_template(unit: str) -> str:
    return (TEMPLATE_DIR / f"{unit}.in").read_text(encoding="utf-8")


def read_installer() -> str:
    return INSTALLER.read_text(encoding="utf-8")


def write_stub(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def section_values(content: str, section: str) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    current_section = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1]
        elif current_section == section and line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values.setdefault(key, []).append(value)
    return values


def run_installer(
    arguments: list[str],
    *,
    env: Optional[dict[str, str]] = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(INSTALLER), *arguments],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def make_restricted_env(tmp_path: Path, commands: tuple[str, ...]) -> dict[str, str]:
    """构造仅含必要真实命令的 PATH，外加记录 systemctl 调用的 stub。"""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for command in commands:
        executable = shutil.which(command)
        assert executable is not None
        (bin_dir / command).symlink_to(executable)
    systemctl_log = tmp_path / "systemctl.log"
    write_stub(
        bin_dir / "systemctl",
        f'printf "%s\\n" "$*" >> "{systemctl_log}"\nexit 1',
    )
    write_stub(bin_dir / "systemd", "exit 1")
    write_stub(bin_dir / "systemd-analyze", "exit 1")
    env = os.environ.copy()
    env["PATH"] = str(bin_dir)
    return env


def run_installer_with_stubbed_systemd(
    tmp_path: Path,
    *,
    arguments: Optional[list[str]] = None,
    current_user: str = "root",
    effective_uid: Optional[int] = 0,
    env_owner: str = "trader",
    env_mode: str = "600",
    health_check_present: bool = True,
) -> tuple[subprocess.CompletedProcess[str], str]:
    project_root = tmp_path / "project"
    scripts_dir = project_root / "scripts"
    template_dir = project_root / "deploy" / "systemd"
    scripts_dir.mkdir(parents=True)
    template_dir.mkdir(parents=True)
    installer_copy = scripts_dir / INSTALLER.name
    shutil.copy2(INSTALLER, installer_copy)
    if effective_uid is not None:
        installer_content = installer_copy.read_text(encoding="utf-8")
        installer_content = installer_content.replace(
            'INSTALLER_EUID="$EUID"',
            f"INSTALLER_EUID={effective_uid}",
        )
        installer_copy.write_text(installer_content, encoding="utf-8")
    for unit in UNIT_NAMES:
        shutil.copy2(TEMPLATE_DIR / f"{unit}.in", template_dir / f"{unit}.in")
    (scripts_dir / "notify_db_trading_failure.py").write_text("", encoding="utf-8")
    if health_check_present:
        (scripts_dir / "service_health_check.py").write_text("", encoding="utf-8")
    env_file = project_root / ".env"
    env_file.write_text("TEST_ONLY=1\n", encoding="utf-8")
    env_file.chmod(int(env_mode, 8))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    call_log = tmp_path / "privileged-calls.log"
    probe_log = tmp_path / "python-probe.log"
    verify_log = tmp_path / "systemd-analyze.log"
    rendered_dir = tmp_path / "rendered"
    rendered_dir.mkdir()

    for command in ("cp", "dirname", "mktemp", "rm", "rmdir", "cat"):
        executable = shutil.which(command)
        assert executable is not None
        (bin_dir / command).symlink_to(executable)

    write_stub(
        bin_dir / "id",
        'if [ "${1:-}" = "-un" ]; then printf "%s\\n" "$TEST_CURRENT_USER"; fi',
    )
    write_stub(
        bin_dir / "stat",
        'printf "%s %s\\n" "$TEST_ENV_OWNER" "$TEST_ENV_MODE"',
    )
    real_python = shutil.which("python3")
    assert real_python is not None
    python_stub = """if [ "${1:-}" = "-c" ]; then
    printf "%s cwd=%s %s\\n" "$0" "$PWD" "$*" >> "$PROBE_LOG"
    exit "$PYTHON_PROBE_EXIT"
fi
exec "$REAL_PYTHON" "$@"
"""
    write_stub(bin_dir / "python3", python_stub)
    explicit_python = tmp_path / "conda-env" / "bin" / "python"
    explicit_python.parent.mkdir(parents=True)
    write_stub(explicit_python, python_stub)

    write_stub(bin_dir / "systemd", "printf '%s\\n' 'systemd 255 (255.4)'")
    write_stub(
        bin_dir / "systemd-analyze",
        """printf "%s\\n" "$*" >> "$VERIFY_LOG"
cp "$2" "$RENDERED_DIR/${2##*/}"
""",
    )

    privileged_stub = 'printf "%s %s\\n" "${0##*/}" "$*" >> "$CALL_LOG"'
    for command in ("install", "systemctl"):
        write_stub(bin_dir / command, privileged_stub)
    user_switch_stub = """if [ "${1:-}" = "-u" ]; then
    printf "%s %s\\n" "${0##*/}" "$*" >> "$PROBE_LOG"
    exit "$PYTHON_PROBE_EXIT"
fi
printf "%s %s\\n" "${0##*/}" "$*" >> "$CALL_LOG"
"""
    for command in ("runuser", "sudo"):
        write_stub(bin_dir / command, user_switch_stub)

    env = os.environ.copy()
    env.pop("SUDO_USER", None)
    env["PATH"] = str(bin_dir)
    env["CALL_LOG"] = str(call_log)
    env["PROBE_LOG"] = str(probe_log)
    env["PYTHON_PROBE_EXIT"] = "0"
    env["REAL_PYTHON"] = real_python
    env["RENDERED_DIR"] = str(rendered_dir)
    env["TEST_CURRENT_USER"] = current_user
    env["TEST_ENV_MODE"] = env_mode
    env["TEST_ENV_OWNER"] = env_owner
    env["VERIFY_LOG"] = str(verify_log)
    resolved_arguments = [
        str(explicit_python) if argument == "@PYTHON@" else argument
        for argument in (arguments or [])
    ]
    result = subprocess.run(
        ["/bin/bash", str(installer_copy), *resolved_arguments],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    calls = call_log.read_text(encoding="utf-8") if call_log.exists() else ""
    return result, calls


@pytest.mark.parametrize(
    "unit,expected",
    [
        ("realtime-kline-sync.service", BASE_PLACEHOLDERS),
        ("sync-macd-indicators.service", BASE_PLACEHOLDERS),
        ("kline-web.service", BASE_PLACEHOLDERS | {"@WEB_PORT@"}),
        ("service-health-check.service", BASE_PLACEHOLDERS),
        ("service-health-check.timer", set()),
    ],
)
def test_templates_have_only_expected_placeholders(unit, expected):
    content = read_template(unit)

    assert set(re.findall(r"@[A-Z_]+@", content)) == expected


@pytest.mark.parametrize("unit", LONG_RUNNING_SERVICES)
def test_long_running_service_supervision_and_hardening_contract(unit):
    values = section_values(read_template(unit), "Service")
    name = unit[: -len(".service")]

    assert values["Type"] == ["simple"]
    assert values["Restart"] == ["always"]
    assert values["RestartSec"] == ["5"]
    assert values["NoNewPrivileges"] == ["true"]
    assert values["PrivateTmp"] == ["true"]
    assert values["EnvironmentFile"] == ["@PROJECT_ROOT@/.env"]
    assert values["Environment"] == ["PYTHONUNBUFFERED=1"]
    assert values["RuntimeDirectory"] == [name]
    assert values["SyslogIdentifier"] == [name]


@pytest.mark.parametrize("unit", LONG_RUNNING_SERVICES)
def test_long_running_service_failure_alert_contract(unit):
    values = section_values(read_template(unit), "Service")
    name = unit[: -len(".service")]

    assert values["ExecStopPost"] == [
        "@PYTHON_BIN@ @PROJECT_ROOT@/scripts/notify_db_trading_failure.py "
        f"--unit {unit} --result ${{SERVICE_RESULT}} "
        "--exit-code ${EXIT_CODE} --exit-status ${EXIT_STATUS} "
        f"--state-file /run/{name}/failure-alert"
    ]


def test_service_exec_start_contract():
    assert section_values(read_template("realtime-kline-sync.service"), "Service")[
        "ExecStart"
    ] == ["@PYTHON_BIN@ @PROJECT_ROOT@/data/realtime_kline_sync.py"]
    assert section_values(read_template("sync-macd-indicators.service"), "Service")[
        "ExecStart"
    ] == ["@PYTHON_BIN@ @PROJECT_ROOT@/data/sync_macd_indicators.py --loop"]
    assert section_values(read_template("kline-web.service"), "Service")[
        "ExecStart"
    ] == ["@PYTHON_BIN@ @PROJECT_ROOT@/web/kline_viewer.py --port @WEB_PORT@"]


def test_health_check_service_is_oneshot_without_restart_or_install():
    content = read_template("service-health-check.service")
    values = section_values(content, "Service")

    assert values["Type"] == ["oneshot"]
    assert "Restart" not in values
    assert "ExecStopPost" not in values
    assert "RuntimeDirectory" not in values
    assert values["ExecStart"] == [
        "@PYTHON_BIN@ @PROJECT_ROOT@/scripts/service_health_check.py"
    ]
    assert "[Install]" not in content


def test_health_check_timer_contract():
    content = read_template("service-health-check.timer")

    assert section_values(content, "Timer") == {
        "OnBootSec": ["60"],
        "OnUnitActiveSec": ["60"],
        "Persistent": ["true"],
    }
    assert section_values(content, "Install") == {"WantedBy": ["timers.target"]}


def test_templates_contain_no_credentials():
    for unit in UNIT_NAMES:
        content = read_template(unit)
        assert "API_KEY" not in content
        assert "API_SECRET" not in content
        assert "WEBHOOK" not in content
        assert "TOKEN=" not in content


def test_dry_run_renders_all_units_without_systemd(tmp_path):
    env = make_restricted_env(
        tmp_path, ("dirname", "id", "python3", "mktemp", "cat", "rm", "rmdir")
    )

    result = run_installer(["--dry-run"], env=env)

    assert result.returncode == 0, result.stderr
    for unit in UNIT_NAMES:
        assert f"===== {unit} =====" in result.stdout
    assert re.search(r"@[A-Z_]+@", result.stdout) is None
    assert "kline_viewer.py --port 8076" in result.stdout
    # 未调用 systemctl（macOS 无 systemd，stub 会留下日志）
    assert not (tmp_path / "systemctl.log").exists()


def test_dry_run_only_filter_selects_single_unit():
    for only_value in ("kline-web", "kline-web.service"):
        result = run_installer(["--dry-run", "--only", only_value])

        assert result.returncode == 0, result.stderr
        assert "===== kline-web.service =====" in result.stdout
        assert "realtime_kline_sync.py" not in result.stdout
        assert "===== service-health-check.timer =====" not in result.stdout


def test_dry_run_only_filter_accepts_multiple_values():
    result = run_installer(
        ["--dry-run", "--only", "realtime-kline-sync", "--only", "sync-macd-indicators"]
    )

    assert result.returncode == 0, result.stderr
    assert "===== realtime-kline-sync.service =====" in result.stdout
    assert "===== sync-macd-indicators.service =====" in result.stdout
    assert "===== kline-web.service =====" not in result.stdout
    assert "===== service-health-check.timer =====" not in result.stdout


def test_dry_run_only_health_check_selects_service_and_timer():
    result = run_installer(["--dry-run", "--only", "service-health-check"])

    assert result.returncode == 0, result.stderr
    assert "===== service-health-check.service =====" in result.stdout
    assert "===== service-health-check.timer =====" in result.stdout
    assert "===== kline-web.service =====" not in result.stdout


def test_dry_run_web_port_option_overrides_default():
    result = run_installer(["--dry-run", "--only", "kline-web", "--web-port", "9000"])

    assert result.returncode == 0, result.stderr
    assert "kline_viewer.py --port 9000" in result.stdout


@pytest.mark.parametrize(
    "arguments",
    [
        ["--bogus"],
        ["--web-port"],
        ["--web-port", "abc"],
        ["--web-port", "70000"],
        ["--only", "unknown-unit"],
        ["trader", "--user", "trader"],
    ],
)
def test_unknown_or_invalid_arguments_exit_with_code_2(arguments):
    result = run_installer(arguments)

    assert result.returncode == 2


def test_installer_has_strict_mode_and_infers_project_root():
    content = read_installer()

    assert content.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in content
    assert 'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' in content
    assert 'PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"' in content


def test_stubbed_install_installs_services_in_order_with_timer_last(tmp_path):
    result, calls = run_installer_with_stubbed_systemd(
        tmp_path,
        arguments=["--user", "trader", "--python", "@PYTHON@", "--web-port", "9000"],
    )

    assert result.returncode == 0, result.stderr
    compact_calls = []
    for line in calls.splitlines():
        command, rest = line.split(" ", 1)
        if command == "install":
            compact_calls.append(f"install {rest.rsplit('/', 1)[-1]}")
        else:
            compact_calls.append(f"{command} {rest}")
    expected_calls = []
    for unit in UNIT_NAMES:
        expected_calls += [
            f"install {unit}",
            "systemctl daemon-reload",
            f"systemctl enable {unit}",
            f"systemctl restart {unit}",
        ]
    assert compact_calls == expected_calls


def test_stubbed_install_renders_all_units_without_leftover_placeholders(tmp_path):
    result, _ = run_installer_with_stubbed_systemd(
        tmp_path,
        arguments=["--user", "trader", "--python", "@PYTHON@", "--web-port", "9000"],
    )

    assert result.returncode == 0, result.stderr
    rendered_dir = tmp_path / "rendered"
    assert sorted(path.name for path in rendered_dir.iterdir()) == sorted(UNIT_NAMES)
    project_root = tmp_path / "project"
    python_bin = tmp_path / "conda-env" / "bin" / "python"
    for unit in UNIT_NAMES:
        rendered = (rendered_dir / unit).read_text(encoding="utf-8")
        assert re.search(r"@[A-Z_]+@", rendered) is None
    web_rendered = (rendered_dir / "kline-web.service").read_text(encoding="utf-8")
    assert "User=trader" in web_rendered
    assert f"WorkingDirectory={project_root}" in web_rendered
    assert f"EnvironmentFile={project_root / '.env'}" in web_rendered
    assert f"ExecStart={python_bin} {project_root}/web/kline_viewer.py --port 9000" in web_rendered
    timer_rendered = (rendered_dir / "service-health-check.timer").read_text(
        encoding="utf-8"
    )
    assert "OnBootSec=60" in timer_rendered


def test_stubbed_install_runs_import_probes_for_each_service(tmp_path):
    result, _ = run_installer_with_stubbed_systemd(
        tmp_path,
        arguments=["--user", "trader", "--python", "@PYTHON@"],
    )

    assert result.returncode == 0, result.stderr
    probe = (tmp_path / "python-probe.log").read_text(encoding="utf-8")
    assert re.search(r"runuser -u trader -- .*python -c import data.realtime_kline_sync", probe)
    assert re.search(r"runuser -u trader -- .*python -c import data.sync_macd_indicators", probe)
    assert re.search(r"runuser -u trader -- .*python -c import web.kline_viewer", probe)
    assert re.search(r"runuser -u trader -- .*python -m py_compile .*service_health_check\.py", probe)


def test_stubbed_install_only_filter_installs_selected_units(tmp_path):
    result, calls = run_installer_with_stubbed_systemd(
        tmp_path,
        arguments=["--user", "trader", "--python", "@PYTHON@", "--only", "kline-web"],
    )

    assert result.returncode == 0, result.stderr
    assert "systemctl enable kline-web.service" in calls
    assert "systemctl restart kline-web.service" in calls
    assert "realtime-kline-sync" not in calls
    assert "service-health-check" not in calls
    assert sorted(path.name for path in (tmp_path / "rendered").iterdir()) == [
        "kline-web.service"
    ]


def test_stubbed_install_requires_health_check_script_when_selected(tmp_path):
    result, calls = run_installer_with_stubbed_systemd(
        tmp_path,
        arguments=["--user", "trader", "--python", "@PYTHON@"],
        health_check_present=False,
    )

    assert result.returncode != 0
    assert "错误: 找不到健康检查脚本" in result.stderr
    assert calls == ""
