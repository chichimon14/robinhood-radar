// 全局状态
let capturedInternalWalletsSet = new Set();
let capturedExternalWalletsSet = new Set();
let capturedWalletsSet = new Set();
let currentSingleResult = null;
let currentCrossResult = null;
let hotTokens = [];
let currentCrossMode = "combined"; // "internal" | "external" | "combined"

// 切换碰撞模式 (内盘 / 外盘 / 综合)
function setCrossMode(mode) {
  currentCrossMode = mode;
  const btnInternal = document.getElementById("modeBtnInternal");
  const btnExternal = document.getElementById("modeBtnExternal");
  const btnCombined = document.getElementById("modeBtnCombined");
  if (!btnInternal || !btnExternal || !btnCombined) return;

  const activeInternal = "px-3 py-1.5 rounded-lg font-semibold transition bg-orange-500/20 text-orange-400 border border-orange-500/30 flex items-center gap-1 cursor-pointer";
  const activeExternal = "px-3 py-1.5 rounded-lg font-semibold transition bg-green-500/20 text-green-400 border border-green-500/30 flex items-center gap-1 cursor-pointer";
  const activeCombined = "px-3 py-1.5 rounded-lg font-semibold transition bg-blue-500/20 text-blue-400 border border-blue-500/30 flex items-center gap-1 cursor-pointer";
  const inactive = "px-3 py-1.5 rounded-lg font-medium transition text-gray-400 hover:text-white flex items-center gap-1 cursor-pointer";

  btnInternal.className = mode === "internal" ? activeInternal : inactive;
  btnExternal.className = mode === "external" ? activeExternal : inactive;
  btnCombined.className = mode === "combined" ? activeCombined : inactive;

  const modeTexts = {
    "internal": "内盘碰撞 (仅分析内盘潜伏地址)",
    "external": "外盘碰撞 (仅分析外盘上线首分钟抢跑地址)",
    "combined": "综合碰撞 (内外盘地址合并碰撞)"
  };
  showToast(`已切换为: ${modeTexts[mode]}`);
}

// 初始化
document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) {
    lucide.createIcons();
  }
  loadHotTokens();
});

// Toast 提示
function showToast(msg) {
  const toast = document.getElementById("toast");
  const toastMsg = document.getElementById("toastMsg");
  toastMsg.textContent = msg;
  toast.classList.remove("translate-y-20", "opacity-0", "pointer-events-none");
  toast.classList.add("translate-y-0", "opacity-100");
  setTimeout(() => {
    toast.classList.add("translate-y-20", "opacity-0", "pointer-events-none");
    toast.classList.remove("translate-y-0", "opacity-100");
  }, 2200);
}

// Tab 切换
function switchTab(tab) {
  const pSingle = document.getElementById("panelSingle");
  const pCross = document.getElementById("panelCross");
  const pExport = document.getElementById("panelExport");

  const bSingle = document.getElementById("tabBtnSingle");
  const bCross = document.getElementById("tabBtnCross");
  const bExport = document.getElementById("tabBtnExport");

  const activeBtnCls = "px-4 py-1.5 rounded-lg font-medium transition flex items-center gap-1.5 bg-green-600 text-black shadow";
  const inactiveBtnCls = "px-4 py-1.5 rounded-lg font-medium transition flex items-center gap-1.5 text-gray-300 hover:text-white";

  [pSingle, pCross, pExport].forEach(p => p.classList.add("hidden"));
  [bSingle, bCross, bExport].forEach(b => b.className = inactiveBtnCls);

  if (tab === 'single') {
    pSingle.classList.remove("hidden");
    bSingle.className = activeBtnCls;
  } else if (tab === 'cross') {
    pCross.classList.remove("hidden");
    bCross.className = activeBtnCls;
  } else if (tab === 'export') {
    pExport.classList.remove("hidden");
    bExport.className = activeBtnCls;
    updateCapturedPoolUI();
  }

  if (window.lucide) lucide.createIcons();
}

// 获取 GMGN 同时段热门代币列表
async function loadHotTokens() {
  const container = document.getElementById("hotTokenChips");
  try {
    const res = await fetch("/api/hot-tokens");
    const json = await res.json();
    if (json.success && json.tokens.length > 0) {
      hotTokens = json.tokens;
      container.innerHTML = "";
      const crossHotContainer = document.getElementById("crossHotChips");
      if (crossHotContainer) crossHotContainer.innerHTML = "";

      hotTokens.forEach(t => {
        // 1. 单币面板胶囊
        const chip = document.createElement("a");
        chip.href = t.gmgn_url || `https://gmgn.ai/robinhood/token/${t.address}`;
        chip.target = "_blank";
        chip.title = `点击在 GMGN 查看 ${t.name} 并同步填入分析`;
        chip.className = "px-3 py-1.5 rounded-lg bg-gray-900/90 hover:bg-gray-800 border border-gray-700/80 hover:border-green-500/50 text-gray-200 transition flex items-center gap-2 text-xs group cursor-pointer shadow-sm";
        chip.innerHTML = `
          <span class="font-bold text-white group-hover:text-green-400 transition">${t.name}</span>
          <span class="px-1.5 py-0.2 rounded bg-orange-500/10 text-orange-400 border border-orange-500/20 font-mono text-[11px] font-semibold">${t.market_cap_formatted}</span>
          <span class="text-[10px] text-gray-500 group-hover:text-green-400 transition">↗</span>
        `;
        chip.onclick = (e) => {
          document.getElementById("singleCaInput").value = t.address;
          analyzeSingleCA();
        };
        container.appendChild(chip);

        // 2. 多币交叉验证面板快捷追加胶囊
        if (crossHotContainer) {
          const crossChip = document.createElement("button");
          crossChip.type = "button";
          crossChip.title = `点击追加 ${t.name} 到多币验证池`;
          crossChip.className = "px-2 py-1 rounded bg-gray-900 hover:bg-gray-800 border border-gray-700/70 hover:border-green-500/40 text-gray-300 hover:text-white transition flex items-center gap-1.5 text-[11px] cursor-pointer";
          crossChip.innerHTML = `
            <span class="font-medium text-white">${t.name}</span>
            <span class="text-orange-400 font-mono text-[10px]">${t.market_cap_formatted}</span>
            <span class="text-green-400 font-bold">+</span>
          `;
          crossChip.onclick = () => appendCaToCross(t.address, t.name);
          crossHotContainer.appendChild(crossChip);
        }
      });

      // 保持 CA 搜索框默认为空
    }
  } catch (err) {
    container.innerHTML = `<span class="text-red-400 text-xs">加载 GMGN 热门代币失败</span>`;
  }
}

// 快速追加代币到多币交叉验证框
function appendCaToCross(address, name) {
  const textarea = document.getElementById("crossCasInput");
  const current = textarea.value.trim();
  const lowerAddrs = current.toLowerCase().split("\n");
  if (lowerAddrs.includes(address.toLowerCase())) {
    showToast(`${name || '该代币'} 已经在列表中！`);
    return;
  }
  textarea.value = current ? `${current}\n${address}` : address;
  updateCrossCasCount();
  showToast(`已追加 ${name || address}！`);
}

// 实时更新已输入的 CA 数量
function updateCrossCasCount() {
  const textarea = document.getElementById("crossCasInput");
  const el = document.getElementById("crossCasCount");
  if (!textarea || !el) return;
  const cas = textarea.value.split("\n").map(l => l.trim()).filter(l => l.startsWith("0x"));
  el.textContent = `已输入 ${cas.length} 个有效 CA`;
}

// 单代币深度分析
async function analyzeSingleCA() {
  const ca = document.getElementById("singleCaInput").value.trim();
  if (!ca || !ca.startsWith("0x")) {
    showToast("请输入有效的 0x 开头合约地址 (CA)");
    return;
  }

  const loading = document.getElementById("singleLoading");
  const resultCont = document.getElementById("singleResultContainer");
  const btn = document.getElementById("btnStartSingleAnalysis");

  loading.classList.remove("hidden");
  resultCont.classList.add("hidden");
  btn.disabled = true;

  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ca: ca })
    });
    const json = await res.json();
    if (!res.ok || !json.success) {
      throw new Error(json.detail || "分析请求失败");
    }

    currentSingleResult = json.data;
    renderSingleResult(currentSingleResult);
    resultCont.classList.remove("hidden");
    showToast("单币深度分析完成！已提取早期地址");
  } catch (err) {
    alert("分析失败: " + err.message);
  } finally {
    loading.classList.add("hidden");
    btn.disabled = false;
  }
}

// 渲染单代币结果
function renderSingleResult(data) {
  const tok = data.token;
  document.getElementById("resTokenInitial").textContent = tok.symbol.charAt(0) || "T";
  document.getElementById("resTokenSymbol").textContent = tok.symbol;
  document.getElementById("resTokenName").textContent = tok.name;
  document.getElementById("resTokenCA").textContent = tok.address;
  document.getElementById("resExplorerLink").href = `https://robinscan.io/token/${tok.address}`;

  document.getElementById("resPriceUsd").textContent = tok.current_price_usd ? `$${tok.current_price_usd.toFixed(6)}` : "N/A";
  document.getElementById("resFdv").textContent = tok.fdv_usd ? `$${(tok.fdv_usd / 1000).toFixed(1)}K` : "N/A";
  document.getElementById("resVolume").textContent = tok.volume_24h_usd ? `$${(tok.volume_24h_usd / 1000000).toFixed(2)}M` : "N/A";

  // 内盘数据
  const internal = data.internal_market;
  document.getElementById("resInternalBuyersCount").textContent = `${internal.buyer_count} 人`;
  document.getElementById("resInternalRoi").textContent = (internal.estimated_roi_pct >= 0 ? "+" : "") + `${internal.estimated_roi_pct.toLocaleString()}%`;

  // 首分钟数据
  const firstMin = data.first_minute;
  document.getElementById("resFirstMinBuyersCount").textContent = `${firstMin.buyer_count} 人`;
  document.getElementById("resFirstMinRoi").textContent = (firstMin.estimated_roi_pct >= 0 ? "+" : "") + `${firstMin.estimated_roi_pct.toLocaleString()}%`;

  // 缓存买家列表供实时搜索过滤
  window.cachedInternalBuyers = internal.top_buyers || [];
  window.cachedFirstMinBuyers = firstMin.top_buyers || [];

  renderBuyersList("internal", window.cachedInternalBuyers);
  renderBuyersList("firstMin", window.cachedFirstMinBuyers);

  // 汇总钱包存入分类集合
  (internal.top_buyers || []).forEach(b => capturedInternalWalletsSet.add(b.address));
  (firstMin.top_buyers || []).forEach(b => capturedExternalWalletsSet.add(b.address));
  data.all_early_wallets.forEach(w => capturedWalletsSet.add(w));
  document.getElementById("resTotalWalletsCount").textContent = data.all_early_wallets.length;
  updateCapturedPoolUI();

  if (window.lucide) lucide.createIcons();
}

// 动态渲染指定类型的买家列表
function renderBuyersList(type, list) {
  const container = document.getElementById(type === "internal" ? "internalBuyersList" : "firstMinBuyersList");
  container.innerHTML = "";

  if (!list || list.length === 0) {
    container.innerHTML = `<div class="text-gray-500 py-3 text-center">暂无匹配的钱包买家记录</div>`;
    return;
  }

  list.forEach((b, idx) => {
    const row = document.createElement("div");
    row.className = "p-2.5 rounded-xl bg-gray-950/70 hover:bg-gray-900 border border-gray-800/80 transition space-y-1.5";
    const roiClass = b.roi_percentage >= 0 ? "text-green-400" : "text-red-400";
    const roiSign = b.roi_percentage >= 0 ? "+" : "";
    const profitClass = b.realized_profit_usd >= 0 ? "text-green-400" : "text-red-400";
    const profitSign = b.realized_profit_usd >= 0 ? "+" : "";

    const speedBadge = b.seconds_after_launch !== undefined 
      ? `<span class="px-1.5 py-0.2 rounded bg-blue-500/10 text-blue-400 border border-blue-500/30 text-[10px] font-mono">+${b.seconds_after_launch}s</span>` 
      : "";

    row.innerHTML = `
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="text-gray-500 text-[11px] w-4">${idx + 1}.</span>
          <a href="${b.gmgn_url}" target="_blank" title="点击在 GMGN 平台分析该地址完整交易与持仓" class="text-gray-200 hover:text-green-400 font-mono font-semibold flex items-center gap-1.5 group">
            <span>${b.address.slice(0, 8)}...${b.address.slice(-6)}</span>
            <span class="px-1.5 py-0.2 rounded bg-green-500/10 text-green-400 border border-green-500/30 text-[10px] font-sans group-hover:bg-green-500 group-hover:text-black transition">
              GMGN ↗
            </span>
          </a>
          ${speedBadge}
        </div>
        <div class="flex items-center gap-2">
          <span class="${roiClass} font-bold font-mono text-xs">${roiSign}${b.roi_percentage.toLocaleString()}%</span>
          <button onclick="copyText('${b.address}')" class="text-gray-500 hover:text-white" title="复制地址"><i data-lucide="copy" class="w-3.5 h-3.5"></i></button>
        </div>
      </div>
      <div class="grid grid-cols-3 gap-2 text-[11px] font-sans pt-1 border-t border-gray-900 text-gray-400">
        <div>买入: <span class="text-gray-200 font-mono font-medium">$${b.buy_amount_usd.toLocaleString()}</span></div>
        <div>卖出: <span class="text-gray-200 font-mono font-medium">$${b.sell_amount_usd.toLocaleString()}</span></div>
        <div>实现利润: <span class="${profitClass} font-mono font-medium">${profitSign}$${b.realized_profit_usd.toLocaleString()}</span></div>
      </div>
    `;
    container.appendChild(row);
  });
  if (window.lucide) lucide.createIcons();
}

// 实时搜索过滤钱包
function filterBuyers(type) {
  const query = document.getElementById(type === "internal" ? "searchInternal" : "searchFirstMin").value.trim().toLowerCase();
  const fullList = type === "internal" ? (window.cachedInternalBuyers || []) : (window.cachedFirstMinBuyers || []);

  if (!query) {
    renderBuyersList(type, fullList);
    return;
  }

  const filtered = fullList.filter(b => b.address.toLowerCase().includes(query));
  renderBuyersList(type, filtered);
}

// 复制列表
function copyList(type) {
  if (!currentSingleResult) return;
  let list = [];
  if (type === 'internal') {
    list = currentSingleResult.internal_market.top_buyers.map(b => b.address);
  } else if (type === 'firstMin') {
    list = currentSingleResult.first_minute.top_buyers.map(b => b.address);
  }
  if (list.length === 0) {
    showToast("当前列表为空");
    return;
  }
  copyText(list.join("\n"));
  showToast(`已复制 ${list.length} 个地址！`);
}

function copyAllCurrentWallets() {
  if (!currentSingleResult) return;
  const list = currentSingleResult.all_early_wallets || [];
  copyText(list.join("\n"));
  showToast(`已复制全部 ${list.length} 个早期地址！`);
}

function copyCurrentCA() {
  if (!currentSingleResult) return;
  copyText(currentSingleResult.token.address);
  showToast("CA 地址已复制！");
}

function sendToCrossValidate() {
  if (!currentSingleResult) return;
  switchTab("cross");
  const textarea = document.getElementById("crossCasInput");
  const ca = currentSingleResult.token.address;
  const current = textarea.value.trim();
  if (!current.includes(ca)) {
    textarea.value = current ? `${current}\n${ca}` : ca;
  }
  showToast("已将当前 CA 加入交叉验证池！");
}

// 一键填入所有热门 CA 到交叉验证输入框
function loadAllHotToCross() {
  if (hotTokens.length === 0) {
    showToast("暂无可用的热门代币");
    return;
  }
  const addrs = hotTokens.slice(0, 5).map(t => t.address);
  document.getElementById("crossCasInput").value = addrs.join("\n");
  showToast(`已填入 ${addrs.length} 个 Robinhood 热门代币！`);
}

// 调节最小重合代币数
function adjustOverlap(delta) {
  const input = document.getElementById("minOverlapInput");
  let val = (parseInt(input.value, 10) || 2) + delta;
  if (val < 1) val = 1;
  if (val > 50) val = 50;
  input.value = val;
}

function setOverlap(val) {
  document.getElementById("minOverlapInput").value = val;
}

// 开始交叉碰撞验证
async function startCrossValidation() {
  const rawText = document.getElementById("crossCasInput").value;
  const cas = rawText.split("\n").map(l => l.trim()).filter(l => l.startsWith("0x"));
  if (cas.length < 2) {
    showToast("交叉验证至少需要 2 个有效的 CA 地址");
    return;
  }

  const inputEl = document.getElementById("minOverlapInput");
  const minOverlap = inputEl ? (parseInt(inputEl.value, 10) || 2) : 2;
  const loading = document.getElementById("crossLoading");
  const resultCont = document.getElementById("crossResultContainer");
  const btn = document.getElementById("btnStartCross");

  loading.classList.remove("hidden");
  resultCont.classList.add("hidden");
  btn.disabled = true;

  try {
    const res = await fetch("/api/cross-validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cas: cas, min_overlap: minOverlap, mode: currentCrossMode })
    });
    const json = await res.json();
    if (!res.ok || !json.success) {
      throw new Error(json.detail || "交叉验证请求失败");
    }

    currentCrossResult = json.data;
    renderCrossResult(currentCrossResult);
    resultCont.classList.remove("hidden");
    showToast(`[${currentCrossResult.mode_name}] 验证完成！识别出 ${currentCrossResult.cross_validated_wallets_count} 个重合地址`);
  } catch (err) {
    alert("交叉验证失败: " + err.message);
  } finally {
    loading.classList.add("hidden");
    btn.disabled = false;
  }
}

// 渲染交叉验证结果
function renderCrossResult(data) {
  document.getElementById("statTokensCount").textContent = data.total_tokens_analyzed;
  document.getElementById("statCrossCount").textContent = data.cross_validated_wallets_count;
  document.getElementById("statCabalCount").textContent = data.cabal_count || 0;
  document.getElementById("statSmartCount").textContent = data.smart_money_count || 0;

  const badge = document.getElementById("crossModeBadge");
  if (badge) badge.textContent = data.mode_name || "综合碰撞";

  const walletsList = data.wallets || [];
  // 存入全局与分类捕获池
  walletsList.forEach(w => {
    capturedWalletsSet.add(w.address);
    if (currentCrossMode === "internal" || w.is_cabal) {
      capturedInternalWalletsSet.add(w.address);
    } else {
      capturedExternalWalletsSet.add(w.address);
    }
  });
  updateCapturedPoolUI();

  const tbody = document.getElementById("crossTableBody");
  tbody.innerHTML = "";

  if (walletsList.length === 0) {
    const minOverlapVal = document.getElementById("minOverlapInput") ? document.getElementById("minOverlapInput").value : 2;
    tbody.innerHTML = `
      <tr>
        <td colspan="9" class="p-8 text-center text-gray-500 font-sans">
          在当前【${data.mode_name || '所选模式'}】下，未发现满足重合代币数 ≥ ${minOverlapVal} 的地址。建议调低最小重合数或增加代币样本。
        </td>
      </tr>
    `;
    return;
  }

  walletsList.forEach(w => {
    const tr = document.createElement("tr");
    tr.className = "hover:bg-gray-900/60 transition";

    // 标签样式渲染
    const tagHtml = w.tags.map(t => {
      if (t.includes("Cabal")) return `<span class="px-2 py-0.5 rounded text-[11px] font-sans font-semibold badge-cabal">${t}</span>`;
      if (t.includes("Smart")) return `<span class="px-2 py-0.5 rounded text-[11px] font-sans font-semibold badge-smart">${t}</span>`;
      if (t.includes("Sniper")) return `<span class="px-2 py-0.5 rounded text-[11px] font-sans font-semibold badge-sniper">${t}</span>`;
      return `<span class="px-2 py-0.5 rounded text-[11px] font-sans bg-gray-800 text-gray-300">${t}</span>`;
    }).join(" ");

    // 参与代币标签
    const tokensHtml = w.tokens_participated.map(sym => 
      `<span class="px-1.5 py-0.5 rounded bg-gray-800 text-gray-200 border border-gray-700 text-[10px] font-sans mr-1">${sym}</span>`
    ).join("");

    tr.innerHTML = `
      <td class="p-3 font-mono text-gray-200 flex items-center gap-1.5">
        <a href="https://gmgn.ai/eth/address/${w.wallet_address}" target="_blank" title="点击在 GMGN 平台分析该地址完整交易与持仓" class="text-gray-200 hover:text-green-400 font-semibold flex items-center gap-1 group">
          <span>${w.wallet_address.slice(0, 8)}...${w.wallet_address.slice(-6)}</span>
          <span class="px-1.5 py-0.2 rounded bg-green-500/10 text-green-400 border border-green-500/30 text-[10px] font-sans group-hover:bg-green-500 group-hover:text-black transition">
            GMGN ↗
          </span>
        </a>
        <button onclick="copyText('${w.wallet_address}')" class="text-gray-500 hover:text-green-400" title="复制"><i data-lucide="copy" class="w-3.5 h-3.5"></i></button>
        <a href="https://robinscan.io/address/${w.wallet_address}" target="_blank" class="text-gray-500 hover:text-blue-400" title="在 RobinScan 查看"><i data-lucide="external-link" class="w-3 h-3"></i></a>
      </td>
      <td class="p-3 text-center font-bold text-green-400">${w.overlap_count} / ${data.total_tokens_analyzed}</td>
      <td class="p-3">${tokensHtml}</td>
      <td class="p-3 text-center font-semibold ${w.win_rate_pct >= 70 ? 'text-green-400' : 'text-gray-300'}">${w.win_rate_pct}%</td>
      <td class="p-3 text-center font-bold text-green-400">+${w.average_roi_pct}%</td>
      <td class="p-3"><div class="flex flex-wrap gap-1">${tagHtml}</div></td>
      <td class="p-3 text-center">
        <a href="https://gmgn.ai/eth/address/${w.wallet_address}" target="_blank" class="px-2 py-1 bg-green-600 hover:bg-green-500 text-black font-semibold rounded text-[11px] transition inline-block">导入GMGN</a>
      </td>
    `;
    tbody.appendChild(tr);
  });

  if (window.lucide) lucide.createIcons();
}

// 导出功能
function exportWallets(format) {
  if (!currentCrossResult || currentCrossResult.matched_wallets.length === 0) {
    showToast("暂无可导出的交叉验证数据");
    return;
  }

  const wallets = currentCrossResult.matched_wallets;
  let content = "";
  let mime = "text/plain";
  let filename = `robinhood_wallets_${Date.now()}`;

  if (format === 'csv') {
    filename += ".csv";
    mime = "text/csv;charset=utf-8;";
    content = "Wallet,OverlapCount,Tokens,WinRatePct,AvgROIPct,Tags\n";
    wallets.forEach(w => {
      content += `"${w.wallet_address}",${w.overlap_count},"${w.tokens_participated.join('/')}",${w.win_rate_pct}%,${w.average_roi_pct}%,"${w.tags.join(';')}"\n`;
    });
  } else if (format === 'gmgn') {
    // GMGN / 常见跟单机器人批量导入格式 (地址 备注)
    filename += "_gmgn_monitor.txt";
    wallets.forEach(w => {
      const tag = w.tags[0] || "EarlyTrader";
      content += `${w.wallet_address} #RH_${tag}_Hit${w.overlap_count}_Win${w.win_rate_pct}%\n`;
    });
  }

  downloadFile(content, filename, mime);
  showToast(`已导出 ${wallets.length} 个精选钱包！`);
}

function downloadFile(content, filename, mime) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// 捕获池维护 (区分内盘地址池与外盘地址池)
function updateCapturedPoolUI() {
  const internalList = Array.from(capturedInternalWalletsSet);
  const externalList = Array.from(capturedExternalWalletsSet);
  const allList = Array.from(new Set([...internalList, ...externalList, ...Array.from(capturedWalletsSet)]));

  const totalEl = document.getElementById("totalCapturedCount");
  if (totalEl) totalEl.textContent = allList.length;

  const countIntEl = document.getElementById("countInternalVault");
  if (countIntEl) countIntEl.textContent = internalList.length;

  const countExtEl = document.getElementById("countExternalVault");
  if (countExtEl) countExtEl.textContent = externalList.length;

  const areaInt = document.getElementById("vaultInternalTextarea");
  if (areaInt) areaInt.value = internalList.join("\n");

  const areaExt = document.getElementById("vaultExternalTextarea");
  if (areaExt) areaExt.value = externalList.join("\n");
}

function clearCapturedPool() {
  capturedInternalWalletsSet.clear();
  capturedExternalWalletsSet.clear();
  capturedWalletsSet.clear();
  updateCapturedPoolUI();
  showToast("钱包分类缓存已全部清空");
}

// 分类复制 (内盘 或 外盘)
function copyVaultCategory(type) {
  const list = type === 'internal' 
    ? Array.from(capturedInternalWalletsSet) 
    : Array.from(capturedExternalWalletsSet);
  const typeName = type === 'internal' ? "内盘潜伏" : "外盘首分钟";

  if (list.length === 0) {
    showToast(`暂无捕获的${typeName}地址`);
    return;
  }
  copyText(list.join("\n"));
  showToast(`已复制 ${list.length} 个${typeName}地址！`);
}

// 一键复制全部去重地址
function copyAllVault() {
  const allList = Array.from(new Set([...capturedInternalWalletsSet, ...capturedExternalWalletsSet, ...capturedWalletsSet]));
  if (allList.length === 0) {
    showToast("当前池中暂无可复制的地址");
    return;
  }
  copyText(allList.join("\n"));
  showToast(`已复制全部 ${allList.length} 个去重早期地址！`);
}

// 复制通用函数
function copyText(str) {
  navigator.clipboard.writeText(str).then(() => {
    showToast("已复制到剪贴板");
  }).catch(() => {
    const input = document.createElement("textarea");
    input.value = str;
    document.body.appendChild(input);
    input.select();
    document.execCommand("copy");
    document.body.removeChild(input);
    showToast("已复制到剪贴板");
  });
}
