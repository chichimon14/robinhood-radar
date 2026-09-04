import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from .token_analyzer import TokenAnalyzer
from .cross_validator import CrossValidator
from .hot_tokens import get_robinhood_hot_tokens
from .token_scanner import TokenScanner
from .wallet_hunter import WalletHunter
from .database import Database

app = FastAPI(
    title="Robinhood Chain Alpha Radar & Smart Money Harvester",
    description="Robinhood链内盘聪明钱包挖掘、24h金狗回测及长期数据库持久化系统",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

analyzer = TokenAnalyzer()
validator = CrossValidator(analyzer)
scanner = TokenScanner()
hunter = WalletHunter()
db = Database()

# ----------------- 数据请求模型 -----------------

class AnalyzeRequest(BaseModel):
    ca: str

class CrossValidateRequest(BaseModel):
    cas: List[str]
    min_overlap: Optional[int] = 2
    mode: Optional[str] = "combined"

class TokenScanRequest(BaseModel):
    min_ath_mc: Optional[float] = 500_000.0
    min_peak_minutes: Optional[float] = 3.0
    time_mode: Optional[str] = "last_24h" # 'last_24h', 'bj_8am', 'custom'
    custom_start_ts: Optional[int] = None
    custom_end_ts: Optional[int] = None

class ExtractWalletsRequest(BaseModel):
    tokens: List[Dict[str, Any]] # [{"address": "0x...", "symbol": "..."}]
    require_strict_filter: Optional[bool] = True
    enable_active_days: Optional[bool] = True
    min_active_days: Optional[int] = 7
    enable_winrate: Optional[bool] = True
    min_winrate: Optional[float] = 50.0
    enable_profit: Optional[bool] = True
    min_profit_usd: Optional[float] = 10000.0

class FrequencyRankRequest(BaseModel):
    wallets: List[Dict[str, Any]]

class SaveWalletRequest(BaseModel):
    wallet: Dict[str, Any]

class BatchSaveWalletsRequest(BaseModel):
    wallets: List[Dict[str, Any]]

class BatchDeleteWalletsRequest(BaseModel):
    addresses: List[str]

class UpdateWalletNoteRequest(BaseModel):
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    is_favorite: Optional[int] = None

# ----------------- 页面 1：筛选 24h 金狗 CA -----------------

@app.post("/api/tokens/filter-24h")
def filter_24h_tokens(req: TokenScanRequest):
    """
    【页面 1 接口】
    按过去 24 小时（或指定北京时间 8 点~次日 8 点），
    严格筛选所有在过去 24 小时内新发射、且高点市值超过 500k 的代币列表
    """
    try:
        res = scanner.scan_tokens(
            min_ath_mc=req.min_ath_mc or 500_000.0,
            min_peak_minutes=req.min_peak_minutes or 3.0,
            time_mode=req.time_mode or "last_24h",
            custom_start_ts=req.custom_start_ts,
            custom_end_ts=req.custom_end_ts
        )
        return {"success": True, "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"扫描代币失败: {str(e)}")

# ----------------- 页面 2：提取内盘地址与聪明钱质检 -----------------

@app.post("/api/wallets/extract-internal")
def extract_internal_wallets(req: ExtractWalletsRequest):
    """
    【页面 2 接口】
    输入页面 1 勾选的 CA 列表，穿透获取内盘阶段买入地址，
    并核验聪明钱包三道闸门（支持用户勾选/取消勾选复选框，自由选择条件）：
    1. 过去一个月内至少超过 X 天有交易 (enable_active_days / min_active_days)
    2. GMGN 胜率超过 Y% (enable_winrate / min_winrate)
    3. GMGN 7D 已实现利润超过 Z 美元 (enable_profit / min_profit_usd)
    """
    if not req.tokens:
        raise HTTPException(status_code=400, detail="请至少选择一个代币 CA 进行提取")
    try:
        res = hunter.batch_extract_and_filter(
            token_items=req.tokens,
            require_strict_filter=req.require_strict_filter if req.require_strict_filter is not None else True,
            enable_active_days=req.enable_active_days if req.enable_active_days is not None else True,
            min_active_days=req.min_active_days if req.min_active_days is not None else 7,
            enable_winrate=req.enable_winrate if req.enable_winrate is not None else True,
            min_winrate=req.min_winrate if req.min_winrate is not None else 50.0,
            enable_profit=req.enable_profit if req.enable_profit is not None else True,
            min_profit_usd=req.min_profit_usd if req.min_profit_usd is not None else 10000.0
        )
        return {"success": True, "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"提取内盘地址失败: {str(e)}")

# ----------------- 页面 3：按 24h 出现频次排序 -----------------

@app.post("/api/wallets/frequency-rank")
def compute_frequency_rank(req: FrequencyRankRequest):
    """
    【页面 3 接口】
    把提取出的内盘地址按【过去 24 小时内玩的内盘数量（出现频次）】从多到少严格排序！
    次要按 7天已实现利润与胜率排序
    """
    try:
        wallets = req.wallets or []
        # 按频次排序
        wallets.sort(
            key=lambda x: (
                x.get("inner_play_count_24h", len(x.get("matched_tokens", []))),
                x.get("profit_7d", x.get("profit_30d", 0.0)),
                x.get("winrate", 0.0)
            ),
            reverse=True
        )
        return {"success": True, "data": {"ranked_wallets": wallets, "count": len(wallets)}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"频次排序计算失败: {str(e)}")

# ----------------- 长期数据库持久化接口 -----------------

@app.get("/api/db/wallets/addresses")
def get_saved_wallet_addresses():
    """获取长期数据库中所有已保存的钱包地址（去重与前端高亮匹配）"""
    try:
        addresses = db.get_all_saved_addresses()
        return {"success": True, "addresses": addresses, "total": len(addresses)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取已保存地址失败: {str(e)}")

@app.post("/api/db/wallets/save")
def save_wallet_to_db(req: SaveWalletRequest):
    """保存单个钱包到长期数据库"""
    try:
        ok = db.save_wallet(req.wallet, only_new=False)
        return {"success": ok}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")

@app.post("/api/db/wallets/batch-save")
def batch_save_wallets_to_db(req: BatchSaveWalletsRequest):
    """批量保存选中的聪明钱包到长期数据库，严格防重复入库"""
    try:
        res = db.batch_save_wallets(req.wallets, only_new=True)
        return {
            "success": True,
            "saved_count": res["saved_count"],
            "skipped_count": res["skipped_count"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量保存失败: {str(e)}")

@app.get("/api/db/wallets")
def get_db_wallets(
    keyword: str = Query("", description="搜索关键词（地址/备注/标签/代币）"),
    order_by: str = Query("inner_play_count", description="排序字段: inner_play_count, profit_30d, winrate, last_updated_at"),
    direction: str = Query("desc", description="排序方向: asc, desc")
):
    """查询长期数据库中保存的所有钱包"""
    try:
        wallets = db.get_saved_wallets(keyword=keyword, order_by=order_by, direction=direction)
        return {"success": True, "wallets": wallets, "total": len(wallets)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询数据库失败: {str(e)}")

@app.post("/api/db/wallets/batch-delete")
def batch_delete_db_wallets(req: BatchDeleteWalletsRequest):
    """批量从长期数据库中删除钱包"""
    try:
        deleted = db.batch_delete_wallets(req.addresses)
        return {"success": True, "deleted_count": deleted}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量删除钱包失败: {str(e)}")

@app.put("/api/db/wallets/{address}")
def update_db_wallet(address: str, req: UpdateWalletNoteRequest):
    """修改数据库中钱包的备注、标签、是否收藏"""
    try:
        ok = db.update_wallet_note(address=address, notes=req.notes, tags=req.tags, is_favorite=req.is_favorite)
        return {"success": ok}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新钱包失败: {str(e)}")

@app.delete("/api/db/wallets/{address}")
def delete_db_wallet(address: str):
    """从长期数据库中删除钱包"""
    try:
        ok = db.delete_wallet(address)
        return {"success": ok}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除钱包失败: {str(e)}")

@app.get("/api/db/wallets/export")
def export_db_wallets(format: str = Query("newline", description="导出格式: newline (GMGN/TG机器人), comma, csv")):
    """一键导出长期数据库中的钱包"""
    try:
        text = db.export_wallets_text(format_type=format)
        media_type = "text/csv" if format == "csv" else "text/plain; charset=utf-8"
        filename = f"robinhood_smart_wallets_{int(os.path.getmtime(db.db_path) if os.path.exists(db.db_path) else 0)}.{format if format == 'csv' else 'txt'}"
        return Response(
            content=text,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")

# ----------------- 原有功能保留 -----------------

@app.get("/api/hot-tokens")
def get_hot_tokens():
    try:
        tokens = get_robinhood_hot_tokens()
        return {"success": True, "tokens": tokens}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze")
def analyze_token(req: AnalyzeRequest):
    if not req.ca or not req.ca.startswith("0x"):
        raise HTTPException(status_code=400, detail="请输入合法的 0x 开头代币合约地址(CA)")
    try:
        data = analyzer.analyze(req.ca)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cross-validate")
def cross_validate_tokens(req: CrossValidateRequest):
    if not req.cas or len(req.cas) < 2:
        raise HTTPException(status_code=400, detail="交叉验证至少需要提供 2 个不同的代币合约地址(CA)")
    try:
        data = validator.validate_multiple_tokens(req.cas, min_overlap=req.min_overlap or 2, mode=req.mode or "combined")
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
def health_check():
    return {"status": "ok", "chain": "Robinhood (Chain ID 4663)"}

# 静态前端挂载
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(frontend_dir, "index.html"))
