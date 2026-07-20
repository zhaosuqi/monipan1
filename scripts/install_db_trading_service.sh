#!/usr/bin/env bash
set -euo pipefail

if (( $# > 1 )); then
    echo "用法: $0 [service-user]" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE="$PROJECT_ROOT/deploy/systemd/db-driven-trading.service.in"
NOTIFIER="$PROJECT_ROOT/scripts/notify_db_trading_failure.py"
UNIT_PATH="/etc/systemd/system/db-driven-trading.service"
SERVICE_USER="${1:-${SUDO_USER:-$(id -un)}}"

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    echo "错误: 用户不存在: $SERVICE_USER" >&2
    exit 1
fi

PYTHON_BIN="$(command -v python3)"
if ! [[ "$PYTHON_BIN" == /* && -x "$PYTHON_BIN" ]]; then
    echo "错误: python3 必须解析为绝对可执行路径" >&2
    exit 1
fi

if ! [[ -f "$TEMPLATE" ]]; then
    echo "错误: 找不到 systemd 模板: $TEMPLATE" >&2
    exit 1
fi
if ! [[ -f "$NOTIFIER" ]]; then
    echo "错误: 找不到异常退出告警脚本: $NOTIFIER" >&2
    exit 1
fi

TEMP_UNIT="$(mktemp "${TMPDIR:-/tmp}/db-driven-trading.service.XXXXXX")"
trap 'rm -f "$TEMP_UNIT"' EXIT

"$PYTHON_BIN" - "$TEMPLATE" "$TEMP_UNIT" "$SERVICE_USER" "$PROJECT_ROOT" "$PYTHON_BIN" <<'PY'
import sys
from pathlib import Path


template_path, output_path, service_user, project_root, python_bin = sys.argv[1:]
rendered = Path(template_path).read_text(encoding="utf-8")
replacements = {
    "@SERVICE_USER@": service_user,
    "@PROJECT_ROOT@": project_root,
    "@PYTHON_BIN@": python_bin,
}

for placeholder, value in replacements.items():
    if placeholder not in rendered:
        raise SystemExit(f"模板缺少占位符: {placeholder}")
    if "\n" in value or "\r" in value:
        raise SystemExit(f"占位符值包含换行符: {placeholder}")
    rendered = rendered.replace(placeholder, value)

if any(placeholder in rendered for placeholder in replacements):
    raise SystemExit("模板包含未替换的占位符")

Path(output_path).write_text(rendered, encoding="utf-8")
PY

if (( EUID == 0 )); then
    SUDO=()
else
    SUDO=(sudo)
    if ! command -v sudo >/dev/null 2>&1; then
        echo "错误: 非 root 用户安装需要 sudo" >&2
        exit 1
    fi
fi

"${SUDO[@]}" install -m 0644 "$TEMP_UNIT" "$UNIT_PATH"
"${SUDO[@]}" systemctl daemon-reload
"${SUDO[@]}" systemctl enable db-driven-trading.service
"${SUDO[@]}" systemctl restart db-driven-trading.service

echo "db-driven-trading.service 已安装并重启。"
echo "查看状态: systemctl status db-driven-trading.service"
echo "跟踪日志: journalctl -u db-driven-trading.service -f"
