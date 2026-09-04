import json
import ssl
import urllib.request
from typing import Any, Dict, List, Optional
import httpx

class GMGNClient:
    """
    GMGN 数据与技能客户端：
    1. 直连 GMGN 官方爬虫接口 (pf/api/v1/wallets/{chain}/token_pnl_info)，直接获取网页端显示的买入、卖出、实现利润与盈利率
    2. 支持 GMGN OpenAPI 与排行榜接口
    """
    def __init__(self):
        self.ssl_context = ssl._create_unverified_context()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://gmgn.ai/",
        }

    def fetch_wallet_token_pnl(self, chain: str, ca: str, wallet: str) -> Optional[Dict[str, Any]]:
        """
        爬取 GMGN 前端弹窗原装数据：
        输入代币 CA 和钱包地址，返回该钱包在该代币的真实买入、卖出、实现利润与盈利率
        """
        url = f"https://gmgn.ai/pf/api/v1/wallets/{chain.lower()}/token_pnl_info"
        payload = {
            "token_address": ca.lower(),
            "wallet_addresses": [wallet.lower()]
        }
        data = json.dumps(payload).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=data, headers=self.headers)
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=4) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                d = res.get("data", {})
                if not d:
                    return None

                bought = float(d.get("bought", 0.0) or 0.0)
                sold = float(d.get("sold", 0.0) or 0.0)
                pnl = float(d.get("pnl", 0.0) or 0.0)
                pnl_percent = float(d.get("pnl_percent", 0.0) or 0.0) * 100.0

                return {
                    "wallet_address": wallet.lower(),
                    "buy_amount_usd": round(bought, 2),
                    "sell_amount_usd": round(sold, 2),
                    "realized_profit_usd": round(pnl, 2),
                    "roi_percentage": round(pnl_percent, 2),
                    "hold": float(d.get("hold", 0.0) or 0.0),
                    "source": "GMGN_CRAWLER"
                }
        except Exception:
            return None

    def batch_fetch_pnl(self, chain: str, ca: str, wallets: List[str], max_workers: int = 10) -> Dict[str, Dict[str, Any]]:
        """
        多线程高并发爬取多个钱包在该代币的 GMGN 官方真实数据
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = {}
        unique_wallets = list(dict.fromkeys([w.lower() for w in wallets if w]))
        if not unique_wallets:
            return results

        url = f"https://gmgn.ai/pf/api/v1/wallets/{chain.lower()}/token_pnl_info"

        def _fetch_single(w):
            payload = json.dumps({"token_address": ca.lower(), "wallet_addresses": [w]}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers=self.headers)
            try:
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=4) as resp:
                    if resp.status == 200:
                        d = json.loads(resp.read().decode("utf-8")).get("data", {})
                        if d:
                            bought = float(d.get("bought", 0.0) or 0.0)
                            sold = float(d.get("sold", 0.0) or 0.0)
                            pnl = float(d.get("pnl", 0.0) or 0.0)
                            pnl_percent = float(d.get("pnl_percent", 0.0) or 0.0) * 100.0
                            return w, {
                                "wallet_address": w,
                                "buy_amount_usd": round(bought, 2),
                                "sell_amount_usd": round(sold, 2),
                                "realized_profit_usd": round(pnl, 2),
                                "roi_percentage": round(pnl_percent, 2),
                                "source": "GMGN_CRAWLER"
                            }
            except Exception:
                pass
            return w, None

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(_fetch_single, w) for w in unique_wallets]
            for f in as_completed(futures):
                w, res = f.result()
                if res:
                    results[w] = res

        return results

    def get_token_rank_wallets(self, chain: str, ca: str) -> Dict[str, Dict[str, Any]]:
        """
        从 GMGN 交易榜获取官方排行榜交易者
        """
        chain = chain.lower()
        ca = ca.lower()
        results: Dict[str, Dict[str, Any]] = {}
        url = f"https://gmgn.ai/defi/quotation/v1/rank/{chain}/wallets/{ca}?orderby=pnl"
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                rank_list = data.get("data", {}).get("rank", [])
                for item in rank_list:
                    w_addr = item.get("wallet_address", "").lower()
                    if w_addr and w_addr not in results:
                        vol = float(item.get("volume_7d", 0.0) or 0.0)
                        realized_profit = float(item.get("realized_profit_7d", 0.0) or 0.0)
                        pnl_val = float(item.get("pnl_7d", 0.0) or 0.0) * 100.0
                        results[w_addr] = {
                            "wallet_address": w_addr,
                            "buy_amount_usd": round(vol * 0.5, 2),
                            "sell_amount_usd": round(vol * 0.5, 2),
                            "realized_profit_usd": round(realized_profit, 2),
                            "roi_percentage": round(pnl_val, 2),
                            "source": "GMGN_OFFICIAL",
                            "gmgn_url": f"https://gmgn.ai/eth/address/{w_addr}",
                        }
        except Exception:
            pass
        return results
