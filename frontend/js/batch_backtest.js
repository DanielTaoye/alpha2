// 批量回测系统 - JavaScript
const API_BASE_URL = '/api';

let allStockGroups = {};
let isRunning = false;
let importedStocksCache = [];
let currentJobId = null;
let interruptRequested = false;

function clampInt(v, min, max, fallback) {
    const n = Number.parseInt(String(v), 10);
    if (Number.isNaN(n)) return fallback;
    return Math.max(min, Math.min(max, n));
}

function loadScriptOnce(src) {
    return new Promise((resolve, reject) => {
        // 如果已经有同 src 的脚本，不重复加载
        const existing = Array.from(document.getElementsByTagName('script')).find(s => s.src && s.src.includes(src));
        if (existing) {
            existing.addEventListener('load', () => resolve());
            existing.addEventListener('error', () => reject(new Error(`加载脚本失败: ${src}`)));
            // 如果已经加载完毕
            if (existing.readyState === 'complete' || existing.readyState === 'loaded') {
                return resolve();
            }
            return;
        }

        const script = document.createElement('script');
        script.src = src;
        script.async = true;
        script.onload = () => resolve();
        script.onerror = () => reject(new Error(`加载脚本失败: ${src}`));
        document.head.appendChild(script);
    });
}

async function ensureXLSXLoaded() {
    if (typeof XLSX !== 'undefined') return;
    // 先尝试本地同源
    try {
        await loadScriptOnce('js/lib/xlsx.full.min.js?v=0.18.5');
    } catch (err) {
        console.warn('本地 xlsx.full.min.js 加载失败，尝试 CDN', err);
    }
    if (typeof XLSX !== 'undefined') return;
    // 再尝试 CDN 兜底（如果生产策略拦截 CDN，仍可能失败）
    try {
        await loadScriptOnce('https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js');
    } catch (err) {
        console.warn('CDN xlsx.full.min.js 加载失败', err);
    }
    if (typeof XLSX === 'undefined') {
        throw new Error('Excel解析库未加载，请部署 js/lib/xlsx.full.min.js 或放行 CDN');
    }
}

// 旧版：前端并发跑每只股票的 cr_analysis/backtest
// 现已改为“后端批处理任务”，保留 backtestSingleStock 仅用于调试单股

// fetch with timeout (ms)
async function fetchWithTimeout(url, options = {}, timeout = 20000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
        const resp = await fetch(url, { ...options, signal: controller.signal });
        return resp;
    } finally {
        clearTimeout(timer);
    }
}

async function fetchJsonWithRetry(url, options, timeoutMs, retries = 1) {
    let lastErr = null;
    for (let attempt = 0; attempt <= retries; attempt++) {
        try {
            const resp = await fetchWithTimeout(url, options, timeoutMs);
            return resp;
        } catch (err) {
            lastErr = err;
            // 超时/网络抖动：做一次退避重试，避免“并发瞬间排队”导致全灭
            if (err && err.name === 'AbortError' && attempt < retries) {
                await sleep(800 * (attempt + 1));
                continue;
            }
            throw err;
        }
    }
    throw lastErr;
}

async function readCsvStocks(file) {
    const text = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result || '');
        reader.onerror = () => reject(new Error('读取CSV失败'));
        reader.readAsText(file, 'utf-8');
    });
    const lines = String(text).split(/\r?\n/).map(l => l.trim()).filter(Boolean);
    return parseRowsToStocks(lines.map(line => line.split(',').map(s => s.trim())));
}

function parseRowsToStocks(rows) {
    if (!rows || rows.length === 0) return [];
    const header = rows[0].map(s => s.trim());
    const hasHeader = header.some(h => ['code', 'stockcode', 'stock_code'].includes(h.toLowerCase()));
    const codeIdx = hasHeader
        ? header.findIndex(h => ['code', 'stockcode', 'stock_code'].includes(h.toLowerCase()))
        : 0;
    const dataRows = hasHeader ? rows.slice(1) : rows;
    const codes = [];
    for (const cols of dataRows) {
        const code = (cols[codeIdx] || '').replace(/[^0-9a-zA-Z]/g, '').toUpperCase();
        if (code) codes.push(code);
    }
    const uniq = Array.from(new Set(codes));
    return uniq.map(code => ({
        code,
        name: code,
        table_name: `basic_data_${code.toLowerCase()}`
    }));
}

async function readExcelStocks(file) {
    await ensureXLSXLoaded();
    const data = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = e => resolve(new Uint8Array(e.target.result));
        reader.onerror = () => reject(new Error('读取Excel失败'));
        reader.readAsArrayBuffer(file);
    });
    const wb = XLSX.read(data, { type: 'array' });
    const sheetName = wb.SheetNames[0];
    if (!sheetName) return [];
    const sheet = wb.Sheets[sheetName];
    const rows = XLSX.utils.sheet_to_json(sheet, { header: 1, raw: false });
    // rows 形如 [ [col1,col2,...], ... ]
    return parseRowsToStocks(rows);
}

async function readFileStocks(file) {
    const ext = (file.name.split('.').pop() || '').toLowerCase();
    if (ext === 'csv') {
        return readCsvStocks(file);
    }
    if (ext === 'xlsx' || ext === 'xls') {
        if (typeof XLSX === 'undefined') {
            throw new Error('Excel解析库未加载，请确保部署了 js/lib/xlsx.full.min.js');
        }
        return readExcelStocks(file);
    }
    throw new Error('仅支持 CSV / XLSX / XLS');
}

function renderImportSummary(stocks) {
    const el = document.getElementById('importSummary');
    if (!el) return;
    if (!stocks || stocks.length === 0) {
        el.textContent = '尚未导入文件或文件为空';
        el.style.color = '#e74c3c';
        return;
    }
    const preview = stocks.slice(0, 10).map(s => s.code).join(', ');
    const more = stocks.length > 10 ? ` ... 共${stocks.length}只` : ` 共${stocks.length}只`;
    el.textContent = `已导入股票: ${preview}${more}`;
    el.style.color = '#333';
}

async function handleFileChange(ev) {
    const file = ev.target.files?.[0];
    if (!file) {
        importedStocksCache = [];
        renderImportSummary([]);
        return;
    }
    try {
        const stocks = await readFileStocks(file);
        importedStocksCache = stocks;
        renderImportSummary(stocks);
    } catch (err) {
        importedStocksCache = [];
        renderImportSummary([]);
        showError(err.message || '文件解析失败');
    }
}

// 初始化
async function init() {
    try {
        updateStatus(false, '正在连接服务器...');
        
        const response = await fetch(`${API_BASE_URL}/stock_groups`);
        const result = await response.json();
        
        if (result.code === 200) {
            allStockGroups = result.data;
            updateStatus(true, `系统就绪 - 已加载 ${getTotalStockCount()} 支股票`);
        } else {
            throw new Error(result.message || '获取数据失败');
        }
    } catch (error) {
        console.error('初始化失败:', error);
        updateStatus(false, '服务器连接失败');
        showError('系统初始化失败: ' + error.message);
    }
    // 绑定文件选择监听，实时展示导入摘要
    const fileInput = document.getElementById('csvFile');
    if (fileInput) {
        fileInput.addEventListener('change', handleFileChange);
    }
}

// 获取总股票数
function getTotalStockCount() {
    let count = 0;
    for (const stocks of Object.values(allStockGroups)) {
        count += stocks.length;
    }
    return count;
}

// 更新状态指示器
function updateStatus(online, text) {
    const indicator = document.getElementById('status-indicator');
    const statusText = document.getElementById('status-text');
    
    if (indicator && statusText) {
        indicator.className = online ? 'status-indicator online' : 'status-indicator offline';
        statusText.textContent = text;
    }
}

// 显示错误信息
function showError(message) {
    const errorDiv = document.getElementById('errorMessage');
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
    
    setTimeout(() => {
        errorDiv.style.display = 'none';
    }, 5000);
}

// 开始批量回测
async function startBatchBacktest() {
    if (isRunning) {
        showError('回测正在进行中，请稍候...');
        return;
    }

    const strategySelect = document.getElementById('strategySelect');
    const strategy = strategySelect.value;
    const concurrency = clampInt(document.getElementById('btConcurrency')?.value, 1, 50, 50);

    // 回测配置（与个股页一致）
    const startDate = document.getElementById('btStartDate')?.value || '';
    const endDate = document.getElementById('btEndDate')?.value || '';
    const onlyGoldenC = !!document.getElementById('btOnlyGolden')?.checked;
    const engine = document.getElementById('btEngine')?.value || 'legacy';

    const backtestConfig = {
        startDate: startDate || null,
        endDate: endDate || null,
        onlyGoldenC,
        engine
    };

    if (!strategy) {
        showError('请选择股性分组（用于套用阈值）');
        return;
    }

    // 获取股票列表
    let stocks = [];
    const csvFile = document.getElementById('csvFile');
    const file = csvFile?.files?.[0];
    if (importedStocksCache.length === 0) {
        if (!file) {
            showError('请选择文件');
            return;
        }
        stocks = await readFileStocks(file);
        importedStocksCache = stocks;
    } else {
        stocks = importedStocksCache;
    }
    if (stocks.length === 0) {
        showError('文件里没有解析到股票代码');
        return;
    }

    const selectedStocks = stocks; // 不再截断数量

    isRunning = true;
    interruptRequested = false;
    currentJobId = null;
    
    // 显示进度条
    const progressContainer = document.getElementById('progressContainer');
    const resultsContainer = document.getElementById('resultsContainer');
    progressContainer.style.display = 'block';
    resultsContainer.style.display = 'none';
    
    // 禁用按钮
    const runBtn = document.getElementById('runBtn');
    const stopBtn = document.getElementById('stopBtn');
    runBtn.disabled = true;
    runBtn.innerHTML = '<span class="loading-spinner"></span> 回测中...';
    if (stopBtn) {
        stopBtn.style.display = 'inline-block';
        stopBtn.disabled = false;
        stopBtn.textContent = '打断';
    }
    
    // 执行批量回测（推荐：由后端统一调度，前端只轮询进度，避免前端高并发/大量HTTP请求）
    let successCount = 0;
    let failCount = 0;
    let skippedCount = 0;

    try {
        const nature = strategy || '波段';
        const startResp = await fetchJsonWithRetry(`${API_BASE_URL}/batch_backtest/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                stocks: selectedStocks,
                stockNature: nature,
                period: 'day',
                concurrency,
                // 批量默认只要 summary（不带 trades），避免结果过大导致轮询/渲染超时
                resultMode: 'summary',
                backtestConfig
            })
        }, 60000, 0);

        const startJson = await startResp.json();
        if (!startJson || startJson.code !== 200 || !startJson.data || !startJson.data.jobId) {
            throw new Error(startJson?.message || '启动批量回测失败');
        }

        const jobId = startJson.data.jobId;
        currentJobId = jobId;

        // 轮询任务状态
        let results = [];
        while (true) {
            await sleep(800);
            // 轮询只拿“轻量进度”，不带 results（否则返回体会随任务进行越来越大，触发20s超时）
            const stResp = await fetchWithTimeout(`${API_BASE_URL}/batch_backtest/status/${jobId}?includeResults=0`, {}, 20000);
            const stJson = await stResp.json();
            if (!stJson || stJson.code !== 200) {
                continue;
            }
            const st = stJson.data || {};
            const finished = st.finished || 0;
            const total = st.total || selectedStocks.length;
            const progress = total > 0 ? ((finished) / total * 100).toFixed(1) : '0.0';

            const stMessage = st.cancelled
                ? `已打断：已完成 ${finished}/${total}（展示已完成数据）`
                : `后端任务处理中：已完成 ${finished}/${total}（并发=${concurrency}）`;
            updateProgress(progress, stMessage);

            // 前端发起了打断：一旦后端标记 done/cancelled，就退出轮询并展示已完成数据
            if (st.done) {
                successCount = st.success || 0;
                failCount = st.failed || 0;
                skippedCount = st.skipped || 0;
                break;
            }
        }

        // 任务结束后再拉一次完整 results（只拉一次，避免轮询期间超大payload）
        try {
            const finalResp = await fetchWithTimeout(`${API_BASE_URL}/batch_backtest/status/${jobId}?includeResults=1`, {}, 60000);
            const finalJson = await finalResp.json();
            const stFinal = (finalJson && finalJson.code === 200) ? (finalJson.data || {}) : {};
            if (Array.isArray(stFinal.results)) {
                results = stFinal.results;
            }
        } catch (e) {
            console.warn('获取最终结果失败，将尝试用空结果展示：', e);
        }

        // 隐藏进度条
        progressContainer.style.display = 'none';

        // 显示结果（无论完成还是取消，都展示已完成数据）
        try {
            displayResults(results, successCount, failCount, skippedCount);
        } catch (e) {
            console.error('displayResults 渲染异常:', e);
            showError('结果渲染异常（已在控制台输出错误），请稍后重试或降低并发数');
        }

        updateStatus(true, interruptRequested ? '已打断（已展示已完成数据）' : '回测完成');
    } catch (err) {
        console.error(err);
        showError(err?.message || '批量回测失败');
        updateStatus(false, '回测失败');
    } finally {
        // 恢复按钮/状态
        runBtn.disabled = false;
        runBtn.innerHTML = '开始批量回测';
        if (stopBtn) {
            stopBtn.disabled = true;
            stopBtn.style.display = 'none';
            stopBtn.textContent = '打断';
        }
        isRunning = false;
        currentJobId = null;
        interruptRequested = false;
    }
}

// 打断批量回测：调用后端 cancel 接口；已完成的数据仍可在 status 里拿到并展示
async function interruptBatchBacktest() {
    if (!isRunning) return;
    if (!currentJobId) {
        showError('任务尚未启动完成，请稍候...');
        return;
    }
    if (interruptRequested) return;
    interruptRequested = true;

    const stopBtn = document.getElementById('stopBtn');
    if (stopBtn) {
        stopBtn.disabled = true;
        stopBtn.textContent = '正在打断...';
    }

    try {
        await fetchWithTimeout(`${API_BASE_URL}/batch_backtest/cancel/${currentJobId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        }, 10000);
        // 轮询逻辑会在 st.done 时自动展示已完成数据
    } catch (err) {
        // 即便 cancel 请求失败，也让轮询继续；用户可再次点击（这里保持 interruptRequested=true 防抖）
        console.warn('取消请求失败:', err);
        showError('打断请求发送失败（可稍后重试）');
    }
}

// 回测单个股票（调试用：批量回测已改为后端任务）
async function backtestSingleStock(stock, stockNature, backtestConfig) {
    try {
        console.log('开始回测股票:', stock.code, stock.name);

        // 批量场景：接口计算时间可能明显 > 20s（尤其是排队/单线程后端）
        // 这里统一把单请求超时拉长，减少误判
        const requestTimeoutMs = 60000;
        
        // 首先获取CR点数据
        const requestBody = {
            stockCode: stock.code,
            stockName: stock.name,
            tableName: stock.table_name,
            period: 'day',
            stockNature: stockNature,
            // 传给后端用于按区间截断K线范围，加速 /cr_analysis
            startDate: backtestConfig?.startDate || null,
            endDate: backtestConfig?.endDate || null
        };
        
        console.log('CR分析请求参数:', requestBody);
        
        const crResponse = await fetchJsonWithRetry(`${API_BASE_URL}/cr_analysis`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        }, requestTimeoutMs, 1);
        
        console.log('CR分析响应状态:', crResponse.status, crResponse.statusText);
        
        // 检查响应是否是JSON
        const contentType = crResponse.headers.get('content-type');
        console.log('CR分析响应Content-Type:', contentType);
        
        if (!contentType || !contentType.includes('application/json')) {
            const text = await crResponse.text();
            console.error('API返回非JSON响应:', text.substring(0, 500));
            throw new Error(`API返回格式错误 (状态码: ${crResponse.status})`);
        }
        
        const crResult = await crResponse.json();
        console.log('CR分析结果:', crResult);
        
        if (crResult.code !== 200) {
            console.error('CR分析失败:', crResult.message);
            throw new Error(crResult.message || 'CR分析失败');
        }
        
        const cPoints = crResult.data.c_points || [];
        const cPointsS2 = crResult.data.strategy2_c_points || [];
        const mergedCPoints = [...cPoints, ...cPointsS2];
        const rPoints = crResult.data.r_points || [];
        
        console.log(`找到C点${mergedCPoints.length}个(策略1:${cPoints.length} / 策略2:${cPointsS2.length}), R点${rPoints.length}个`);
        
        if (mergedCPoints.length === 0) {
            console.warn('没有C点数据，跳过回测');
            return {
                success: true,
                skipped: true,
                message: '没有C点数据(已跳过)'
            };
        }
        
        // 执行回测
        const backtestResponse = await fetchJsonWithRetry(`${API_BASE_URL}/backtest`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                stockCode: stock.code,
                tableName: stock.table_name,
                cPoints: mergedCPoints,
                rPoints: rPoints,
                backtestConfig
            })
        }, requestTimeoutMs, 1);
        
        // 检查响应是否是JSON
        const contentType2 = backtestResponse.headers.get('content-type');
        if (!contentType2 || !contentType2.includes('application/json')) {
            const text = await backtestResponse.text();
            console.error('回测API返回非JSON响应:', text.substring(0, 200));
            throw new Error('回测API返回格式错误');
        }
        
        const backtestResult = await backtestResponse.json();
        
        if (backtestResult.code === 200) {
            const tradesArr = backtestResult.data && Array.isArray(backtestResult.data.trades) ? backtestResult.data.trades : [];
            if (!tradesArr.length) {
                return {
                    success: true,
                    skipped: true,
                    message: '无CR配对(已跳过)'
                };
            }
            return {
                success: true,
                skipped: false,
                data: backtestResult.data
            };
        } else {
            return {
                success: false,
                message: backtestResult.message || '回测失败'
            };
        }
        
    } catch (error) {
        console.error('回测失败:', stock.code, error);
        if (error.name === 'AbortError') {
            return {
                success: false,
                message: '接口超时(60s)'
            };
        }
        return {
            success: false,
            message: error.message
        };
    }
}

// 更新进度条
function updateProgress(percent, text) {
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    
    progressFill.style.width = percent + '%';
    progressFill.textContent = percent + '%';
    progressText.textContent = text;
}

// 显示结果
function displayResults(results, successCount, failCount, skippedCount = 0) {
    const resultsContainer = document.getElementById('resultsContainer');
    resultsContainer.style.display = 'block';
    
    // 兜底：没有任何可展示的结果时，给出提示
    if (!Array.isArray(results) || results.length === 0) {
        document.getElementById('totalStocks').textContent = 0;
        document.getElementById('avgReturn').textContent = '0%';
        document.getElementById('returnSumAll').textContent = '0%';
        document.getElementById('totalTrades').textContent = 0;
        document.getElementById('avgWinRate').textContent = '0%';
        document.getElementById('successCount').textContent = successCount || 0;
        document.getElementById('failCount').textContent = failCount || 0;
        document.getElementById('avgHoldingDaysStocks').textContent = `0天`;
        const tableBody = document.getElementById('resultsTableBody');
        tableBody.innerHTML = `<tr><td colspan="10" style="color:#999;">暂无可展示结果（可能全部超时/失败，或后端任务异常）</td></tr>`;
        resultsContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return;
    }

    // 计算汇总数据
    // 注意：统计/平均值只基于“真正跑出回测数据”的股票：
    // - success=true 且 skipped=false 且 data.summary 存在（后端保证此时 trades 非空）
    const successResults = results.filter(r => r && r.success && !r.skipped);
    const statResults = successResults.filter(r => r.data && r.data.summary);
    
    let totalTrades = 0;
    let totalReturnSum = 0;
    let avgReturnSum = 0;
    let winRateSum = 0;
    let holdingDaysSum = 0;
    
    statResults.forEach(r => {
        if (r.data && r.data.summary) {
            totalTrades += r.data.summary.total_trades || 0;
            totalReturnSum += (r.data.summary.return_sum ?? r.data.summary.total_return ?? 0);
            avgReturnSum += r.data.summary.avg_return || 0;
            winRateSum += r.data.summary.win_rate || 0;
            holdingDaysSum += r.data.summary.avg_holding_days || 0;
        }
    });
    
    const denom = statResults.length;
    const avgReturn = denom > 0 ? (avgReturnSum / denom).toFixed(2) : 0;
    const avgWinRate = denom > 0 ? (winRateSum / denom).toFixed(2) : 0;
    const avgHoldingDaysStocks = denom > 0 ? (holdingDaysSum / denom).toFixed(2) : 0;
    
    // 更新汇总卡片
    document.getElementById('totalStocks').textContent = results.length;
    document.getElementById('avgReturn').textContent = avgReturn + '%';
    document.getElementById('avgReturn').className = avgReturn >= 0 ? 'positive' : 'negative';
    document.getElementById('returnSumAll').textContent = totalReturnSum.toFixed(2) + '%';
    document.getElementById('returnSumAll').className = totalReturnSum >= 0 ? 'positive' : 'negative';
    document.getElementById('totalTrades').textContent = totalTrades;
    document.getElementById('avgWinRate').textContent = avgWinRate + '%';
    document.getElementById('successCount').textContent = successCount;
    document.getElementById('failCount').textContent = failCount;
    // 复用“失败股票数”卡片的 title 不改UI结构：在数字后面附带跳过数（避免大改页面）
    const failEl = document.getElementById('failCount');
    if (failEl && skippedCount > 0) {
        failEl.textContent = `${failCount}（跳过${skippedCount}）`;
    }
    document.getElementById('avgHoldingDaysStocks').textContent = `${avgHoldingDaysStocks}天`;
    
    // 填充表格
    const tableBody = document.getElementById('resultsTableBody');
    tableBody.innerHTML = '';
    
    results.forEach((result, index) => {
        const row = document.createElement('tr');

        // 安全获取股票代码（后端可能返回 dict 或字符串）
        const stockObj = result && result.stock;
        const stockCode = (stockObj && typeof stockObj === 'object')
            ? (stockObj.code || stockObj.stockCode || stockObj.stock_code || '未知')
            : (stockObj ? String(stockObj) : '未知');
        
        if (result.success && result.skipped) {
            const cells = [
                index + 1,
                stockCode,
            ];
            row.innerHTML = cells.map(cell => `<td>${cell}</td>`).join('') +
                `<td colspan="8" style="color: #999;">
                    <span style="color: #f39c12; font-weight: bold;">⏭ 跳过</span> - ${result.message || '无可回测的CR配对'}
                </td>`;
        } else if (result.success && result.data && result.data.summary) {
            const summary = result.data.summary;
            const totalReturn = summary.total_return || 0;
            const avgReturn = summary.avg_return || 0;
            const winRate = summary.win_rate || 0;
            const maxReturn = summary.max_return || 0;
            const minReturn = summary.min_return || 0;
            const avgHoldingDays = summary.avg_holding_days || 0;
            
            const cells = [
                index + 1,
                stockCode,
                summary.total_trades || 0,
                `<span class="${totalReturn >= 0 ? 'positive' : 'negative'}">${totalReturn.toFixed(2)}%</span>`,
                `<span class="${avgReturn >= 0 ? 'positive' : 'negative'}">${avgReturn.toFixed(2)}%</span>`,
                `${winRate.toFixed(2)}%`,
                `<span class="positive">${maxReturn.toFixed(2)}%</span>`,
                `<span class="negative">${minReturn.toFixed(2)}%</span>`,
                `${avgHoldingDays.toFixed(2)}天`,
                '<span style="color: #27ae60; font-weight: bold;">✓ 成功</span>'
            ];
            
            row.innerHTML = cells.map(cell => `<td>${cell}</td>`).join('');
        } else {
            const cells = [
                index + 1,
                stockCode
            ];
            
            row.innerHTML = cells.map(cell => `<td>${cell}</td>`).join('') + 
                `<td colspan="8" style="color: #999;">
                    <span style="color: #e74c3c; font-weight: bold;">✗ 失败</span> - ${result.error || result.message || '未知错误'}
                </td>`;
        }
        
        tableBody.appendChild(row);
    });
    
    // 滚动到结果区域
    resultsContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// 睡眠函数
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// 页面加载完成后初始化
window.addEventListener('DOMContentLoaded', init);

