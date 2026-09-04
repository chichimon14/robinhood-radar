#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# 默认端口 8888，也可通过环境变量 PORT 或第一个参数指定，避免冲突
PORT="${1:-${PORT:-8888}}"

# 虚拟环境探测（支持项目内.venv以及Linux原生目录~/.venvs/robinhood-radar，兼容exFAT/NTFS等无软链接文件系统）
VENV_PATH=""
if [ -f ".venv/bin/python3" ]; then
    VENV_PATH=".venv"
elif [ -f "$HOME/.venvs/robinhood-radar/bin/python3" ]; then
    VENV_PATH="$HOME/.venvs/robinhood-radar"
else
    echo "[*] 正在准备 Python 虚拟环境..."
    # 尝试在当前目录创建，若失败（如exfat限制）则自动切换至用户主目录
    if python3 -m venv .venv 2>/dev/null; then
        VENV_PATH=".venv"
    else
        echo "[!] 当前磁盘文件系统限制符号链接，自动在用户主目录创建虚拟环境..."
        mkdir -p "$HOME/.venvs"
        python3 -m venv "$HOME/.venvs/robinhood-radar"
        VENV_PATH="$HOME/.venvs/robinhood-radar"
    fi
    "$VENV_PATH/bin/pip" install --upgrade pip
    "$VENV_PATH/bin/pip" install fastapi uvicorn httpx web3 pydantic
fi

echo "======================================================="
echo "   Robinhood Chain 内盘雷达与聪明钱包系统启动中..."
echo "   Chain ID: 4663 (Arbitrum Orbit / Robinhood L2)"
echo "   虚拟环境: ${VENV_PATH}"
echo "   Web 访问地址: http://127.0.0.1:${PORT}"
echo "======================================================="

exec "${VENV_PATH}/bin/python3" -m uvicorn backend.api:app --host 0.0.0.0 --port "${PORT}" --reload
