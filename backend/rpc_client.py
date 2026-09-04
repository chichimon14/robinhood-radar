import json
import ssl
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from .config import PUBLIC_RPCS, RPC_HEADERS, BLOCKS_PER_SECOND

class RobinhoodRPCClient:
    def __init__(self, rpcs: Optional[List[str]] = None):
        self.rpcs = rpcs or PUBLIC_RPCS
        self.ssl_context = ssl._create_unverified_context()
        self.active_rpc_idx = 0

    def get_active_rpc(self) -> str:
        return self.rpcs[self.active_rpc_idx]

    def _rotate_rpc(self):
        self.active_rpc_idx = (self.active_rpc_idx + 1) % len(self.rpcs)

    def call(self, method: str, params: list, retries: int = 3) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000) % 1000000,
            "method": method,
            "params": params
        }
        data = json.dumps(payload).encode("utf-8")

        for attempt in range(retries):
            rpc_url = self.get_active_rpc()
            try:
                req = urllib.request.Request(rpc_url, data=data, headers=RPC_HEADERS)
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=8) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    if "error" in result:
                        raise Exception(f"RPC Error: {result['error']}")
                    return result.get("result")
            except Exception as e:
                self._rotate_rpc()
                if attempt == retries - 1:
                    raise Exception(f"Failed RPC call {method} after {retries} retries: {e}")
                time.sleep(0.5)

    def get_latest_block(self) -> Tuple[int, int]:
        """获取最新区块高度和时间戳"""
        res = self.call("eth_getBlockByNumber", ["latest", False])
        return int(res["number"], 16), int(res["timestamp"], 16)

    def get_block_by_number(self, block_num: int) -> Dict[str, Any]:
        """根据区块高度获取区块信息"""
        return self.call("eth_getBlockByNumber", [hex(block_num), False])

    def find_block_by_timestamp(self, target_ts: int, tolerance_sec: int = 2) -> int:
        """二分查找接近目标时间戳的区块高度"""
        latest_num, latest_ts = self.get_latest_block()
        if target_ts >= latest_ts:
            return latest_num

        # 估算起点
        diff_sec = latest_ts - target_ts
        est_blocks_ago = int(diff_sec * BLOCKS_PER_SECOND)
        low = max(1, latest_num - int(est_blocks_ago * 1.5) - 20000)
        high = latest_num

        best_block = low
        best_diff = float("inf")

        for _ in range(25):
            if low > high:
                break
            mid = (low + high) // 2
            try:
                block_info = self.get_block_by_number(mid)
                if not block_info:
                    high = mid - 1
                    continue
                block_ts = int(block_info["timestamp"], 16)
                diff = abs(block_ts - target_ts)

                if diff < best_diff:
                    best_diff = diff
                    best_block = mid

                if diff <= tolerance_sec:
                    return mid

                if block_ts < target_ts:
                    low = mid + 1
                else:
                    high = mid - 1
            except Exception:
                mid = (low + high) // 2
                low = mid + 1

        return best_block

    _metadata_cache: Dict[str, Any] = {}

    def get_token_metadata_dexscreener(self, ca: str) -> Optional[Dict[str, Any]]:
        """从 DexScreener 获取 Robinhood 链上的代币池子和元数据，支持重试与内存缓存"""
        ca_lower = ca.lower()
        if ca_lower in self._metadata_cache:
            return self._metadata_cache[ca_lower]

        url = f"https://api.dexscreener.com/latest/dex/tokens/{ca}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=12) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    pairs = [p for p in data.get("pairs", []) if p.get("chainId") == "robinhood"]
                    if not pairs:
                        pairs = data.get("pairs", [])
                    if pairs:
                        pairs.sort(key=lambda x: float(x.get("volume", {}).get("h24", 0) or 0), reverse=True)
                        self._metadata_cache[ca_lower] = pairs[0]
                        return pairs[0]
            except Exception as e:
                if attempt == 2:
                    print(f"Dexscreener lookup error for {ca}: {e}")
                time.sleep(0.5)
        return None

    def get_logs_chunked(self, address: str, from_block: int, to_block: int, topics: List[str], chunk_size: int = 1500) -> List[Dict[str, Any]]:
        """分段获取日志，避免公用 RPC 请求过载"""
        all_logs = []
        cur_from = from_block
        while cur_from <= to_block:
            cur_to = min(cur_from + chunk_size - 1, to_block)
            params = [{
                "address": address,
                "fromBlock": hex(cur_from),
                "toBlock": hex(cur_to),
                "topics": topics
            }]
            try:
                logs = self.call("eth_getLogs", params)
                if logs:
                    all_logs.extend(logs)
            except Exception as e:
                # 出现限制则缩小分块
                if chunk_size > 300:
                    chunk_size = chunk_size // 2
                    continue
                else:
                    print(f"Error fetching logs from {cur_from} to {cur_to}: {e}")
            cur_from = cur_to + 1
        return all_logs
