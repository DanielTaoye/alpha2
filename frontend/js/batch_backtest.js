// 批量回测系统 - JavaScript
const API_BASE_URL = '/api';

let allStockGroups = {};
let isRunning = false;

function getSelectedMode() {
    const modeEl = document.querySelector('input[name="btMode"]:checked');
    return modeEl ? modeEl.value : 'group';
}

function bindModeUI() {
    const radios = document.querySelectorAll('input[name="btMode"]');
    const csvFile = document.getElementById('csvFile');
    const csvHint = document.getElementById('csvHint');
    const strategySelect = document.getElementById('strategySelect');
    if (!radios.length) return;

    const refresh = () => {
        const mode = getSelectedMode();
        const isCsv = mode === 'csv';
        if (csvFile) csvFile.style.display = isCsv ? 'inline-block' : 'none';
        if (csvHint) csvHint.style.display = isCsv ? 'inline-block' : 'none';
        if (strategySelect) strategySelect.disabled = isCsv;
    };

    radios.forEach(r => r.addEventListener('change', refresh));
    refresh();
}

async function readCsvStocks(file) {
    const text = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result || '');
        reader.onerror = () => reject(new Error('读取CSV失败'));
        reader.readAsText(file, 'utf-8');
    });

    const lines = String(text).split(/\r?\n/).map(l => l.trim()).filter(Boolean);
    if (lines.length === 0) return [];

    // 简单CSV解析：支持 header（code/stockCode）或第一列直接是代码
    const header = lines[0].split(',').map(s => s.trim());
    const hasHeader = header.some(h => ['code', 'stockcode', 'stock_code'].includes(h.toLowerCase()));
    const codeIdx = hasHeader
        ? header.findIndex(h => ['code', 'stockcode', 'stock_code'].includes(h.toLowerCase()))
        : 0;

    const dataLines = hasHeader ? lines.slice(1) : lines;
    const codes = [];
    for (const line of dataLines) {
        const cols = line.split(',').map(s => s.trim());
        const code = (cols[codeIdx] || '').replace(/[^0-9a-zA-Z]/g, '').toUpperCase();
        if (code) codes.push(code);
    }

    // 去重
    const uniq = Array.from(new Set(codes));
    return uniq.map(code => ({
        code,
        name: code,
        table_name: `basic_data_${code.toLowerCase()}`
    }));
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
            bindModeUI();
        } else {
            throw new Error(result.message || '获取数据失败');
        }
    } catch (error) {
        console.error('初始化失败:', error);
        updateStatus(false, '服务器连接失败');
        showError('系统初始化失败: ' + error.message);
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
    const stockLimit = parseInt(document.getElementById('stockLimit').value) || 20;
    const strategy = strategySelect.value;

    // 回测配置（与个股页一致）
    const startMonth = document.getElementById('btStartDate')?.value || '';
    const endMonth = document.getElementById('btEndDate')?.value || '';
    const exitAfterDaysRaw = document.getElementById('btExitAfterDays')?.value;
    const onlyGoldenC = !!document.getElementById('btOnlyGolden')?.checked;
    const engine = document.getElementById('btEngine')?.value || 'legacy';

    const backtestConfig = {
        startDate: startMonth ? `${startMonth}-01` : null,
        endDate: endMonth ? `${endMonth}-31` : null,
        exitAfterDays: exitAfterDaysRaw ? parseInt(exitAfterDaysRaw, 10) : null,
        onlyGoldenC,
        engine
    };
    
    const mode = getSelectedMode();
    if (mode === 'group' && !strategy) {
        showError('请选择股性分组');
        return;
    }

    // 获取股票列表
    let stocks = [];
    if (mode === 'csv') {
        const csvFile = document.getElementById('csvFile');
        const file = csvFile?.files?.[0];
        if (!file) {
            showError('请选择CSV文件');
            return;
        }
        stocks = await readCsvStocks(file);
        if (stocks.length === 0) {
            showError('CSV里没有解析到股票代码');
            return;
        }
    } else {
        if (strategy === 'all') {
            // 合并所有策略的股票
            for (const strategyStocks of Object.values(allStockGroups)) {
                stocks = stocks.concat(strategyStocks);
            }
        } else {
            stocks = allStockGroups[strategy] || [];
        }
    }
    
    if (stocks.length === 0) {
        showError('该分组没有股票数据');
        return;
    }

    // 限制股票数量
    const selectedStocks = stocks.slice(0, stockLimit);
    
    isRunning = true;
    
    // 显示进度条
    const progressContainer = document.getElementById('progressContainer');
    const resultsContainer = document.getElementById('resultsContainer');
    progressContainer.style.display = 'block';
    resultsContainer.style.display = 'none';
    
    // 禁用按钮
    const runBtn = document.getElementById('runBtn');
    runBtn.disabled = true;
    runBtn.innerHTML = '<span class="loading-spinner"></span> 回测中...';
    
    // 执行批量回测
    const results = [];
    let successCount = 0;
    let failCount = 0;
    
    for (let i = 0; i < selectedStocks.length; i++) {
        const stock = selectedStocks[i];
        const progress = ((i + 1) / selectedStocks.length * 100).toFixed(1);
        
        updateProgress(progress, `正在回测: ${stock.name} (${stock.code}) - ${i + 1}/${selectedStocks.length}`);
        
        try {
            const nature = mode === 'csv' ? (strategy || '波段') : strategy;
            const result = await backtestSingleStock(stock, nature, backtestConfig);
            if (result.success) {
                successCount++;
                results.push({
                    stock: stock,
                    data: result.data,
                    success: true
                });
            } else {
                failCount++;
                results.push({
                    stock: stock,
                    error: result.message,
                    success: false
                });
            }
        } catch (error) {
            failCount++;
            results.push({
                stock: stock,
                error: error.message,
                success: false
            });
        }
        
        // 避免请求过快
        await sleep(100);
    }
    
    // 隐藏进度条
    progressContainer.style.display = 'none';
    
    // 显示结果
    displayResults(results, successCount, failCount);
    
    // 恢复按钮
    runBtn.disabled = false;
    runBtn.innerHTML = '开始批量回测';
    isRunning = false;
    
    updateStatus(true, '回测完成');
}

// 回测单个股票
async function backtestSingleStock(stock, stockNature, backtestConfig) {
    try {
        console.log('开始回测股票:', stock.code, stock.name);
        
        // 首先获取CR点数据
        const requestBody = {
            stockCode: stock.code,
            stockName: stock.name,
            tableName: stock.table_name,
            period: 'day',
            stockNature: stockNature
        };
        
        console.log('CR分析请求参数:', requestBody);
        
        const crResponse = await fetch(`${API_BASE_URL}/cr_analysis`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });
        
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
        const rPoints = crResult.data.r_points || [];
        
        console.log(`找到C点${cPoints.length}个, R点${rPoints.length}个`);
        
        if (cPoints.length === 0) {
            console.warn('没有C点数据，跳过回测');
            return {
                success: false,
                message: '没有C点数据'
            };
        }
        
        // 执行回测
        const backtestResponse = await fetch(`${API_BASE_URL}/backtest`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                stockCode: stock.code,
                tableName: stock.table_name,
                cPoints: cPoints,
                rPoints: rPoints,
                backtestConfig
            })
        });
        
        // 检查响应是否是JSON
        const contentType2 = backtestResponse.headers.get('content-type');
        if (!contentType2 || !contentType2.includes('application/json')) {
            const text = await backtestResponse.text();
            console.error('回测API返回非JSON响应:', text.substring(0, 200));
            throw new Error('回测API返回格式错误');
        }
        
        const backtestResult = await backtestResponse.json();
        
        if (backtestResult.code === 200) {
            return {
                success: true,
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
function displayResults(results, successCount, failCount) {
    const resultsContainer = document.getElementById('resultsContainer');
    resultsContainer.style.display = 'block';
    
    // 计算汇总数据
    const successResults = results.filter(r => r.success);
    
    let totalTrades = 0;
    let totalReturnSum = 0;
    let avgReturnSum = 0;
    let winRateSum = 0;
    
    successResults.forEach(r => {
        if (r.data && r.data.summary) {
            totalTrades += r.data.summary.total_trades || 0;
            totalReturnSum += (r.data.summary.return_sum ?? r.data.summary.total_return ?? 0);
            avgReturnSum += r.data.summary.avg_return || 0;
            winRateSum += r.data.summary.win_rate || 0;
        }
    });
    
    const avgReturn = successResults.length > 0 ? (avgReturnSum / successResults.length).toFixed(2) : 0;
    const avgWinRate = successResults.length > 0 ? (winRateSum / successResults.length).toFixed(2) : 0;
    
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
    
    // 填充表格
    const tableBody = document.getElementById('resultsTableBody');
    tableBody.innerHTML = '';
    
    results.forEach((result, index) => {
        const row = document.createElement('tr');
        
        if (result.success && result.data && result.data.summary) {
            const summary = result.data.summary;
            const totalReturn = summary.total_return || 0;
            const avgReturn = summary.avg_return || 0;
            const winRate = summary.win_rate || 0;
            const maxReturn = summary.max_return || 0;
            const minReturn = summary.min_return || 0;
            
            // 创建每个单元格
            const cells = [
                index + 1,
                result.stock?.code || '未知',
                result.stock?.name || '未知',
                summary.total_trades || 0,
                `<span class="${totalReturn >= 0 ? 'positive' : 'negative'}">${totalReturn.toFixed(2)}%</span>`,
                `<span class="${avgReturn >= 0 ? 'positive' : 'negative'}">${avgReturn.toFixed(2)}%</span>`,
                `${winRate.toFixed(2)}%`,
                `<span class="positive">${maxReturn.toFixed(2)}%</span>`,
                `<span class="negative">${minReturn.toFixed(2)}%</span>`,
                '<span style="color: #27ae60; font-weight: bold;">✓ 成功</span>'
            ];
            
            row.innerHTML = cells.map(cell => `<td>${cell}</td>`).join('');
        } else {
            // 失败的情况
            const cells = [
                index + 1,
                result.stock.code || '未知',
                result.stock.name || '未知'
            ];
            
            row.innerHTML = cells.map(cell => `<td>${cell}</td>`).join('') + 
                `<td colspan="7" style="color: #999;">
                    <span style="color: #e74c3c; font-weight: bold;">✗ 失败</span> - ${result.error || '未知错误'}
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

