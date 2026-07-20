import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional


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
) -> tuple[subprocess.CompletedProcess[str], str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    call_log = tmp_path / "privileged-calls.log"

    for command in ("dirname", "id", "mktemp", "python3", "rm"):
        executable = shutil.which(command)
        assert executable is not None
        (bin_dir / command).symlink_to(executable)

    if systemd_output is not None:
        escaped_output = systemd_output.replace("'", "'\\''")
        write_stub(bin_dir / "systemd", f"printf '%s\\n' '{escaped_output}'")

    privileged_stub = 'printf "%s %s\\n" "${0##*/}" "$*" >> "$CALL_LOG"'
    for command in ("install", "sudo", "systemctl"):
        write_stub(bin_dir / command, privileged_stub)

    env = os.environ.copy()
    env.pop("SUDO_USER", None)
    env["PATH"] = str(bin_dir)
    env["CALL_LOG"] = str(call_log)
    result = subprocess.run(
        ["/bin/bash", str(INSTALLER)],
        cwd=PROJECT_ROOT,
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
    assert values["EnvironmentFile"] == ["-@PROJECT_ROOT@/.env"]
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


def test_installer_resolves_and_validates_user_and_python():
    content = read_installer()

    assert 'SERVICE_USER="${1:-${SUDO_USER:-$(id -un)}}"' in content
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

    assert re.search(r'if \(\( EUID == 0 \)\); then\s+SUDO=\(\)', content)
    assert re.search(r'else\s+SUDO=\(sudo\)', content)
    assert '"${SUDO[@]}" install -m 0644' in content
    assert '"${SUDO[@]}" systemctl daemon-reload' in content
    assert '"${SUDO[@]}" systemctl enable db-driven-trading.service' in content
    assert '"${SUDO[@]}" systemctl restart db-driven-trading.service' in content


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
