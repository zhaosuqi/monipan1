import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICE_TEMPLATE = PROJECT_ROOT / "deploy/systemd/db-driven-trading.service.in"
INSTALLER = PROJECT_ROOT / "scripts/install_db_trading_service.sh"


def read_service_template() -> str:
    return SERVICE_TEMPLATE.read_text(encoding="utf-8")


def read_installer() -> str:
    return INSTALLER.read_text(encoding="utf-8")


def write_stub(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def run_installer_with_stubbed_systemd(
    tmp_path: Path,
    systemd_output: Optional[str],
    *,
    env_present: bool = True,
    env_mode: str = "600",
    env_owner: str = "trader",
    arguments: Optional[list[str]] = None,
    current_user: str = "trader",
    effective_uid: Optional[int] = None,
    python_probe_exit: int = 0,
    systemd_analyze_exit: int = 0,
    systemd_analyze_present: bool = True,
    stat_present: bool = True,
    project_name: str = "project",
) -> tuple[subprocess.CompletedProcess[str], str]:
    project_root = tmp_path / project_name
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
    shutil.copy2(SERVICE_TEMPLATE, template_dir / SERVICE_TEMPLATE.name)
    (scripts_dir / "notify_db_trading_failure.py").write_text("", encoding="utf-8")
    if env_present:
        env_file = project_root / ".env"
        env_file.write_text("TEST_ONLY=1\n", encoding="utf-8")
        env_file.chmod(int(env_mode, 8))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    call_log = tmp_path / "privileged-calls.log"
    probe_log = tmp_path / "python-probe.log"
    verify_log = tmp_path / "systemd-analyze.log"
    rendered_unit = tmp_path / "rendered.service"

    for command in ("cp", "dirname", "mktemp", "rm", "rmdir"):
        executable = shutil.which(command)
        assert executable is not None
        (bin_dir / command).symlink_to(executable)

    write_stub(
        bin_dir / "id",
        'if [ "${1:-}" = "-un" ]; then printf "%s\\n" "$TEST_CURRENT_USER"; fi',
    )
    if stat_present:
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
    unsafe_python = tmp_path / "conda%env" / "bin" / "python"
    unsafe_python.parent.mkdir(parents=True)
    write_stub(unsafe_python, python_stub)

    if systemd_output is not None:
        escaped_output = systemd_output.replace("'", "'\\''")
        write_stub(bin_dir / "systemd", f"printf '%s\\n' '{escaped_output}'")

    if systemd_analyze_present:
        write_stub(
            bin_dir / "systemd-analyze",
            """printf "%s\\n" "$*" >> "$VERIFY_LOG"
if [ "$SYSTEMD_ANALYZE_EXIT" -ne 0 ]; then
    printf "%s\\n" "unit verification failed" >&2
    exit "$SYSTEMD_ANALYZE_EXIT"
fi
cp "$2" "$RENDERED_UNIT"
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
    env["PYTHON_PROBE_EXIT"] = str(python_probe_exit)
    env["REAL_PYTHON"] = real_python
    env["RENDERED_UNIT"] = str(rendered_unit)
    env["SYSTEMD_ANALYZE_EXIT"] = str(systemd_analyze_exit)
    env["TEST_CURRENT_USER"] = current_user
    env["TEST_ENV_MODE"] = env_mode
    env["TEST_ENV_OWNER"] = env_owner
    env["VERIFY_LOG"] = str(verify_log)
    resolved_arguments = [
        str(explicit_python)
        if argument == "@PYTHON@"
        else str(unsafe_python)
        if argument == "@UNSAFE_PYTHON@"
        else argument
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


def test_systemd_template_exists_and_has_only_expected_placeholders():
    content = read_service_template()

    assert set(re.findall(r"@[A-Z_]+@", content)) == {
        "@SERVICE_USER@",
        "@PROJECT_ROOT@",
        "@PYTHON_BIN@",
    }


def test_systemd_unit_and_install_contract():
    content = read_service_template()

    assert section_values(content, "Unit") == {
        "Description": ["BTCUSD perpetual data-driven trading service"],
        "Wants": ["network-online.target"],
        "After": ["network-online.target"],
        "StartLimitIntervalSec": ["300"],
        "StartLimitBurst": ["5"],
    }
    assert section_values(content, "Install") == {
        "WantedBy": ["multi-user.target"]
    }


def test_systemd_service_execution_and_failure_alert_contract():
    values = section_values(read_service_template(), "Service")

    assert values["Type"] == ["simple"]
    assert values["User"] == ["@SERVICE_USER@"]
    assert values["WorkingDirectory"] == ["@PROJECT_ROOT@"]
    assert values["EnvironmentFile"] == ["@PROJECT_ROOT@/.env"]
    assert values["Environment"] == ["PYTHONUNBUFFERED=1"]
    assert values["ExecStart"] == [
        "@PYTHON_BIN@ @PROJECT_ROOT@/data/db_driven_trading.py --live --silent-startup"
    ]
    assert values["ExecStopPost"] == [
        "@PYTHON_BIN@ @PROJECT_ROOT@/scripts/notify_db_trading_failure.py "
        "--unit db-driven-trading.service --result ${SERVICE_RESULT} "
        "--exit-code ${EXIT_CODE} --exit-status ${EXIT_STATUS} "
        "--state-file /run/db-driven-trading/failure-alert"
    ]


def test_systemd_service_supervision_and_hardening_contract():
    values = section_values(read_service_template(), "Service")

    expected = {
        "RuntimeDirectory": ["db-driven-trading"],
        "RuntimeDirectoryMode": ["0700"],
        "RuntimeDirectoryPreserve": ["restart"],
        "Restart": ["always"],
        "RestartSec": ["5"],
        "KillSignal": ["SIGINT"],
        "TimeoutStopSec": ["60"],
        "NoNewPrivileges": ["true"],
        "PrivateTmp": ["true"],
        "UMask": ["0077"],
        "StandardOutput": ["journal"],
        "StandardError": ["journal"],
        "SyslogIdentifier": ["db-driven-trading"],
    }
    for key, value in expected.items():
        assert values[key] == value


def test_service_template_contains_no_credentials():
    content = read_service_template()

    assert "API_KEY" not in content
    assert "API_SECRET" not in content
    assert "WEBHOOK" not in content
    assert "TOKEN=" not in content


def test_installer_has_strict_mode_and_infers_project_root():
    content = read_installer()

    assert content.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in content
    assert 'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' in content
    assert 'PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"' in content


def test_installer_rejects_missing_systemd_before_privileged_commands(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(tmp_path, None)

    assert result.returncode != 0
    assert "错误: 未找到 systemd" in result.stderr
    assert privileged_calls == ""


def test_installer_rejects_unparseable_systemd_version(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd version unknown",
    )

    assert result.returncode != 0
    assert "错误: 无法解析 systemd 版本" in result.stderr
    assert privileged_calls == ""


def test_installer_rejects_systemd_older_than_235(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 234 (234.11)",
    )

    assert result.returncode != 0
    assert "错误: systemd 版本 234 过低，至少需要 235" in result.stderr
    assert privileged_calls == ""


def test_installer_accepts_systemd_235_and_continues_installation(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 235 (235.1)\n+PAM +AUDIT",
    )

    assert result.returncode == 0, result.stderr
    assert "systemctl daemon-reload" in privileged_calls
    assert "systemctl enable db-driven-trading.service" in privileged_calls
    assert "systemctl restart db-driven-trading.service" in privileged_calls


def test_installer_rejects_missing_env_before_privileged_commands(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        env_present=False,
    )

    assert result.returncode != 0
    assert "错误: 找不到必需的环境变量文件" in result.stderr
    assert privileged_calls == ""


def test_installer_requires_linux_stat_before_privileged_commands(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        stat_present=False,
    )

    assert result.returncode != 0
    assert "错误: 未找到 Linux stat 命令" in result.stderr
    assert privileged_calls == ""


def test_installer_rejects_env_with_group_or_world_permissions(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        env_mode="640",
    )

    assert result.returncode != 0
    assert "错误: .env 权限必须为 0400 或 0600" in result.stderr
    assert "chmod 600" in result.stderr
    assert privileged_calls == ""


def test_installer_rejects_env_owned_by_another_user(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        env_owner="root",
    )

    assert result.returncode != 0
    assert "错误: .env 所有者必须是 trader" in result.stderr
    assert "chown trader" in result.stderr
    assert privileged_calls == ""


def test_installer_rejects_env_without_owner_read_permission(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        env_mode="200",
    )

    assert result.returncode != 0
    assert "错误: .env 权限必须为 0400 或 0600" in result.stderr
    assert "chmod 600" in result.stderr
    assert privileged_calls == ""


def test_installer_rejects_env_with_owner_execute_permission(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        env_mode="700",
    )

    assert result.returncode != 0
    assert "错误: .env 权限必须为 0400 或 0600" in result.stderr
    assert privileged_calls == ""


def test_installer_accepts_explicit_conda_python_and_runs_import_probe(tmp_path):
    result, _ = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        arguments=["--user", "trader", "--python", "@PYTHON@"],
    )

    assert result.returncode == 0, result.stderr
    probe = (tmp_path / "python-probe.log").read_text(encoding="utf-8")
    assert str(tmp_path / "conda-env" / "bin" / "python") in probe
    assert f"cwd={tmp_path / 'project'}" in probe
    assert "-c import data.db_driven_trading" in probe


def test_installer_requires_explicit_python_for_different_service_user(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        arguments=["--user", "trader"],
        current_user="root",
        effective_uid=0,
    )

    assert result.returncode != 0
    assert "错误: 当前用户与服务用户不同时必须使用 --python" in result.stderr
    assert privileged_calls == ""


def test_installer_import_probe_failure_stops_before_privileged_install(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        arguments=["--user", "trader", "--python", "@PYTHON@"],
        python_probe_exit=23,
    )

    assert result.returncode != 0
    assert "错误: Python 依赖导入检查失败" in result.stderr
    assert privileged_calls == ""


def test_installer_runs_probe_through_user_switch_for_different_user(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        arguments=["--user", "trader", "--python", "@PYTHON@"],
        current_user="root",
        effective_uid=0,
    )

    assert result.returncode == 0, result.stderr
    probe = (tmp_path / "python-probe.log").read_text(encoding="utf-8")
    assert re.search(r"runuser -u trader -- .*python -c import data.db_driven_trading", probe)
    assert "install -m 0644" in privileged_calls
    assert "sudo install" not in privileged_calls


def test_installer_rejects_non_root_cross_user_before_python_or_privileged_actions(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        arguments=["--user", "trader", "--python", "/missing/python"],
        current_user="deployer",
        effective_uid=1000,
    )

    assert result.returncode != 0
    assert "错误: 非 root 用户不能为其他服务用户安装" in result.stderr
    assert "请以 trader 用户运行，或使用 root 运行" in result.stderr
    assert "Python 必须是绝对可执行路径" not in result.stderr
    assert privileged_calls == ""
    assert not (tmp_path / "python-probe.log").exists()
    assert not (tmp_path / "systemd-analyze.log").exists()


def test_installer_accepts_service_user_identity_without_user_switch(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        arguments=["--user", "trader", "--python", "@PYTHON@"],
        current_user="trader",
        effective_uid=1000,
    )

    assert result.returncode == 0, result.stderr
    probe = (tmp_path / "python-probe.log").read_text(encoding="utf-8")
    assert probe.startswith(str(tmp_path / "conda-env" / "bin" / "python"))
    assert "runuser" not in probe
    assert "sudo -u" not in probe
    assert "sudo install -m 0644" in privileged_calls


def test_installer_rejects_positional_user_overwrite_after_double_dash(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        arguments=["trader", "--", "another"],
    )

    assert result.returncode == 2
    assert "错误: -- 后的用户不能覆盖已有位置 service-user" in result.stderr
    assert privileged_calls == ""


@pytest.mark.parametrize(
    "unsafe_user",
    ["bad user", 'bad"user', "bad\\user", "bad%user", "bad\nuser"],
)
def test_installer_rejects_unsafe_service_user(tmp_path, unsafe_user):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        arguments=["--user", unsafe_user, "--python", "@PYTHON@"],
        env_owner=unsafe_user,
    )

    assert result.returncode != 0
    assert "错误: SERVICE_USER 包含不安全字符" in result.stderr
    assert privileged_calls == ""


@pytest.mark.parametrize("project_name", ["project unsafe", "project%unsafe"])
def test_installer_rejects_unsafe_project_root(tmp_path, project_name):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        project_name=project_name,
    )

    assert result.returncode != 0
    assert "错误: PROJECT_ROOT 包含不安全字符" in result.stderr
    assert privileged_calls == ""


def test_installer_rejects_unsafe_python_path(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        arguments=["--python", "@UNSAFE_PYTHON@"],
    )

    assert result.returncode != 0
    assert "错误: PYTHON_BIN 包含不安全字符" in result.stderr
    assert privileged_calls == ""


def test_installer_requires_anchored_systemd_version_line(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "wrapper 999 for systemd 255",
    )

    assert result.returncode != 0
    assert "错误: 无法解析 systemd 版本" in result.stderr
    assert privileged_calls == ""


def test_installer_requires_systemd_analyze_before_install(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        systemd_analyze_present=False,
    )

    assert result.returncode != 0
    assert "错误: 未找到 systemd-analyze" in result.stderr
    assert privileged_calls == ""


def test_installer_verify_failure_stops_before_install_and_restart(tmp_path):
    result, privileged_calls = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        systemd_analyze_exit=1,
    )

    assert result.returncode != 0
    assert "错误: systemd unit 验证失败" in result.stderr
    assert privileged_calls == ""


def test_installer_verifies_fully_rendered_unit(tmp_path):
    result, _ = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        arguments=["--user", "trader", "--python", "@PYTHON@"],
    )

    assert result.returncode == 0, result.stderr
    rendered = (tmp_path / "rendered.service").read_text(encoding="utf-8")
    verify_call = (tmp_path / "systemd-analyze.log").read_text(encoding="utf-8")
    assert verify_call.startswith("verify ")
    assert Path(verify_call.strip().split(maxsplit=1)[1]).name == "db-driven-trading.service"
    assert "@SERVICE_USER@" not in rendered
    assert "@PROJECT_ROOT@" not in rendered
    assert "@PYTHON_BIN@" not in rendered
    assert "User=trader" in rendered
    assert f"WorkingDirectory={tmp_path / 'project'}" in rendered
    assert f"EnvironmentFile={tmp_path / 'project' / '.env'}" in rendered
    assert f"ExecStart={tmp_path / 'conda-env' / 'bin' / 'python'} " in rendered


def test_installer_resolves_and_validates_user_and_python(tmp_path):
    content = read_installer()

    result, _ = run_installer_with_stubbed_systemd(
        tmp_path,
        "systemd 255 (255.4)",
        arguments=["trader"],
    )

    assert result.returncode == 0, result.stderr
    assert 'SERVICE_USER_OPTION="$2"' in content
    assert 'PYTHON_OPTION="$2"' in content
    assert 'POSITIONAL_USER="$1"' in content
    assert 'CURRENT_USER="$(id -un)"' in content
    assert "当前用户与服务用户不同时必须使用 --python" in content
    assert re.search(r'\bid\s+"\$SERVICE_USER"', content)
    assert 'PYTHON_BIN="$(command -v python3)"' in content
    assert '[[ "$PYTHON_BIN" == /* && -x "$PYTHON_BIN" ]]' in content


def test_installer_validates_inputs_and_renders_all_placeholders_safely():
    content = read_installer()

    assert 'TEMPLATE="$PROJECT_ROOT/deploy/systemd/db-driven-trading.service.in"' in content
    assert 'NOTIFIER="$PROJECT_ROOT/scripts/notify_db_trading_failure.py"' in content
    assert '[[ -f "$TEMPLATE" ]]' in content
    assert '[[ -f "$NOTIFIER" ]]' in content
    assert re.search(r'\bmktemp\b', content)
    assert re.search(r"\btrap\b.*\bEXIT\b", content)
    for placeholder in ("@SERVICE_USER@", "@PROJECT_ROOT@", "@PYTHON_BIN@"):
        assert placeholder in content
    assert "if any(placeholder in rendered for placeholder in replacements):" in content


def test_installer_uses_sudo_array_only_for_non_root_execution():
    content = read_installer()

    assert 'INSTALLER_EUID="$EUID"' in content
    assert re.search(r'if \(\( INSTALLER_EUID == 0 \)\); then\s+SUDO=\(\)', content)
    assert re.search(r'else\s+SUDO=\(sudo\)', content)
    assert '"${SUDO[@]}" "$@"' in content
    assert 'run_privileged install -m 0644' in content
    assert 'run_privileged systemctl daemon-reload' in content
    assert 'run_privileged systemctl enable db-driven-trading.service' in content
    assert 'run_privileged systemctl restart db-driven-trading.service' in content


def test_installer_installs_expected_unit_and_prints_diagnostics():
    content = read_installer()

    assert "/etc/systemd/system/db-driven-trading.service" in content
    assert "systemctl status db-driven-trading.service" in content
    assert "journalctl -u db-driven-trading.service -f" in content


def test_installer_never_reads_credentials_or_uses_legacy_process_control():
    content = read_installer()
    forbidden_patterns = (
        r"\bsource\b",
        r"(^|\s)\.\s+[^/]",
        r"\bpgrep\b",
        r"\bkill(?:all)?\b",
        r"\bnohup\b",
        r"API_KEY\s*=",
        r"API_SECRET\s*=",
    )

    for pattern in forbidden_patterns:
        assert re.search(pattern, content, flags=re.MULTILINE) is None
