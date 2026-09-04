import sqlite3
import os
import json
import time
from typing import Any, Dict, List, Optional

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "alpha_radar.db")

def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. 长期保存的聪明钱包表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS saved_wallets (
        address TEXT PRIMARY KEY,
        name TEXT DEFAULT '',
        winrate REAL DEFAULT 0.0,
        profit_7d REAL DEFAULT 0.0,
        profit_30d REAL DEFAULT 0.0,
        active_days_30d INTEGER DEFAULT 0,
        total_swaps_30d INTEGER DEFAULT 0,
        inner_play_count INTEGER DEFAULT 0,
        matched_tokens TEXT DEFAULT '[]',
        tags TEXT DEFAULT '["SmartMoney"]',
        notes TEXT DEFAULT '',
        first_seen_at INTEGER,
        last_updated_at INTEGER,
        is_favorite INTEGER DEFAULT 0
    )
    """)

    # 动态迁移增加 profit_7d 列
    try:
        cursor.execute("ALTER TABLE saved_wallets ADD COLUMN profit_7d REAL DEFAULT 0.0")
    except Exception:
        pass

    # 2. 扫描过的金狗代币缓存表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cached_tokens (
        address TEXT PRIMARY KEY,
        name TEXT,
        symbol TEXT,
        launch_time INTEGER,
        ath_mc REAL,
        current_mc REAL,
        peak_duration_minutes REAL,
        launchpad TEXT,
        pair_address TEXT,
        scanned_at INTEGER
    )
    """)

    conn.commit()
    conn.close()

class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def save_wallet(self, wallet_data: Dict[str, Any]) -> bool:
        """保存或更新钱包"""
        conn = self._get_conn()
        cursor = conn.cursor()
        addr = wallet_data["address"].lower().strip()
        now = int(time.time())

        # 检查是否已存在
        cursor.execute("SELECT first_seen_at, notes, tags FROM saved_wallets WHERE address = ?", (addr,))
        row = cursor.fetchone()

        first_seen = row["first_seen_at"] if row else now
        existing_notes = row["notes"] if row and row["notes"] else wallet_data.get("notes", "")
        
        # 标签合并
        tags = wallet_data.get("tags", ["SmartMoney"])
        if isinstance(tags, str):
            tags = [tags]
        if row and row["tags"]:
            try:
                old_tags = json.loads(row["tags"])
                tags = list(dict.fromkeys(old_tags + tags))
            except Exception:
                pass

        matched_tokens = wallet_data.get("matched_tokens", [])
        if isinstance(matched_tokens, list):
            matched_tokens_json = json.dumps(matched_tokens, ensure_ascii=False)
        else:
            matched_tokens_json = str(matched_tokens)

        p7 = float(wallet_data.get("profit_7d", 0.0) or 0.0)
        p30 = float(wallet_data.get("profit_30d", 0.0) or 0.0)

        cursor.execute("""
        INSERT INTO saved_wallets (
            address, name, winrate, profit_7d, profit_30d, active_days_30d, total_swaps_30d,
            inner_play_count, matched_tokens, tags, notes, first_seen_at, last_updated_at, is_favorite
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(address) DO UPDATE SET
            name = excluded.name,
            winrate = excluded.winrate,
            profit_7d = excluded.profit_7d,
            profit_30d = excluded.profit_30d,
            active_days_30d = excluded.active_days_30d,
            total_swaps_30d = excluded.total_swaps_30d,
            inner_play_count = excluded.inner_play_count,
            matched_tokens = excluded.matched_tokens,
            tags = excluded.tags,
            last_updated_at = excluded.last_updated_at
        """, (
            addr,
            wallet_data.get("name", ""),
            float(wallet_data.get("winrate", 0.0) or 0.0),
            p7,
            p30,
            int(wallet_data.get("active_days_30d", 0) or 0),
            int(wallet_data.get("total_swaps_30d", 0) or 0),
            int(wallet_data.get("inner_play_count", 0) or 0),
            matched_tokens_json,
            json.dumps(tags, ensure_ascii=False),
            existing_notes,
            first_seen,
            now,
            int(wallet_data.get("is_favorite", 0) or 0)
        ))

        conn.commit()
        conn.close()
        return True

    def batch_save_wallets(self, wallets: List[Dict[str, Any]]) -> int:
        count = 0
        for w in wallets:
            if self.save_wallet(w):
                count += 1
        return count

    def get_saved_wallets(self, keyword: str = "", order_by: str = "inner_play_count", direction: str = "desc") -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()

        valid_orders = {
            "inner_play_count": "inner_play_count",
            "profit_7d": "profit_7d",
            "profit_30d": "profit_30d",
            "winrate": "winrate",
            "last_updated_at": "last_updated_at",
            "active_days_30d": "active_days_30d"
        }
        order_col = valid_orders.get(order_by, "inner_play_count")
        dir_sql = "ASC" if direction.lower() == "asc" else "DESC"

        if keyword:
            sql = f"""
            SELECT * FROM saved_wallets 
            WHERE address LIKE ? OR name LIKE ? OR notes LIKE ? OR tags LIKE ? OR matched_tokens LIKE ?
            ORDER BY is_favorite DESC, {order_col} {dir_sql}
            """
            kw = f"%{keyword}%"
            cursor.execute(sql, (kw, kw, kw, kw, kw))
        else:
            sql = f"SELECT * FROM saved_wallets ORDER BY is_favorite DESC, {order_col} {dir_sql}"
            cursor.execute(sql)

        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["matched_tokens"] = json.loads(d["matched_tokens"])
            except Exception:
                d["matched_tokens"] = []
            try:
                d["tags"] = json.loads(d["tags"])
            except Exception:
                d["tags"] = []
            d["gmgn_url"] = f"https://gmgn.ai/eth/address/{d['address']}"
            result.append(d)

        conn.close()
        return result

    def update_wallet_note(self, address: str, notes: str = None, tags: Optional[List[str]] = None, is_favorite: Optional[int] = None) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        addr = address.lower().strip()

        updates = ["last_updated_at = ?"]
        params = [int(time.time())]

        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
        if tags is not None:
            updates.append("tags = ?")
            params.append(json.dumps(tags, ensure_ascii=False))
        if is_favorite is not None:
            updates.append("is_favorite = ?")
            params.append(is_favorite)

        params.append(addr)
        sql = f"UPDATE saved_wallets SET {', '.join(updates)} WHERE address = ?"
        cursor.execute(sql, params)
        conn.commit()
        affected = cursor.rowcount > 0
        conn.close()
        return affected

    def delete_wallet(self, address: str) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM saved_wallets WHERE address = ?", (address.lower().strip(),))
        conn.commit()
        affected = cursor.rowcount > 0
        conn.close()
        return affected

    def export_wallets_text(self, format_type: str = "newline") -> str:
        wallets = self.get_saved_wallets(order_by="inner_play_count", direction="desc")
        if format_type == "newline":
            return "\n".join([w["address"] for w in wallets])
        elif format_type == "comma":
            return ", ".join([w["address"] for w in wallets])
        elif format_type == "csv":
            lines = ["Address,Name,WinRate(%),30dProfit($),ActiveDays,24hInnerCount,MatchedTokens,Notes"]
            for w in wallets:
                tokens_str = ";".join([str(t) for t in w.get("matched_tokens", [])])
                note_clean = (w.get("notes") or "").replace(",", " ")
                lines.append(f"{w['address']},{w.get('name','')},{w.get('winrate',0):.1f},{w.get('profit_30d',0):.2f},{w.get('active_days_30d',0)},{w.get('inner_play_count',0)},\"{tokens_str}\",\"{note_clean}\"")
            return "\n".join(lines)
        return "\n".join([w["address"] for w in wallets])
