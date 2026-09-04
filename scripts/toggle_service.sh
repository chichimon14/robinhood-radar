#!/usr/bin/env bash

# ==============================================================================
# Robinhood 监控系统与雷达一键启停总开关 (全面集成所有服务)
# ==============================================================================

PROJECT_DIR="/Users/julian/antigravity/gmgn"
PORT=8888
TARGET_URL="http://127.0.0.1:${PORT}"

# 1. 检查 8888 端口是否正在运行
IS_RUNNING=0
if lsof -i :${PORT} >/dev/null 2>&1; then
    IS_RUNNING=1
fi

if [ $IS_RUNNING -eq 1 ]; then
    # --- 关闭全部服务与对应网页 ---
    echo "[*] 检测到 Robinhood 雷达服务正在运行，正在关闭所有关联进程..."
    
    # 彻底关闭进程树
    pkill -9 -f "uvicorn backend.api:app" 2>/dev/null
    pkill -9 -f "backend.api:app" 2>/dev/null
    PIDS=$(lsof -ti :${PORT} 2>/dev/null)
    if [ -n "$PIDS" ]; then
        kill -9 $PIDS 2>/dev/null
    fi
    sleep 0.5

    # 尝试关闭 Brave、Chrome、Safari 中对应的雷达网页标签
    osascript -e '
    try
        tell application "Brave Browser"
            if it is running then
                repeat with w in windows
                    repeat with t in (tabs of w)
                        if URL of t contains "127.0.0.1:8888" or URL of t contains "localhost:8888" then
                            close t
                        end if
                    end repeat
                end repeat
            end if
        end tell
    end try
    try
        tell application "Google Chrome"
            if it is running then
                repeat with w in windows
                    repeat with t in (tabs of w)
                        if URL of t contains "127.0.0.1:8888" or URL of t contains "localhost:8888" then
                            close t
                        end if
                    end repeat
                end repeat
            end if
        end tell
    end try
    try
        tell application "Safari"
            if it is running then
                repeat with w in windows
                    repeat with t in (tabs of w)
                        if URL of t contains "127.0.0.1:8888" or URL of t contains "localhost:8888" then
                            close t
                        end if
                    end repeat
                end repeat
            end if
        end tell
    end try
    ' 2>/dev/null

    # 弹出 macOS 通知
    osascript -e 'display notification "Robinhood 雷达所有服务已停止，网页已关闭" with title "Robinhood 监控雷达" sound name "Glass"' 2>/dev/null
    echo "[+] 雷达服务已成功关闭。"
else
    # --- 启动全部服务并打开网页 ---
    echo "[*] 雷达服务未运行，正在初始化并启动所有关联服务..."
    cd "$PROJECT_DIR" || exit 1

    # 关键环境净化：清除系统本地代理干扰，确保 GMGN 官方爬虫与 RPC 节点 100% 畅通
    unset http_proxy HTTP_PROXY https_proxy HTTPS_PROXY all_proxy ALL_PROXY
    export no_proxy="localhost,127.0.0.1,gmgn.ai,*.gmgn.ai"
    export NO_PROXY="localhost,127.0.0.1,gmgn.ai,*.gmgn.ai"

    # 启动后台服务 (绑定 0.0.0.0:8888，开启自动热重载)
    nohup "$PROJECT_DIR/.venv/bin/python3" -m uvicorn backend.api:app --host 0.0.0.0 --port ${PORT} --reload > "$PROJECT_DIR/server.log" 2>&1 &
    
    # 等待端口就绪 (最多等待 8 秒)
    READY=0
    for i in {1..25}; do
        if lsof -i :${PORT} >/dev/null 2>&1; then
            READY=1
            break
        fi
        sleep 0.3
    done

    if [ $READY -eq 1 ]; then
        # 成功唤起默认浏览器打开 8888 端口
        open "$TARGET_URL"
        osascript -e 'display notification "Robinhood 雷达已启动，已为您自动打开 8888 端口雷达网页！" with title "Robinhood 监控雷达" sound name "Ping"' 2>/dev/null
        echo "[+] 所有服务已启动并在浏览器打开: $TARGET_URL"
    else
        osascript -e 'display alert "Robinhood 雷达启动超时，请查看 server.log 日志"' 2>/dev/null
        echo "[-] 服务启动超时，请检查日志 $PROJECT_DIR/server.log"
    fi
fi
