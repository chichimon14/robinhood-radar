import json
import ssl
import urllib.request
from typing import Any, Dict, List

def format_mc(val: float) -> str:
    """格式化市值为易读形式 ($107.5K / $5.88M)"""
    if val >= 1_000_000:
        return f"${val / 1_000_000:.2f}M"
    elif val >= 1_000:
        return f"${val / 1_000:.1f}K"
    elif val > 0:
        return f"${val:.0f}"
    return "$0"

def get_robinhood_hot_tokens() -> List[Dict[str, Any]]:
    """
    调用 GMGN 官方热门代币接口 (1小时热门 / trend?chain=robinhood&tab=trending)
    接口：https://gmgn.ai/defi/quotation/v1/rank/robinhood/swaps/1h?orderby=default&direction=desc
    """
    ctx = ssl._create_unverified_context()
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://gmgn.ai/trend?chain=robinhood&tab=trending"
    }

    url = "https://gmgn.ai/defi/quotation/v1/rank/robinhood/swaps/1h?orderby=default&direction=desc"
    tokens = []
    seen = set()

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            rank = data.get("data", {}).get("rank", [])
            for item in rank:
                addr = item.get("address", "").lower()
                if not addr or addr in seen:
                    continue
                seen.add(addr)

                name = item.get("name") or item.get("symbol") or "Unknown"
                if len(name) > 16:
                    name = name[:15] + ".."
                symbol = item.get("symbol") or name
                mc = float(item.get("market_cap", 0.0) or item.get("fdv", 0.0) or 0.0)

                tokens.append({
                    "name": name,
                    "symbol": symbol,
                    "market_cap": mc,
                    "market_cap_formatted": format_mc(mc),
                    "address": addr,
                    "gmgn_url": f"https://gmgn.ai/robinhood/token/{addr}"
                })
                if len(tokens) >= 12:
                    break
    except Exception as e:
        print(f"Error fetching GMGN 1h trending tokens: {e}")

    return tokens[:12]
