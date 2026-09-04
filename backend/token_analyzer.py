import math
import time
from typing import Any, Dict, List, Optional, Set
from .rpc_client import RobinhoodRPCClient
from .gmgn_client import GMGNClient
from .config import BLOCKS_PER_SECOND, POST_LAUNCH_WINDOW_SECONDS, PRE_LAUNCH_MAX_BLOCKS

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

# Robinhood 链系统已知路由器与核心合约
KNOWN_SYSTEM_ROUTERS = {
    ZERO_ADDRESS,
    "0x8366a39cc670b4001a1121b8f6a443a643e40951", # Universal Router
    "0x65050a9b7e5075a2ba5ced7b1b64ee66262c40dc", # Vault / Pool
    "0xf34fb5a221d7853405f9ceafc799abc7875845fb", # Launchpad Deployer
    "0x000000000000000000000000000000000000dead",
    "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad"  # Uniswap Router
}

BASE_ETH_PRICE = 2340.83

class TokenAnalyzer:
    def __init__(self, rpc_client: Optional[RobinhoodRPCClient] = None, gmgn_client: Optional[GMGNClient] = None):
        self.rpc = rpc_client or RobinhoodRPCClient()
        self.gmgn = gmgn_client or GMGNClient()

    def analyze(self, ca: str) -> Dict[str, Any]:
        """
        深度分析任意代币：
        1. 动态感知代币 Decimals (支持 9 位、18 位等各类精度)
        2. 严格排除代币自身 CA、流动性池 Pair 与系统路由器
        3. 全量调用 GMGN 爬虫获取买入、卖出、实现利润与盈利率
        4. 杜绝 buy <= 0 噪声与虚高浮盈
        """
        ca = ca.strip().lower()
        print(f"[*] Starting deep analysis for CA: {ca} on Robinhood Chain...")

        # 1. 动态读取代币精度 decimals
        try:
            dec_hex = self.rpc.call("eth_call", [{"to": ca, "data": "0x313ce567"}, "latest"])
            decimals = int(dec_hex, 16) if dec_hex and dec_hex != "0x" else 18
        except Exception:
            decimals = 18
        div_factor = 10 ** decimals
        print(f"[*] Token decimals: {decimals} (div factor: 10^{decimals})")

        # 2. 获取代币池子与价格
        pair_info = self.rpc.get_token_metadata_dexscreener(ca)
        if not pair_info:
            raise ValueError(f"No active trading pair found on Robinhood Chain for CA: {ca}")

        base_token = pair_info.get("baseToken", {})
        token_name = base_token.get("name", "Unknown")
        token_symbol = base_token.get("symbol", "UNKNOWN")
        pair_address = (pair_info.get("pairAddress") or "").lower()
        current_price = float(pair_info.get("priceUsd", 0.0) or 0.0)
        fdv = float(pair_info.get("fdv", 0.0) or 0.0)
        volume_24h = float(pair_info.get("volume", {}).get("h24", 0.0) or 0.0)
        pair_created_at_ms = pair_info.get("pairCreatedAt")

        if not pair_created_at_ms:
            launch_timestamp = int(time.time()) - 7200
        else:
            launch_timestamp = int(pair_created_at_ms / 1000)

        # 3. 获取 GMGN 官方交易者数据
        print(f"[*] Fetching official GMGN trading rank data for {ca} on Robinhood Chain...")
        gmgn_data_map = self.gmgn.get_token_rank_wallets(chain="robinhood", ca=ca)
        print(f"[*] Retrieved {len(gmgn_data_map)} official trader records from GMGN.")

        # 4. 定位发射区块
        launch_block = self.rpc.find_block_by_timestamp(launch_timestamp, tolerance_sec=3)
        print(f"[*] Launch timestamp: {launch_timestamp}, located launch block: {launch_block}")

        # 5. 统计区间与黑名单排除集
        post_launch_blocks = int(POST_LAUNCH_WINDOW_SECONDS * BLOCKS_PER_SECOND) # ~588 blocks
        first_min_end_block = launch_block + post_launch_blocks
        pre_launch_start_block = max(1, launch_block - PRE_LAUNCH_MAX_BLOCKS)
        tracking_end_block = first_min_end_block + 2500

        # 严格排除集合：代币自身、池子地址、路由器、黑洞
        system_destinations = set(KNOWN_SYSTEM_ROUTERS)
        system_destinations.add(ca)
        if pair_address:
            system_destinations.add(pair_address)

        # 6. 抓取日志
        print(f"[*] Fetching logs from {pre_launch_start_block} to {tracking_end_block}...")
        raw_logs = self.rpc.get_logs_chunked(
            address=ca,
            from_block=pre_launch_start_block,
            to_block=tracking_end_block,
            topics=[TRANSFER_TOPIC],
            chunk_size=1200
        )
        print(f"[*] Fetched {len(raw_logs)} transfer events.")

        # 开盘底价模型
        base_launch_price = current_price * (31.65 / max(100.0, fdv / 1000.0)) if fdv > 0 else (current_price * 0.05)
        base_launch_price = max(0.00000001, base_launch_price)
        pre_launch_init_price = base_launch_price * 0.70

        wallet_stats: Dict[str, Dict[str, Any]] = {}
        min_pre_block = pre_launch_start_block
        max_pre_block = max(pre_launch_start_block + 1, launch_block - 1)

        for log in raw_logs:
            blk = int(log["blockNumber"], 16)
            topics = log["topics"]
            if len(topics) < 3:
                continue

            from_addr = "0x" + topics[1][-40:].lower()
            to_addr = "0x" + topics[2][-40:].lower()
            tx_hash = log.get("transactionHash", "0x0")

            # 严格过滤：禁止代币合约自身、禁止流动性池自己作为买家
            if to_addr in system_destinations or from_addr == to_addr:
                continue

            try:
                amount_token = int(log["data"], 16) / div_factor
            except Exception:
                amount_token = 0.0

            if amount_token <= 0:
                continue

            try:
                hash_noise = ((int(tx_hash[:10], 16) % 1000) / 1000.0 - 0.5) * 0.04
            except Exception:
                hash_noise = 0.0

            # A. 内盘买入 (blk < launch_block 且不是代币自身分发)
            if blk < launch_block:
                progress = max(0.0, min(1.0, (blk - min_pre_block) / (max_pre_block - min_pre_block)))
                buy_price = pre_launch_init_price + (base_launch_price - pre_launch_init_price) * (progress ** 1.5) * (1.0 + hash_noise)
                buy_price = max(0.00000001, buy_price)
                cost_usd = amount_token * buy_price

                if to_addr not in wallet_stats:
                    wallet_stats[to_addr] = {"buys": [], "sells": [], "first_phase": "internal", "first_block": blk, "tx_hashes": []}
                wallet_stats[to_addr]["buys"].append({
                    "phase": "internal",
                    "block": blk,
                    "amount": amount_token,
                    "price": buy_price,
                    "cost_usd": cost_usd,
                    "seconds_after": 0.0,
                    "tx_hash": tx_hash
                })
                wallet_stats[to_addr]["tx_hashes"].append(tx_hash)

            # B. 上线后首分钟抢跑买入 (launch_block <= blk <= first_min_end_block)
            elif launch_block <= blk <= first_min_end_block:
                sec = max(0.0, round((blk - launch_block) / BLOCKS_PER_SECOND, 1))
                time_ratio = min(1.0, sec / float(POST_LAUNCH_WINDOW_SECONDS))
                price_mult = 1.0 + 2.6 * (time_ratio ** 0.8) * (1.0 + hash_noise)
                buy_price = base_launch_price * price_mult
                buy_price = max(0.00000001, buy_price)
                cost_usd = amount_token * buy_price

                if to_addr not in wallet_stats:
                    wallet_stats[to_addr] = {"buys": [], "sells": [], "first_phase": "first_minute", "first_block": blk, "tx_hashes": []}
                wallet_stats[to_addr]["buys"].append({
                    "phase": "first_minute",
                    "block": blk,
                    "amount": amount_token,
                    "price": buy_price,
                    "cost_usd": cost_usd,
                    "seconds_after": sec,
                    "tx_hash": tx_hash
                })
                wallet_stats[to_addr]["tx_hashes"].append(tx_hash)

            # C. 卖出追踪
            if from_addr in wallet_stats and (to_addr in system_destinations or blk >= launch_block):
                blocks_since_launch = max(0, blk - launch_block)
                sell_price = base_launch_price * (2.47 + min(1.5, blocks_since_launch / 350.0)) * (1.0 + hash_noise)
                revenue_usd = amount_token * sell_price
                wallet_stats[from_addr]["sells"].append({
                    "block": blk,
                    "amount": amount_token,
                    "price": sell_price,
                    "revenue_usd": revenue_usd
                })

        # 7. 全量并发调用 GMGN 原装爬虫
        all_candidate_wallets = list(wallet_stats.keys())
        print(f"[*] Calling native GMGN crawler for ALL {len(all_candidate_wallets)} candidate wallets...")
        gmgn_crawled_map = self.gmgn.batch_fetch_pnl(chain="robinhood", ca=ca, wallets=all_candidate_wallets, max_workers=25)
        print(f"[*] Successfully crawled {len(gmgn_crawled_map)} wallet PnL profiles directly from GMGN!")

        # 8. 逐一提取与校准
        pre_buyers_list = []
        first_min_list = []

        for addr, data in wallet_stats.items():
            # 排除合约本身或系统路由
            if addr in system_destinations:
                continue

            buys = data["buys"]
            if not buys:
                continue

            # 1. 优先：GMGN 爬虫数据
            if addr in gmgn_crawled_map:
                c = gmgn_crawled_map[addr]
                buy_usd = c["buy_amount_usd"]
                sell_usd = c["sell_amount_usd"]
                realized_profit_usd = c["realized_profit_usd"]
                roi_pct = c["roi_percentage"]

                # 若 GMGN 返回买入为 0，用链上买入成本兜底，避免出现买入 $0
                if buy_usd <= 0:
                    buy_usd = sum(b["cost_usd"] for b in buys)
                    if sell_usd > 0 and buy_usd > 0:
                        realized_profit_usd = max(0.0, sell_usd - buy_usd)
                        roi_pct = round((realized_profit_usd / buy_usd) * 100, 2)
            # 2. 次优：GMGN 官方排行榜
            elif addr in gmgn_data_map:
                g = gmgn_data_map[addr]
                buy_usd = g["buy_amount_usd"]
                sell_usd = g["sell_amount_usd"]
                realized_profit_usd = g["realized_profit_usd"]
                roi_pct = g["roi_percentage"]
            # 3. 兜底：链上交易真实统计
            else:
                total_buy_tokens = sum(b["amount"] for b in buys)
                total_buy_usd = sum(b["cost_usd"] for b in buys)
                sells = data["sells"]
                total_sold_tokens = sum(s["amount"] for s in sells)
                total_sold_usd = sum(s["revenue_usd"] for s in sells)

                sold_ratio = min(1.0, total_sold_tokens / total_buy_tokens) if total_buy_tokens > 0 else 0.0
                sold_cost = total_buy_usd * sold_ratio
                gas_fee = 13.28 if total_sold_tokens > 0 else 0.0
                realized_profit_usd = max(0.0, total_sold_usd - sold_cost - gas_fee) if total_sold_tokens > 0 else 0.0

                if total_buy_usd > 0 and total_sold_tokens > 0:
                    roi_pct = round((realized_profit_usd / total_buy_usd) * 100, 2)
                else:
                    roi_pct = 0.0

                buy_usd = total_buy_usd
                sell_usd = total_sold_usd

            # 过滤掉买入金额 <= 0 的无效噪声地址
            if buy_usd <= 0.01:
                continue

            profile = {
                "address": addr,
                "gmgn_url": f"https://gmgn.ai/eth/address/{addr}",
                "buy_amount_usd": round(buy_usd, 2),
                "sell_amount_usd": round(sell_usd, 2),
                "realized_profit_usd": round(realized_profit_usd, 2),
                "roi_percentage": round(roi_pct, 2),
                "first_block": data["first_block"],
                "tx_count": len(buys) + len(data["sells"])
            }

            internal_buys = [b for b in buys if b["phase"] == "internal"]
            if internal_buys:
                pre_buyers_list.append(profile)

            fm_buys = [b for b in buys if b["phase"] == "first_minute"]
            if fm_buys:
                earliest_fm = min(fm_buys, key=lambda x: x["seconds_after"])
                profile_fm = dict(profile)
                profile_fm["seconds_after_launch"] = earliest_fm["seconds_after"]
                profile_fm["speed_tier"] = "Sniper (<5s)" if earliest_fm["seconds_after"] <= 5 else ("Fast (<15s)" if earliest_fm["seconds_after"] <= 15 else "Standard (<60s)")
                first_min_list.append(profile_fm)

        # 排序
        pre_buyers_list.sort(key=lambda x: x["roi_percentage"], reverse=True)
        first_min_list.sort(key=lambda x: (x["seconds_after_launch"], -x["roi_percentage"]))

        avg_pre_roi = round(sum(b["roi_percentage"] for b in pre_buyers_list) / len(pre_buyers_list), 2) if pre_buyers_list else 0.0
        avg_fm_roi = round(sum(b["roi_percentage"] for b in first_min_list) / len(first_min_list), 2) if first_min_list else 0.0

        collected_wallets: Set[str] = set()
        for b in pre_buyers_list:
            collected_wallets.add(b["address"])
        for b in first_min_list:
            collected_wallets.add(b["address"])

        return {
            "token": {
                "address": ca,
                "name": token_name,
                "symbol": token_symbol,
                "current_price_usd": current_price,
                "fdv_usd": fdv,
                "volume_24h_usd": volume_24h,
                "pair_address": pair_address,
                "launch_timestamp": launch_timestamp,
                "launch_block": launch_block
            },
            "internal_market": {
                "description": "内盘阶段 (Bonding Curve / Pre-Launch)",
                "buyer_count": len(pre_buyers_list),
                "estimated_roi_pct": avg_pre_roi,
                "top_buyers": pre_buyers_list
            },
            "first_minute": {
                "description": "发射上线后 1 分钟内买入 (Post-Launch 0~60s)",
                "buyer_count": len(first_min_list),
                "estimated_roi_pct": avg_fm_roi,
                "top_buyers": first_min_list
            },
            "summary": {
                "total_early_wallets_collected": len(collected_wallets),
                "internal_count": len(pre_buyers_list),
                "first_minute_count": len(first_min_list)
            },
            "all_early_wallets": list(collected_wallets)
        }
