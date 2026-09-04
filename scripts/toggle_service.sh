#!/usr/bin/env bash

# ==============================================================================
# Robinhood 监控系统与雷达一键启停总开关 (Ubuntu / Linux)
# ==============================================================================

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_DIR="$( dirname "$SCRIPT_DIR" )"
PORT=8888
TARGET_URL="http://127.0.0.1:${PORT}"
ICON_PATH="$HOME/.local/share/icons/robinhood-radar.svg"
SERVICE_NAME="robinhood-radar"

# 查找 Python 虚拟环境
PYTHON_BIN=""
if [ -f "$HOME/.venvs/robinhood-radar/bin/python3" ]; then
    PYTHON_BIN="$HOME/.venvs/robinhood-radar/bin/python3"
elif [ -f "$PROJECT_DIR/.venv/bin/python3" ]; then
    PYTHON_BIN="$PROJECT_DIR/.venv/bin/python3"
else
    PYTHON_BIN="$(which python3)"
fi

# 检查服务是否正在运行
is_running() {
    if systemctl --user is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
        return 0
    fi
    if ss -tln "( sport = :${PORT} )" 2>/dev/null | grep -q "${PORT}"; then
        return 0
    fi
    if command -v lsof >/dev/null 2>&1 && lsof -i :${PORT} >/dev/null 2>&1; then
        return 0
    fi
    return 1
}

send_notification() {
    local title="$1"
    local msg="$2"
    local urgency="${3:-normal}"
    if command -v notify-send >/dev/null 2>&1; then
        if [ -f "$ICON_PATH" ]; then
            notify-send -u "$urgency" -i "$ICON_PATH" "$title" "$msg"
        else
            notify-send -u "$urgency" "$title" "$msg"
        fi
    fi
}

if is_running; then
    # --- 关闭全部服务 ---
    echo "[*] 检测到 Robinhood 雷达服务正在运行，正在关闭所有关联服务..."
    
    # 停止 systemd 用户服务
    systemctl --user stop "${SERVICE_NAME}" 2>/dev/null || true

    # 停止常规进程
    pkill -TERM -f "uvicorn backend.api:app" 2>/dev/null || true
    pkill -TERM -f "backend.api:app" 2>/dev/null || true
    sleep 0.5

    # 强制清理占用端口的残余进程
    if command -v fuser >/dev/null 2>&1; then
        fuser -k -9 "${PORT}/tcp" 2>/dev/null || true
    fi
    pkill -9 -f "uvicorn backend.api:app" 2>/dev/null || true
    pkill -9 -f "backend.api:app" 2>/dev/null || true

    send_notification "Robinhood Radar" "服务已停止，已成功卸载全部后台服务。"
    echo "[+] 雷达服务已成功停止。"
else
    # --- 启动全部服务并打开网页 ---
    echo "[*] 雷达服务未运行，正在初始化并启动服务..."
    cd "$PROJECT_DIR" || exit 1

    # 关键环境净化：清除系统代理干扰，确保 GMGN 官方接口与 RPC 节点直连
    unset http_proxy HTTP_PROXY https_proxy HTTPS_PROXY all_proxy ALL_PROXY
    export no_proxy="localhost,127.0.0.1,gmgn.ai,*.gmgn.ai"
    export NO_PROXY="localhost,127.0.0.1,gmgn.ai,*.gmgn.ai"

    # 优先使用 systemd-run 保证作为守护进程长驻，若无则使用 setsid/nohup
    if command -v systemd-run >/dev/null 2>&1; then
        # 如果旧 unit 还在失败状态，先 reset
        systemctl --user reset-failed "${SERVICE_NAME}" 2>/dev/null || true
        systemd-run --user --unit="${SERVICE_NAME}" \
            --working-directory="${PROJECT_DIR}" \
            "${PYTHON_BIN}" -m uvicorn backend.api:app --host 0.0.0.0 --port "${PORT}" --app-dir "${PROJECT_DIR}" >/dev/null 2>&1
    else
        setsid "${PYTHON_BIN}" -m uvicorn backend.api:app --host 0.0.0.0 --port "${PORT}" --app-dir "${PROJECT_DIR}" < /dev/null >> "${PROJECT_DIR}/server.log" 2>&1 &
    fi

    # 循环等待端口就绪 (最多等待 8 秒)
    READY=0
    for i in {1..25}; do
        if ss -tln "( sport = :${PORT} )" 2>/dev/null | grep -q "${PORT}"; then
            READY=1
            break
        fi
        sleep 0.3
    done

    if [ $READY -eq 1 ]; then
        # 成功唤起默认浏览器打开 8888 端口
        if command -v xdg-open >/dev/null 2>&1; then
            xdg-open "$TARGET_URL" >/dev/null 2>&1 &
        fi
        send_notification "Robinhood Radar" "服务已成功启动！正在为您打开网页..."
        echo "[+] 所有服务已启动并在浏览器打开: $TARGET_URL"
    else
        send_notification "Robinhood Radar" "启动超时，请检查服务日志" "critical"
        echo "[-] 服务启动超时"
    fi
fi
