# Robinhood Chain 聪明钱与阴谋老鼠仓回测分析系统 (Robinhood Chain Alpha Radar)

针对 **Robinhood Chain (Chain ID: 4663)** 专为 Meme/代币打新与回测打造的链上早期地址穿透与交叉验证系统。

---

## 🌟 核心功能

1. **单代币 (Single CA) 深度穿透分析**：
   - **内盘阶段 (Pre-launch / Bonding Curve)**：
     - 自动定位代币开盘前的链上出块与事件，统计内盘买入独立人数。
     - 预估买入成本与当前盈利率（%）。
     - 列出早期潜伏地址与持仓占比。
   - **发射首分钟 (First 60s Post-Migration)**：
     - 毫秒级锁定开盘时间戳，精确定位开盘首 600 个区块（约 60 秒内）的所有买入交易。
     - 统计首分钟买入人数、极速抢筹（<5s 狙击手、<15s 抢跑、<60s 早期跟单）。
     - 计算首分钟买入地址当前盈利率（%）。
   - **早期地址池自动沉淀**：自动收集全部早期高胜率地址供后续跟踪与监控。

2. **多热门 CA 交叉验证与阴谋钱包/聪明钱挖掘 (Cross-Validation Radar)**：
   - 支持批量输入多个热门代币 CA，或直接**一键填入全网最活跃热门代币**。
   - 跨币地址频次矩阵碰撞：
     - 挖掘在 $\ge 2$ 个或多个热门代币中重复出现的地址。
     - 计算综合胜率（Win Rate %）与多币平均 ROI。
   - **智能行为标签标记**：
     - `[Cabal / 老鼠仓]`：多次在内盘或开盘极早期第一批精准协同潜伏。
     - `[Smart Money / 聪明钱]`：高胜率、高回报率、波段逃顶能力强。
     - `[Sniper / 极速狙击手]`：多币开盘 5 秒内极速上车。

3. **开箱即用与格式导出**：
   - 基于纯公共 RPC 节点（无需私有节点或付费 API Key），内置智能限速分块与容灾故障转移。
   - 一键导出 CSV 报表。
   - 一键导出兼容 GMGN / Telegram 监控机器人批量添加格式的地址清单。

---

## 🚀 快速启动

1. **运行程序**：
   ```bash
   ./run.sh
   # 或者指定自定义端口运行：
   # ./run.sh 8888
   ```
   或者通过 Python 直接启动：
   ```bash
   .venv/bin/python3 -m uvicorn backend.api:app --host 0.0.0.0 --port 8888
   ```

2. **访问 Web 界面**：
   打开浏览器访问：`http://127.0.0.1:8888`

---

## 🛠️ 技术架构

- **公链适配**：Robinhood Chain (Arbitrum Orbit L2, Chain ID 4663, 块时间约 0.10 秒)
- **后端服务**：FastAPI + Uvicorn + Web3.py + Httpx
- **前端交互**：TailwindCSS + Lucide Icons + 原生响应式架构

---

## 📖 开发进度与功能详述

详细的开发进度、已实现功能清单与架构设计报告请参见：[DEVELOPMENT_PROGRESS.md](DEVELOPMENT_PROGRESS.md)。
