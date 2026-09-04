import os
from typing import List

# Robinhood Chain Configuration (Chain ID: 4663)
ROBINHOOD_CHAIN_ID = 4663

# Public RPC Endpoints
PUBLIC_RPCS: List[str] = [
    "https://rpc.mainnet.chain.robinhood.com",
    "https://robinhood-rpc.publicnode.com"
]

# Standard request headers for Robinhood RPC endpoints
RPC_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://robinscan.io",
    "Referer": "https://robinscan.io/"
}

# Average block time on Robinhood Chain is ~0.10s
BLOCKS_PER_SECOND = 9.8
POST_LAUNCH_WINDOW_SECONDS = 60 # 发射首分钟窗口
PRE_LAUNCH_MAX_BLOCKS = 3000   # 内盘前溯区块范围
