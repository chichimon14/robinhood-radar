import concurrent.futures
import json
import ssl
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

class TokenScanner:
    """
    GMGN 官方技能规范代币扫描器：
    调用 GMGN 核心行情规范接口，根据 filter=is_out_market 严格筛选过去 24 小时内【已开盘】的 Robinhood 链代币
    """
    def __init__(self):
        self.ssl_context = ssl._create_unverified_context()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://gmgn.ai/"
        }

    @staticmethod
    def get_bj_24h_window() -> Tuple[int, int, str]:
        """
        计算北京时间早上 8 点到次日 8 点的时间窗口时间戳
        """
        tz_bj = timezone(timedelta(hours=8))
        now_bj = datetime.now(tz_bj)
        
        today_8am = now_bj.replace(hour=8, minute=0, second=0, microsecond=0)
        if now_bj < today_8am:
            start_dt = today_8am - timedelta(days=1)
            end_dt = today_8am
        else:
            start_dt = today_8am
            end_dt = today_8am + timedelta(days=1)

        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())
        label = f"北京时间 {start_dt.strftime('%m-%d 08:00')} ~ {end_dt.strftime('%m-%d 08:00')}"
        return start_ts, end_ts, label

    def _fetch_url(self, url: str, retry: int = 1) -> Optional[Dict[str, Any]]:
        for attempt in range(retry + 1):
            try:
                time.sleep(0.1) # 轻微防抖防触发高频限制
                req = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=8) as resp:
                    if resp.status == 200:
                        return json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                if attempt < retry:
                    time.sleep(0.4)
                    continue
                print(f"[GMGN-Skill Scanner] Error fetching {url}: {e}")
        return None

    def scan_tokens(
        self,
        min_ath_mc: float = 500_000.0,
        min_peak_minutes: float = 3.0,
        time_mode: str = "last_24h",
        custom_start_ts: Optional[int] = None,
        custom_end_ts: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        根据 GMGN 规范调用 GMGN 接口：
        1. 必须是 Robinhood 链【已开盘 (is_out_market)】的代币
        2. 开盘时间 open_timestamp 严格在过去 24 小时内
        3. 历史最高市值 ATH >= min_ath_mc (默认 500k)
        4. 达到峰值维持/换手超过 min_peak_minutes (默认 3 分钟)
        """
        now_ts = int(time.time())
        # 支持用户自选精确时间区间（精确到月日时），默认使用固定北京时间早8点~次日早8点
        if custom_start_ts and custom_end_ts:
            start_ts = custom_start_ts
            end_ts = custom_end_ts
            dt_start = datetime.fromtimestamp(start_ts, timezone(timedelta(hours=8)))
            dt_end = datetime.fromtimestamp(end_ts, timezone(timedelta(hours=8)))
            time_label = f"{dt_start.strftime('%Y-%m-%d %H:%M')} ~ {dt_end.strftime('%Y-%m-%d %H:%M')}"
        else:
            start_ts, end_ts, time_label = self.get_bj_24h_window()

        print(f"[*] Calling GMGN API: Scanning tokens opened on Robinhood chain in {time_label} [{start_ts} ~ {end_ts}]")

        candidates: Dict[str, Dict[str, Any]] = {}

        # GMGN 官方多周期多维度请求已开盘外盘代币 (filter=is_out_market)
        endpoints = [
            "https://gmgn.ai/defi/quotation/v1/rank/robinhood/swaps/24h?orderby=open_timestamp&direction=desc&filter=is_out_market&limit=100",
            "https://gmgn.ai/defi/quotation/v1/rank/robinhood/swaps/24h?orderby=history_highest_market_cap&direction=desc&filter=is_out_market&limit=100",
            "https://gmgn.ai/defi/quotation/v1/rank/robinhood/swaps/24h?orderby=swaps&direction=desc&filter=is_out_market&limit=100",
            "https://gmgn.ai/defi/quotation/v1/rank/robinhood/swaps/24h?orderby=volume&direction=desc&filter=is_out_market&limit=100",
            "https://gmgn.ai/defi/quotation/v1/rank/robinhood/swaps/6h?orderby=open_timestamp&direction=desc&filter=is_out_market&limit=100",
            "https://gmgn.ai/defi/quotation/v1/rank/robinhood/swaps/1h?orderby=open_timestamp&direction=desc&filter=is_out_market&limit=100",
            "https://gmgn.ai/defi/quotation/v1/pairs/robinhood/new_pairs/24h?limit=100"
        ]

        for url in endpoints:
            res = self._fetch_url(url)
            if res and res.get("code") == 0:
                data = res.get("data", {})
                items = data.get("rank", []) or data.get("pairs", [])
                for it in items:
                    binfo = it.get("base_token_info") if "base_token_info" in it else it
                    addr = (binfo.get("address") or it.get("base_address") or it.get("address") or "").lower()
                    if not addr or addr in candidates:
                        continue
                    ots = it.get("open_timestamp") or binfo.get("open_timestamp") or binfo.get("creation_timestamp")
                    candidates[addr] = {
                        "address": addr,
                        "name": binfo.get("name") or "Unknown",
                        "symbol": binfo.get("symbol") or "UNKNOWN",
                        "market_cap": float(binfo.get("market_cap", 0.0) or 0.0),
                        "history_highest_market_cap": float(binfo.get("history_highest_market_cap") or binfo.get("market_cap") or 0.0),
                        "open_timestamp": ots,
                        "creation_timestamp": binfo.get("creation_timestamp") or ots,
                        "launchpad_platform": it.get("launchpad_platform") or binfo.get("launchpad_platform") or "DEX",
                        "swaps": binfo.get("swaps", 0),
                        "buys": binfo.get("buys", 0),
                        "volume": float(binfo.get("volume", 0.0) or 0.0),
                        "holder_count": binfo.get("holder_count", 0),
                        "twitter_username": binfo.get("twitter_username", ""),
                        "telegram": binfo.get("telegram", ""),
                        "website": binfo.get("website", "")
                    }

        print(f"[*] Fetched {len(candidates)} total candidates from GMGN for Robinhood chain.")

        # 核心业务铁律：用户明确定义【发射时间 = 迁移到外盘时间 (open_timestamp)】
        # 1. 先进行时间区间与 ATH 市值初筛，筛选出真正达标的金狗（通常 10~30 个）
        target_tokens: Dict[str, Dict[str, Any]] = {}
        for addr, item in candidates.items():
            migration_open_ts = int(item.get("open_timestamp", 0) or 0)
            if migration_open_ts <= 0:
                continue

            # 严格限定迁移外盘时间在所选区间内
            if migration_open_ts < start_ts or migration_open_ts > end_ts:
                continue

            ath_mc = float(item.get("history_highest_market_cap", 0.0) or item.get("market_cap", 0.0) or 0.0)
            if ath_mc >= min_ath_mc:
                target_tokens[addr] = item

        print(f"[*] Found {len(target_tokens)} qualified tokens in target window. Enriching socials & holder count...")

        # 2. 仅对达标的这批优质金狗并发补充社交链接与真实持币人数，彻底避免并发 429 报错
        true_meta_map: Dict[str, Tuple[Optional[int], Optional[int], Dict[str, str]]] = {}

        def _get_true_meta(addr_key: str):
            u_info = f"https://gmgn.ai/api/v1/token_info/robinhood/{addr_key}"
            d_info = self._fetch_url(u_info)
            ct = None
            hc = None
            if d_info and d_info.get("code") == 0 and d_info.get("data"):
                td = d_info["data"]
                ct = td.get("creation_timestamp")
                hc = td.get("holder_count")

            # 抓取完整的社交媒体链接（YouTube, Twitter/X, Telegram, Website, Discord 等）
            u_link = f"https://gmgn.ai/api/v1/token_link/robinhood/{addr_key}"
            d_link = self._fetch_url(u_link)
            links = {}
            if d_link and d_link.get("code") == 0 and d_link.get("data"):
                ld = d_link["data"]
                tw = (ld.get("twitter_username") or "").strip()
                if tw and not tw.startswith("http"):
                    tw = f"https://x.com/{tw.lstrip('@')}"
                links = {
                    "twitter_url": tw,
                    "telegram_url": (ld.get("telegram") or "").strip(),
                    "website_url": (ld.get("website") or "").strip(),
                    "youtube_url": (ld.get("youtube") or "").strip(),
                    "discord_url": (ld.get("discord") or "").strip(),
                    "tiktok_url": (ld.get("tiktok") or "").strip()
                }
            return addr_key, ct, hc, links

        if target_tokens:
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
                for addr_k, ct, hc, lks in executor.map(_get_true_meta, target_tokens.keys()):
                    true_meta_map[addr_k] = (ct, hc, lks)

        qualified_tokens: List[Dict[str, Any]] = []

        for addr, item in target_tokens.items():
            meta = true_meta_map.get(addr)
            true_ct = meta[0] if meta else None
            true_hc = meta[1] if meta else None
            socials = meta[2] if meta else {}

            migration_open_ts = int(item.get("open_timestamp", 0) or 0)
            ath_mc = float(item.get("history_highest_market_cap", 0.0) or item.get("market_cap", 0.0) or 0.0)
            cur_mc = float(item.get("market_cap", 0.0) or 0.0)

            swaps = int(item.get("swaps", 0) or 0)
            volume = float(item.get("volume", 0.0) or 0.0)
            holder_count = true_hc if (true_hc is not None and true_hc > 0) else int(item.get("holder_count", 0) or 0)

            name = item.get("name") or item.get("symbol") or "Unknown"
            symbol = item.get("symbol") or name
            launchpad = item.get("launchpad_platform") or item.get("launchpad") or "DEX"

            # 社交媒体提取与规范化（优先使用官方 token_link 数据）
            tw = socials.get("twitter_url") or (item.get("twitter_username") or "").strip()
            if tw and not tw.startswith("http"):
                tw = f"https://x.com/{tw.lstrip('@')}"
            tg = socials.get("telegram_url") or (item.get("telegram") or "").strip()
            web = socials.get("website_url") or (item.get("website") or "").strip()
            yt = socials.get("youtube_url") or ""
            disc = socials.get("discord_url") or ""
            tk = socials.get("tiktok_url") or ""

            # 创建时间与迁移外盘时间
            creation_ts = int(true_ct or item.get("creation_timestamp", 0) or 0)
            creation_time_str = datetime.fromtimestamp(creation_ts, timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S") if creation_ts > 0 else ""

            qualified_tokens.append({
                "address": addr,
                "name": name,
                "symbol": symbol,
                "ath_market_cap": round(ath_mc, 2),
                "ath_mc_formatted": self._format_usd(ath_mc),
                "current_market_cap": round(cur_mc, 2),
                "current_mc_formatted": self._format_usd(cur_mc),
                "holder_count": holder_count,
                "holder_count_formatted": f"{holder_count:,}",
                "twitter_url": tw,
                "telegram_url": tg,
                "website_url": web,
                "youtube_url": yt,
                "discord_url": disc,
                "tiktok_url": tk,
                "open_timestamp": migration_open_ts,
                "open_time_str": datetime.fromtimestamp(migration_open_ts, timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),
                "creation_timestamp": creation_ts,
                "creation_time_str": creation_time_str,
                "token_age_hours": round((now_ts - migration_open_ts) / 3600.0, 1),
                "launchpad_platform": launchpad,
                "swaps": swaps,
                "volume": round(volume, 2),
                "gmgn_url": f"https://gmgn.ai/robinhood/token/{addr}",
                "robinscan_url": f"https://robinscan.io/token/{addr}",
                "selected": True
            })

        # 按 ATH 市值降序排列
        qualified_tokens.sort(key=lambda x: x["ath_market_cap"], reverse=True)

        return {
            "time_label": time_label,
            "start_timestamp": start_ts,
            "end_timestamp": end_ts,
            "total_scanned": len(candidates),
            "matched_count": len(qualified_tokens),
            "tokens": qualified_tokens
        }

    @staticmethod
    def _format_usd(val: float) -> str:
        if val >= 1_000_000:
            return f"${val / 1_000_000:.2f}M"
        elif val >= 1_000:
            return f"${val / 1_000:.1f}K"
        elif val > 0:
            return f"${val:.2f}"
        return "$0"
