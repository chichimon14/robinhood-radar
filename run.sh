#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# 默认端口 8888，也可通过环境变量 PORT 或第一个参数指定，避免冲突
PORT="${1:-${PORT:-8888}}"

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "[*] 创建虚拟环境..."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install fastapi uvicorn httpx web3 pydantic
fi

echo "======================================================="
echo "   Robinhood Chain 内盘雷达与聪明钱包系统启动中..."
echo "   Chain ID: 4663 (Arbitrum Orbit / Robinhood L2)"
echo "   Web 访问地址: http://127.0.0.1:${PORT}"
echo "======================================================="

exec .venv/bin/python3 -m uvicorn backend.api:app --host 0.0.0.0 --port "${PORT}" --reload
