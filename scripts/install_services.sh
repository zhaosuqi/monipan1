#!/usr/bin/env bash
set -euo pipefail

validate_systemd_version() {
    local systemd_bin version_output first_line version

    if ! systemd_bin="$(command -v systemd)" || [[ -z "$systemd_bin" ]]; then
        echo "错误: 未找到 systemd" >&2
        return 1
    fi
    if ! version_output="$("$systemd_bin" --version 2>&1)"; then
        echo "错误: 无法执行 systemd --version" >&2
        return 1
    fi

    first_line="${version_output%%$'\n'*}"
    if [[ ! "$first_line" =~ ^systemd\ ([0-9]+) ]]; then
        echo "错误: 无法解析 systemd 版本: $first_line" >&2
        return 1
    fi

    version="${BASH_REMATCH[1]}"
    if (( 10#$version < 235 )); then
        echo "错误: systemd 版本 $version 过低，至少需要 235" >&2
        return 1
    fi
}

resolve_systemd_analyze() {
    if ! SYSTEMD_ANALYZE_BIN="$(command -v systemd-analyze)" ||
        ! [[ "$SYSTEMD_ANALYZE_BIN" == /* && -x "$SYSTEMD_ANALYZE_BIN" ]]; then
        echo "错误: 未找到 systemd-analyze" >&2
        return 1
    fi
}

validate_safe_service_user() {
    if [[ ! "$1" =~ ^[A-Za-z_][A-Za-z0-9_-]*$ ]]; then
        echo "错误: SERVICE_USER 包含不安全字符" >&2
        return 1
    fi
}

validate_safe_absolute_path() {
    local label="$1"
    local value="$2"

    if [[ ! "$value" =~ ^/[A-Za-z0-9._/:+-]+$ ]] ||
        [[ "$value" == *"/../"* || "$value" == */.. || "$value" == *"/./"* ]]; then
        echo "错误: $label 包含不安全字符或路径片段" >&2
        return 1
    fi
}

validate_installer_identity() {
    local current_user="$1"
    local service_user="$2"
    local effective_uid="$3"

    if [[ "$current_user" != "$service_user" ]] && (( effective_uid != 0 )); then
        echo "错误: 非 root 用户不能为其他服务用户安装" >&2
        echo "请以 $service_user 用户运行，或使用 root 运行" >&2
        return 1
    fi
}

usage() {
    echo "用法: $0 [service-user] [--user USER] [--python ABSOLUTE_PATH] [--web-port PORT] [--only UNIT]... [--dry-run]" >&2
}

SERVICE_USER_OPTION=""
PYTHON_OPTION=""
WEB_PORT_OPTION=""
DRY_RUN=0
POSITIONAL_USER=""
ONLY_OPTIONS=()
while (( $# > 0 )); do
    case "$1" in
        --user)
            if (( $# < 2 )) || [[ -z "$2" ]]; then
                usage
                exit 2
            fi
            SERVICE_USER_OPTION="$2"
            shift 2
            ;;
        --python)
            if (( $# < 2 )) || [[ -z "$2" ]]; then
                usage
                exit 2
            fi
            PYTHON_OPTION="$2"
            shift 2
            ;;
        --web-port)
            if (( $# < 2 )) || [[ -z "$2" ]]; then
                usage
                exit 2
            fi
            WEB_PORT_OPTION="$2"
            shift 2
            ;;
        --only)
            if (( $# < 2 )) || [[ -z "$2" ]]; then
                usage
                exit 2
            fi
            ONLY_OPTIONS+=("$2")
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --)
            shift
            if (( $# > 1 )); then
                usage
                exit 2
            fi
            if [[ -n "$POSITIONAL_USER" && $# -eq 1 ]]; then
                echo "错误: -- 后的用户不能覆盖已有位置 service-user" >&2
                usage
                exit 2
            fi
            if (( $# == 1 )); then
                POSITIONAL_USER="$1"
            fi
            shift "$#"
            ;;
        -*)
            echo "错误: 未知参数: $1" >&2
            usage
            exit 2
            ;;
        *)
            if [[ -n "$POSITIONAL_USER" ]]; then
                usage
                exit 2
            fi
            POSITIONAL_USER="$1"
            shift
            ;;
    esac
done

if [[ -n "$SERVICE_USER_OPTION" && -n "$POSITIONAL_USER" ]]; then
    echo "错误: 不能同时使用位置 service-user 和 --user" >&2
    usage
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
NOTIFIER="$PROJECT_ROOT/scripts/notify_db_trading_failure.py"
HEALTH_CHECK_SCRIPT="$PROJECT_ROOT/scripts/service_health_check.py"
ENV_FILE="$PROJECT_ROOT/.env"
CURRENT_USER="$(id -un)"
INSTALLER_EUID="$EUID"
SERVICE_USER="${SERVICE_USER_OPTION:-${POSITIONAL_USER:-${SUDO_USER:-$CURRENT_USER}}}"
WEB_PORT="${WEB_PORT_OPTION:-8076}"

if [[ ! "$WEB_PORT" =~ ^[0-9]+$ ]] || (( 10#$WEB_PORT < 1 || 10#$WEB_PORT > 65535 )); then
    echo "错误: --web-port 必须是 1-65535 的端口号: $WEB_PORT" >&2
    usage
    exit 2
fi

# 安装顺序: 4 个 service 在前，timer 最后（timer 触发 service-health-check.service）
UNIT_NAMES=(
    realtime-kline-sync.service
    sync-macd-indicators.service
    kline-web.service
    service-health-check.service
    service-health-check.timer
)

SELECTED_UNITS=()
if (( ${#ONLY_OPTIONS[@]} > 0 )); then
    for requested in "${ONLY_OPTIONS[@]}"; do
        base="$requested"
        base="${base%.service}"
        base="${base%.timer}"
        matched=0
        for unit in "${UNIT_NAMES[@]}"; do
            if [[ "$unit" == "$base".* ]]; then
                duplicate=0
                for existing in ${SELECTED_UNITS[@]+"${SELECTED_UNITS[@]}"}; do
                    if [[ "$existing" == "$unit" ]]; then
                        duplicate=1
                    fi
                done
                if (( ! duplicate )); then
                    SELECTED_UNITS+=("$unit")
                fi
                matched=1
            fi
        done
        if (( ! matched )); then
            echo "错误: 未知 unit: $requested" >&2
            usage
            exit 2
        fi
    done
else
    SELECTED_UNITS=("${UNIT_NAMES[@]}")
fi

validate_safe_service_user "$SERVICE_USER"
validate_safe_absolute_path "PROJECT_ROOT" "$PROJECT_ROOT"

if (( ! DRY_RUN )); then
    validate_installer_identity "$CURRENT_USER" "$SERVICE_USER" "$INSTALLER_EUID"

    validate_systemd_version
    resolve_systemd_analyze

    if ! id "$SERVICE_USER" >/dev/null 2>&1; then
        echo "错误: 用户不存在: $SERVICE_USER" >&2
        exit 1
    fi
fi

if [[ -n "$PYTHON_OPTION" ]]; then
    PYTHON_BIN="$PYTHON_OPTION"
else
    if (( ! DRY_RUN )) && [[ "$CURRENT_USER" != "$SERVICE_USER" ]]; then
        echo "错误: 当前用户与服务用户不同时必须使用 --python 指定服务用户的 Python" >&2
        exit 1
    fi
    PYTHON_BIN="$(command -v python3)"
fi
validate_safe_absolute_path "PYTHON_BIN" "$PYTHON_BIN"
if ! [[ "$PYTHON_BIN" == /* && -x "$PYTHON_BIN" ]]; then
    echo "错误: Python 必须是绝对可执行路径: $PYTHON_BIN" >&2
    exit 1
fi

for unit in "${SELECTED_UNITS[@]}"; do
    template="$PROJECT_ROOT/deploy/systemd/$unit.in"
    if ! [[ -f "$template" ]]; then
        echo "错误: 找不到 systemd 模板: $template" >&2
        exit 1
    fi
done

needs_notifier=0
for unit in "${SELECTED_UNITS[@]}"; do
    if [[ "$unit" == *.service && "$unit" != service-health-check.service ]]; then
        needs_notifier=1
    fi
done
if (( needs_notifier )) && ! [[ -f "$NOTIFIER" ]]; then
    echo "错误: 找不到异常退出告警脚本: $NOTIFIER" >&2
    exit 1
fi

if (( ! DRY_RUN )); then
    if ! [[ -f "$ENV_FILE" ]]; then
        echo "错误: 找不到必需的环境变量文件: $ENV_FILE" >&2
        exit 1
    fi

    if ! STAT_BIN="$(command -v stat)" ||
        ! [[ "$STAT_BIN" == /* && -x "$STAT_BIN" ]]; then
        echo "错误: 未找到 Linux stat 命令" >&2
        exit 1
    fi
    if ! ENV_METADATA="$("$STAT_BIN" -c '%U %a' -- "$ENV_FILE")"; then
        echo "错误: 无法读取 .env 的所有者和权限" >&2
        exit 1
    fi
    read -r ENV_OWNER ENV_MODE ENV_EXTRA <<< "$ENV_METADATA"
    ENV_REMEDIATION="修复: sudo chown $SERVICE_USER '$ENV_FILE' && sudo chmod 600 '$ENV_FILE'"
    if [[ -n "${ENV_EXTRA:-}" || ! "$ENV_MODE" =~ ^[0-7]{3,4}$ ]]; then
        echo "错误: 无法解析 .env 权限" >&2
        echo "$ENV_REMEDIATION" >&2
        exit 1
    fi
    if [[ "$ENV_OWNER" != "$SERVICE_USER" ]]; then
        echo "错误: .env 所有者必须是 ${SERVICE_USER}，当前为 $ENV_OWNER" >&2
        echo "$ENV_REMEDIATION" >&2
        exit 1
    fi
    ENV_MODE_VALUE=$((8#$ENV_MODE))
    if (( ENV_MODE_VALUE != 0400 && ENV_MODE_VALUE != 0600 )); then
        echo "错误: .env 权限必须为 0400 或 0600，当前为 $ENV_MODE" >&2
        echo "$ENV_REMEDIATION" >&2
        exit 1
    fi
fi

run_python_as_service_user() {
    if [[ "$CURRENT_USER" == "$SERVICE_USER" ]]; then
        (cd "$PROJECT_ROOT" && "$PYTHON_BIN" "$@")
    elif (( INSTALLER_EUID == 0 )); then
        local runuser_bin
        runuser_bin="$(command -v runuser)"
        if ! [[ "$runuser_bin" == /* && -x "$runuser_bin" ]]; then
            echo "错误: root 为其他用户执行检查时需要 runuser" >&2
            return 1
        fi
        (cd "$PROJECT_ROOT" && "$runuser_bin" -u "$SERVICE_USER" -- "$PYTHON_BIN" "$@")
    else
        local sudo_bin
        sudo_bin="$(command -v sudo)"
        if ! [[ "$sudo_bin" == /* && -x "$sudo_bin" ]]; then
            echo "错误: 为其他用户执行检查时需要 sudo" >&2
            return 1
        fi
        (cd "$PROJECT_ROOT" && "$sudo_bin" -u "$SERVICE_USER" -- "$PYTHON_BIN" "$@")
    fi
}

probe_python_dependencies() {
    local unit
    for unit in "${SELECTED_UNITS[@]}"; do
        case "$unit" in
            realtime-kline-sync.service)
                if ! run_python_as_service_user -c 'import data.realtime_kline_sync'; then
                    echo "错误: Python 依赖导入检查失败: import data.realtime_kline_sync" >&2
                    return 1
                fi
                ;;
            sync-macd-indicators.service)
                if ! run_python_as_service_user -c 'import data.sync_macd_indicators'; then
                    echo "错误: Python 依赖导入检查失败: import data.sync_macd_indicators" >&2
                    return 1
                fi
                ;;
            kline-web.service)
                if ! run_python_as_service_user -c 'import web.kline_viewer'; then
                    echo "错误: Python 依赖导入检查失败: import web.kline_viewer" >&2
                    return 1
                fi
                ;;
            service-health-check.service)
                # scripts/ 目录没有 __init__.py，且该脚本由其他任务提供，
                # 用文件存在性 + py_compile 语法检查代替 import 探测
                if ! [[ -f "$HEALTH_CHECK_SCRIPT" ]]; then
                    echo "错误: 找不到健康检查脚本: $HEALTH_CHECK_SCRIPT" >&2
                    return 1
                fi
                if ! run_python_as_service_user -m py_compile "$HEALTH_CHECK_SCRIPT"; then
                    echo "错误: 健康检查脚本语法检查失败: $HEALTH_CHECK_SCRIPT" >&2
                    return 1
                fi
                ;;
        esac
    done
}

if (( ! DRY_RUN )); then
    if ! probe_python_dependencies; then
        exit 1
    fi
fi

TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/install-services.XXXXXX")"
trap 'status=$?; rm -rf "$TEMP_DIR"; exit "$status"' EXIT

render_unit() {
    local template="$1"
    local output="$2"

    "$PYTHON_BIN" - "$template" "$output" "$SERVICE_USER" "$PROJECT_ROOT" "$PYTHON_BIN" "$WEB_PORT" <<'PY'
import re
import sys
from pathlib import Path


template_path, output_path, service_user, project_root, python_bin, web_port = sys.argv[1:]
rendered = Path(template_path).read_text(encoding="utf-8")
replacements = {
    "@SERVICE_USER@": service_user,
    "@PROJECT_ROOT@": project_root,
    "@PYTHON_BIN@": python_bin,
    "@WEB_PORT@": web_port,
}

for placeholder, value in replacements.items():
    if placeholder not in rendered:
        continue
    if "\n" in value or "\r" in value:
        raise SystemExit(f"占位符值包含换行符: {placeholder}")
    rendered = rendered.replace(placeholder, value)

if re.search(r"@[A-Z_]+@", rendered):
    raise SystemExit("模板包含未替换的占位符")

Path(output_path).write_text(rendered, encoding="utf-8")
PY
}

for unit in "${SELECTED_UNITS[@]}"; do
    render_unit "$PROJECT_ROOT/deploy/systemd/$unit.in" "$TEMP_DIR/$unit"
done

if (( DRY_RUN )); then
    for unit in "${SELECTED_UNITS[@]}"; do
        echo "===== $unit ====="
        cat "$TEMP_DIR/$unit"
    done
    exit 0
fi

for unit in "${SELECTED_UNITS[@]}"; do
    if ! "$SYSTEMD_ANALYZE_BIN" verify "$TEMP_DIR/$unit"; then
        echo "错误: systemd unit 验证失败，未安装或重启服务: $unit" >&2
        exit 1
    fi
done

if (( INSTALLER_EUID == 0 )); then
    SUDO=()
else
    SUDO=(sudo)
    if ! command -v sudo >/dev/null 2>&1; then
        echo "错误: 非 root 用户安装需要 sudo" >&2
        exit 1
    fi
fi

run_privileged() {
    if (( INSTALLER_EUID == 0 )); then
        "$@"
    else
        "${SUDO[@]}" "$@"
    fi
}

for unit in "${SELECTED_UNITS[@]}"; do
    run_privileged install -m 0644 "$TEMP_DIR/$unit" "/etc/systemd/system/$unit"
    run_privileged systemctl daemon-reload
    run_privileged systemctl enable "$unit"
    run_privileged systemctl restart "$unit"
done

echo "以下 unit 已安装并重启:"
for unit in "${SELECTED_UNITS[@]}"; do
    echo "  $unit"
    echo "    查看状态: systemctl status $unit"
    if [[ "$unit" == *.timer ]]; then
        echo "    查看定时器: systemctl list-timers $unit"
    else
        echo "    跟踪日志: journalctl -u $unit -f"
    fi
done
