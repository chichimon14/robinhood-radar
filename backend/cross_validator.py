import time
from typing import Any, Dict, List, Set, Optional
from .token_analyzer import TokenAnalyzer

class CrossValidator:
    def __init__(self, analyzer: TokenAnalyzer = None):
        self.analyzer = analyzer or TokenAnalyzer()

    def validate_multiple_tokens(self, cas: List[str], min_overlap: int = 2, mode: str = "combined") -> Dict[str, Any]:
        """
        对多个热门 CA 进行多维交叉验证：
        mode: 
          - "internal": 只分析各代币内盘阶段买入地址进行碰撞
          - "external": 只分析各代币外盘上线后首分钟买入地址进行碰撞
          - "combined": 内外盘地址合并进行碰撞 (默认)
        """
        clean_cas = list(dict.fromkeys([c.strip().lower() for c in cas if c.strip()]))
        if len(clean_cas) < 2:
            raise ValueError("至少需要输入 2 个不同的 CA 进行交叉验证比对")

        mode = (mode or "combined").lower()
        if mode not in ["internal", "external", "combined"]:
            mode = "combined"

        mode_name_map = {
            "internal": "内盘碰撞 (仅内盘潜伏地址)",
            "external": "外盘碰撞 (仅上线首分钟抢跑地址)",
            "combined": "综合碰撞 (内外盘地址合并)"
        }

        print(f"[*] Starting cross-validation for {len(clean_cas)} tokens under [{mode_name_map[mode]}]: {clean_cas}")

        token_results = {}
        wallet_occurrences: Dict[str, Dict[str, Any]] = {}

        for ca in clean_cas:
            try:
                res = self.analyzer.analyze(ca)
                token_symbol = res["token"]["symbol"]
                token_name = res["token"]["name"]
                token_results[ca] = res

                # 1. 记录内盘地址 (在 internal 或 combined 模式下生效)
                if mode in ["internal", "combined"]:
                    for buyer in res["internal_market"]["top_buyers"]:
                        w = buyer["address"]
                        if w not in wallet_occurrences:
                            wallet_occurrences[w] = {"tokens": {}, "token_symbols": set(), "internal_hits": 0, "sniper_hits": 0}
                        wallet_occurrences[w]["tokens"][ca] = {
                            "phase": "internal",
                            "symbol": token_symbol,
                            "roi": buyer["roi_percentage"],
                            "buy_usd": buyer["buy_amount_usd"],
                            "sell_usd": buyer["sell_amount_usd"],
                            "profit_usd": buyer["realized_profit_usd"],
                            "entry": "Bonding Curve"
                        }
                        wallet_occurrences[w]["token_symbols"].add(token_symbol)
                        wallet_occurrences[w]["internal_hits"] += 1

                # 2. 记录发射首分钟外盘地址 (在 external 或 combined 模式下生效)
                if mode in ["external", "combined"]:
                    for buyer in res["first_minute"]["top_buyers"]:
                        w = buyer["address"]
                        if w not in wallet_occurrences:
                            wallet_occurrences[w] = {"tokens": {}, "token_symbols": set(), "internal_hits": 0, "sniper_hits": 0}
                        
                        # 若在 combined 模式下且该地址在内盘已有记录，合并标记
                        if ca not in wallet_occurrences[w]["tokens"]:
                            wallet_occurrences[w]["tokens"][ca] = {
                                "phase": "first_minute",
                                "symbol": token_symbol,
                                "roi": buyer["roi_percentage"],
                                "buy_usd": buyer["buy_amount_usd"],
                                "sell_usd": buyer["sell_amount_usd"],
                                "profit_usd": buyer["realized_profit_usd"],
                                "entry": f"+{buyer.get('seconds_after_launch', 0)}s"
                            }
                        wallet_occurrences[w]["token_symbols"].add(token_symbol)
                        if buyer.get("seconds_after_launch", 999) <= 5:
                            wallet_occurrences[w]["sniper_hits"] += 1

            except Exception as e:
                print(f"[!] Error analyzing token {ca}: {e}")
                token_results[ca] = {"error": str(e)}

        # 3. 过滤与标记满足重合条件的地址
        matched_wallets = []
        cabal_wallets = []
        smart_money_wallets = []
        sniper_wallets = []

        for wallet, info in wallet_occurrences.items():
            participated_count = len(info["tokens"])
            if participated_count >= min_overlap:
                token_list = list(info["token_symbols"])
                rois = [t["roi"] for t in info["tokens"].values()]
                avg_roi = round(sum(rois) / len(rois), 2) if rois else 0.0
                win_count = sum(1 for r in rois if r > 0)
                win_rate = round((win_count / participated_count) * 100, 1)

                total_profit = sum(t.get("profit_usd", 0.0) for t in info["tokens"].values())
                total_buy = sum(t.get("buy_usd", 0.0) for t in info["tokens"].values())
                total_sell = sum(t.get("sell_usd", 0.0) for t in info["tokens"].values())

                # 判定画像标签
                tags = []
                if info["internal_hits"] >= 2 or (info["internal_hits"] >= 1 and win_rate >= 80):
                    tags.append("Cabal / 老鼠仓")
                    cabal_wallets.append(wallet)

                if win_rate >= 70 and avg_roi >= 50:
                    tags.append("Smart Money / 聪明钱")
                    smart_money_wallets.append(wallet)

                if info["sniper_hits"] >= 2:
                    tags.append("Sniper / 极速狙击手")
                    sniper_wallets.append(wallet)

                if not tags:
                    tags.append("Active Trader / 高频早期交易者")

                matched_wallets.append({
                    "address": wallet,
                    "gmgn_url": f"https://gmgn.ai/eth/address/{wallet}",
                    "overlap_count": participated_count,
                    "tokens_hit": token_list,
                    "details": info["tokens"],
                    "win_rate": win_rate,
                    "avg_roi": avg_roi,
                    "total_profit_usd": round(total_profit, 2),
                    "total_buy_usd": round(total_buy, 2),
                    "total_sell_usd": round(total_sell, 2),
                    "tags": tags,
                    "is_cabal": "Cabal / 老鼠仓" in tags,
                    "is_smart": "Smart Money / 聪明钱" in tags
                })

        # 按重合币种数倒序、胜率倒序排序
        matched_wallets.sort(key=lambda x: (x["overlap_count"], x["win_rate"], x["avg_roi"]), reverse=True)

        return {
            "mode": mode,
            "mode_name": mode_name_map[mode],
            "total_tokens_analyzed": len(clean_cas),
            "tokens_metadata": {
                ca: {
                    "name": data.get("token", {}).get("name", "Unknown"),
                    "symbol": data.get("token", {}).get("symbol", "UNKNOWN"),
                    "current_price": data.get("token", {}).get("current_price_usd", 0.0),
                    "launch_block": data.get("token", {}).get("launch_block", 0)
                }
                for ca, data in token_results.items() if "token" in data
            },
            "min_overlap_threshold": min_overlap,
            "cross_validated_wallets_count": len(matched_wallets),
            "cabal_count": len(cabal_wallets),
            "smart_money_count": len(smart_money_wallets),
            "sniper_count": len(sniper_wallets),
            "wallets": matched_wallets
        }
