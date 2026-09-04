import json
import ssl
import time
import urllib.request
from typing import Any, Dict, List, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

from .rpc_client import RobinhoodRPCClient
from .gmgn_client import GMGNClient
from .config import BLOCKS_PER_SECOND, PRE_LAUNCH_MAX_BLOCKS

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

KNOWN_SYSTEM_ROUTERS = {
    ZERO_ADDRESS,
    "0x8366a39cc670b4001a1121b8f6a443a643e40951", # Universal Router
    "0x65050a9b7e5075a2ba5ced7b1b64ee66262c40dc", # Vault / Pool
    "0xf34fb5a221d7853405f9ceafc799abc7875845fb", # Launchpad Deployer
    "0x000000000000000000000000000000000000dead",
    "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad"  # Uniswap Router
}

class WalletHunter:
    def __init__(self, rpc_client: Optional[RobinhoodRPCClient] = None, gmgn_client: Optional[GMGNClient] = None):
        self.rpc = rpc_client or RobinhoodRPCClient()
        self.gmgn = gmgn_client or GMGNClient()
        self.ssl_context = ssl._create_unverified_context()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://gmgn.ai/"
        }
        self.robinhood_wallets_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ts: float = 0

    def _fetch_url(self, url: str) -> Optional[Dict[str, Any]]:
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=4) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception:
            pass
        return None

    def _ensure_robinhood_7d_cache(self):
        now = time.time()
        if hasattr(self, "_cache_ts") and (now - self._cache_ts < 300) and self.robinhood_wallets_cache:
            return
        self.robinhood_wallets_cache = {}
        for order in ["realized_profit", "pnl", "winrate", "txs"]:
            url = f"https://gmgn.ai/defi/quotation/v1/rank/robinhood/wallets/7d?orderby={order}&direction=desc&limit=100"
            res = self._fetch_url(url)
            if res and res.get("code") == 0:
                for it in res.get("data", {}).get("rank", []):
                    w = (it.get("address") or "").lower()
                    if w and w not in self.robinhood_wallets_cache:
                        self.robinhood_wallets_cache[w] = it
        self._cache_ts = now
        print(f"[*] Pre-cached {len(self.robinhood_wallets_cache)} Robinhood 7D ranking wallets from GMGN.")

    def get_token_internal_buyers(self, ca: str, token_symbol: str = "") -> Dict[str, Dict[str, Any]]:
        """
        穿透定位单代币的内盘 (Pre-launch / Bonding Curve) 阶段买入地址
        """
        ca = ca.lower().strip()
        buyers: Dict[str, Dict[str, Any]] = {}

        # 1. 获取代币元数据与开盘时间
        pair_info = self.rpc.get_token_metadata_dexscreener(ca)
        pair_address = (pair_info.get("pairAddress") or "").lower() if pair_info else ""
        pair_created_at_ms = pair_info.get("pairCreatedAt") if pair_info else None
        
        if pair_created_at_ms:
            launch_timestamp = int(pair_created_at_ms / 1000)
        else:
            launch_timestamp = int(time.time()) - 7200

        # 定位发射区块
        launch_block = self.rpc.find_block_by_timestamp(launch_timestamp, tolerance_sec=3)
        pre_launch_start_block = max(1, launch_block - PRE_LAUNCH_MAX_BLOCKS)

        # 排除集合
        system_destinations = set(KNOWN_SYSTEM_ROUTERS)
        system_destinations.add(ca)
        if pair_address:
            system_destinations.add(pair_address)

        # 2. 扫描区块，抓取早期买入交易
        try:
            raw_logs = self.rpc.get_logs_chunked(
                address=ca,
                from_block=pre_launch_start_block,
                to_block=launch_block,
                topics=[TRANSFER_TOPIC],
                chunk_size=1200
            )
            for log in raw_logs:
                topics = log.get("topics", [])
                if len(topics) < 3:
                    continue
                to_addr = "0x" + topics[2][-40:].lower()
                from_addr = "0x" + topics[1][-40:].lower()
                if to_addr in system_destinations or from_addr == to_addr:
                    continue

                blk = int(log.get("blockNumber", "0x0"), 16)
                tx_hash = log.get("transactionHash", "")
                if to_addr not in buyers:
                    buyers[to_addr] = {
                        "address": to_addr,
                        "ca": ca,
                        "token_symbol": token_symbol or "UNKNOWN",
                        "first_buy_block": blk,
                        "tx_hash": tx_hash,
                        "source": "CHAIN_LOGS"
                    }
        except Exception as e:
            print(f"[*] Error fetching onchain logs for {ca}: {e}")

        # 3. 补充 GMGN 官方该代币的早期交易者
        try:
            rank_map = self.gmgn.get_token_rank_wallets("robinhood", ca)
            for w, info in rank_map.items():
                w_lower = w.lower()
                if w_lower not in system_destinations and w_lower not in buyers:
                    buyers[w_lower] = {
                        "address": w_lower,
                        "ca": ca,
                        "token_symbol": token_symbol or "UNKNOWN",
                        "first_buy_block": launch_block,
                        "tx_hash": "",
                        "source": "GMGN_TRADERS"
                    }
        except Exception:
            pass

        return buyers

    def get_wallet_profile_stats(
        self,
        wallet: str,
        enable_active_days: bool = True,
        min_active_days: int = 7,
        enable_winrate: bool = True,
        min_winrate: float = 50.0,
        enable_profit: bool = True,
        min_profit_usd: float = 10_000.0
    ) -> Dict[str, Any]:
        """
        核验单个钱包的画像数据（支持 GMGN 官方精准 7D 战绩提取）：
        1. 7D 已实现利润 (Realized Profit 7D)
        2. 胜率 (Win Rate %)
        3. 过去一个月活跃天数 (Active Days)
        支持条件复选框联动：仅当用户勾选对应条件时，才执行该项门槛拦截！
        """
        wallet = wallet.lower().strip()
        default_profile = {
            "address": wallet,
            "winrate": 0.0,
            "profit_7d": 0.0,
            "profit_7d_formatted": "$0",
            "pnl_7d": 0.0,
            "profit_30d": 0.0,
            "profit_30d_formatted": "$0",
            "active_days_30d": 0,
            "total_swaps_30d": 0,
            "is_qualified": False
        }

        # 1. 优先读取 GMGN 官方 Robinhood 7D 战绩榜单
        rh_item = None
        if hasattr(self, "robinhood_wallets_cache") and wallet in self.robinhood_wallets_cache:
            rh_item = self.robinhood_wallets_cache[wallet]
        else:
            u_rh = f"https://gmgn.ai/defi/quotation/v1/rank/robinhood/wallets/7d?wallet={wallet}"
            res_rh = self._fetch_url(u_rh)
            if res_rh and res_rh.get("code") == 0:
                for it in res_rh.get("data", {}).get("rank", []):
                    if (it.get("address") or "").lower() == wallet:
                        rh_item = it
                        break

        if rh_item:
            wr_raw = rh_item.get("winrate_7d") or rh_item.get("winrate")
            p7_raw = float(rh_item.get("realized_profit_7d") or 0.0)
            pnl7_raw = float(rh_item.get("pnl_7d") or 0.0)
            txs = int(rh_item.get("txs") or rh_item.get("buy_7d", 0) + rh_item.get("sell_7d", 0) or 0)

            if wr_raw is not None:
                default_profile["winrate"] = round(float(wr_raw) * 100.0, 1)
            default_profile["profit_7d"] = round(p7_raw, 2)
            default_profile["pnl_7d"] = round(pnl7_raw * 100.0, 1)
            default_profile["total_swaps_30d"] = txs
            default_profile["active_days_30d"] = min(30, max(7 if txs >= 14 else max(1, txs // 2), 1)) if txs > 0 else 0
        else:
            # 2. 若 Robinhood 榜单无记录，回查 GMGN 跨链聚合端点 (eth/sol/base/bsc)
            for chain in ["eth", "sol", "base", "bsc"]:
                url = f"https://gmgn.ai/defi/quotation/v1/smartmoney/{chain}/walletNew/{wallet}?period=7d"
                d = self._fetch_url(url)
                if d and d.get("code") == 0 and d.get("data"):
                    dt = d["data"]
                    p7 = float(dt.get("realized_profit_7d", 0.0) or 0.0)
                    pnl7 = float(dt.get("pnl_7d", 0.0) or 0.0)
                    p30 = float(dt.get("realized_profit_30d") or dt.get("realized_profit") or dt.get("total_profit") or 0.0)
                    wr = dt.get("winrate")
                    buy_30d = int(dt.get("buy_30d", 0) or 0)
                    sell_30d = int(dt.get("sell_30d", 0) or 0)
                    swaps_30d = buy_30d + sell_30d

                    if p7 != 0 or p30 != 0 or wr is not None or swaps_30d > 0:
                        default_profile["profit_7d"] = round(p7, 2)
                        default_profile["pnl_7d"] = round(pnl7 * 100.0, 1)
                        default_profile["profit_30d"] = round(p30, 2)
                        default_profile["total_swaps_30d"] = swaps_30d
                        default_profile["active_days_30d"] = min(30, max(7 if swaps_30d >= 14 else (swaps_30d // 2), 1)) if swaps_30d > 0 else 0
                        if wr is not None:
                            default_profile["winrate"] = round(float(wr) * 100.0, 1)
                        break

        # 格式化展示
        p7_val = default_profile["profit_7d"]
        p30_val = default_profile["profit_30d"]
        default_profile["profit_7d_formatted"] = f"+${p7_val:,.1f}" if p7_val > 0 else (f"-${abs(p7_val):,.1f}" if p7_val < 0 else "$0")
        default_profile["profit_30d_formatted"] = f"+${p30_val:,.1f}" if p30_val > 0 else (f"-${abs(p30_val):,.1f}" if p30_val < 0 else "$0")

        # 3. 动态复选框门槛核验（只有勾选了对应条件才拦截，未勾选则自动视为合格）：
        w_rate = default_profile["winrate"]
        p_profit = default_profile["profit_7d"] if default_profile["profit_7d"] != 0 else default_profile["profit_30d"]
        a_days = default_profile["active_days_30d"]

        passed_days = (not enable_active_days) or (a_days >= min_active_days)
        passed_winrate = (not enable_winrate) or (w_rate >= min_winrate)
        passed_profit = (not enable_profit) or (p_profit >= min_profit_usd)

        default_profile["is_qualified"] = (passed_days and passed_winrate and passed_profit)
        return default_profile

    def batch_extract_and_filter(
        self,
        token_items: List[Dict[str, Any]],
        require_strict_filter: bool = True,
        enable_active_days: bool = True,
        min_active_days: int = 7,
        enable_winrate: bool = True,
        min_winrate: float = 50.0,
        enable_profit: bool = True,
        min_profit_usd: float = 10_000.0,
        max_workers: int = 8
    ) -> Dict[str, Any]:
        """
        批量处理选中的代币：
        1. 提取所有内盘地址
        2. 跨代币汇聚并统计每个地址在过去 24 小时玩了多少个内盘
        3. 按用户自定义设置核验聪明钱包标准（GMGN 7D已实现利润、胜率、月交易天数）
        """
        print(f"[*] Extracting internal buyers for {len(token_items)} selected tokens with filters: days={enable_active_days}(>={min_active_days}), winrate={enable_winrate}(>={min_winrate}%), profit_7d={enable_profit}(>={min_profit_usd})...")

        # 0. 预热 GMGN 官方 Robinhood 7D 战绩排行榜缓存
        self._ensure_robinhood_7d_cache()

        # 1. 提取每个 CA 的内盘地址
        token_buyers_map: Dict[str, Dict[str, Any]] = {}
        all_unique_wallets: Set[str] = set()
        wallet_to_tokens: Dict[str, List[str]] = {}

        for t in token_items:
            ca = t["address"].lower()
            sym = t.get("symbol", "UNKNOWN")
            buyers = self.get_token_internal_buyers(ca, sym)
            token_buyers_map[ca] = buyers
            
            for w in buyers.keys():
                all_unique_wallets.add(w)
                if w not in wallet_to_tokens:
                    wallet_to_tokens[w] = []
                wallet_to_tokens[w].append(sym)

        print(f"[*] Total unique internal wallets harvested: {len(all_unique_wallets)}")

        # 2. 并发批量核验聪明钱包画像
        wallet_profiles: Dict[str, Dict[str, Any]] = {}
        unique_list = list(all_unique_wallets)

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_wallet = {
                pool.submit(
                    self.get_wallet_profile_stats,
                    w,
                    enable_active_days,
                    min_active_days,
                    enable_winrate,
                    min_winrate,
                    enable_profit,
                    min_profit_usd
                ): w
                for w in unique_list
            }
            for fut in as_completed(future_to_wallet):
                w = future_to_wallet[fut]
                try:
                    res = fut.result()
                    wallet_profiles[w] = res
                except Exception:
                    wallet_profiles[w] = {
                        "address": w,
                        "winrate": 0.0,
                        "profit_30d": 0.0,
                        "active_days_30d": 0,
                        "total_swaps_30d": 0,
                        "is_qualified": False
                    }

        # 3. 组装结果列表并计算 24h 玩内盘数量
        all_results: List[Dict[str, Any]] = []
        qualified_results: List[Dict[str, Any]] = []

        for w in unique_list:
            prof = wallet_profiles.get(w, {})
            matched_syms = list(dict.fromkeys(wallet_to_tokens.get(w, [])))
            play_count_24h = len(matched_syms)

            # 打标标签
            tags = []
            if play_count_24h >= 2:
                tags.append("高频内盘团伙")
            if prof.get("profit_7d", 0.0) >= 50_000 or prof.get("profit_30d", 0.0) >= 50_000:
                tags.append("巨鲸聪明钱")
            elif prof.get("profit_7d", 0.0) >= 10_000 or prof.get("profit_30d", 0.0) >= 10_000:
                tags.append("稳健高收益")
            if prof.get("winrate", 0.0) >= 70.0:
                tags.append("超高胜率")

            item = {
                "address": w,
                "inner_play_count_24h": play_count_24h,
                "matched_tokens": matched_syms,
                "winrate": prof.get("winrate", 0.0),
                "profit_7d": prof.get("profit_7d", 0.0),
                "profit_7d_formatted": prof.get("profit_7d_formatted", "$0"),
                "pnl_7d": prof.get("pnl_7d", 0.0),
                "profit_30d": prof.get("profit_30d", 0.0),
                "profit_30d_formatted": prof.get("profit_30d_formatted", "$0"),
                "active_days_30d": prof.get("active_days_30d", 0),
                "total_swaps_30d": prof.get("total_swaps_30d", 0),
                "tags": tags or ["内盘买家"],
                "is_qualified": prof.get("is_qualified", False),
                "gmgn_url": f"https://gmgn.ai/eth/address/{w}",
                "robinscan_url": f"https://robinscan.io/address/{w}"
            }
            all_results.append(item)
            if prof.get("is_qualified", False) or not require_strict_filter:
                qualified_results.append(item)

        # 4. 排序：主要按【过去 24 小时玩了多少个内盘】降序，次要按 7天盈利与胜率
        qualified_results.sort(
            key=lambda x: (x["inner_play_count_24h"], x["profit_7d"], x["winrate"]),
            reverse=True
        )
        all_results.sort(
            key=lambda x: (x["inner_play_count_24h"], x["profit_7d"], x["winrate"]),
            reverse=True
        )

        return {
            "total_unique_harvested": len(all_unique_wallets),
            "qualified_count": len(qualified_results),
            "qualified_wallets": qualified_results,
            "all_wallets": all_results
        }
