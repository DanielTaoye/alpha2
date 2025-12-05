// 阿尔法策略2.0系统 - 主应用脚本
const API_BASE_URL = '/api';
let allStockGroups = {};
let currentStrategy = '波段';
let currentStockCode = '';
let currentTableName = '';
let currentPeriod = 'day'; // 当前周期，默认日K线
let availablePeriods = {};
let chart = null;
let currentAnalysisController = null;
let volumeTypeMap = {}; // 存储成交量类型数据，key为日期字符串，value为成交量类型
let winRatioScoreMap = {}; // 存储赔率总分数据，key为日期字符串，value为total_win_ratio_score
let bullishPatternMap = {}; // 存储多头组合数据，key为日期字符串，value为多头组合
let bearishPatternMap = {}; // 存储空头组合数据，key为日期字符串，value为空头组合
let supportPriceMap = {}; // 存储支撑线数据，key为日期字符串，value为支撑价格（整数，需除以100）
let pressurePriceMap = {}; // 存储压力线数据，key为日期字符串，value为压力价格（整数，需除以100）
let autoRefreshInterval = null; // 自动刷新定时器
let predictedVolume = null; // 预测的成交量
let predictedVolumeType = null; // 预测的成交量类型（基于预测成交量实时计算）

// ECharts加载状态检测和等待函数
function waitForECharts(timeout = 15000) {
    return new Promise((resolve, reject) => {
        // 检查 ECharts 是否已经加载并验证
        function isEChartsReady() {
            try {
                return typeof echarts !== 'undefined' 
                    && typeof echarts.init === 'function'
                    && window.echartsLoadStatus === 'success';
            } catch (e) {
                return false;
            }
        }

        // 如果ECharts已经加载，直接返回
        if (isEChartsReady()) {
            console.log('✅ ECharts已就绪');
            resolve(echarts);
            return;
        }

        // 检查是否已经加载失败
        if (window.echartsLoadStatus === 'failed') {
            reject(new Error('ECharts加载失败：所有CDN都不可用'));
            return;
        }

        const startTime = Date.now();
        
        // 定期检查ECharts是否已加载
        const checkInterval = setInterval(() => {
            // 检查是否加载成功
            if (isEChartsReady()) {
                clearInterval(checkInterval);
                console.log('✅ ECharts已就绪');
                resolve(echarts);
                return;
            }
            
            // 检查是否加载失败
            if (window.echartsLoadStatus === 'failed') {
                clearInterval(checkInterval);
                reject(new Error('ECharts加载失败：所有CDN都不可用'));
                return;
            }
            
            // 检查是否超时
            if (Date.now() - startTime > timeout) {
                clearInterval(checkInterval);
                reject(new Error(`ECharts加载超时 (${timeout}ms)，当前状态: ${window.echartsLoadStatus || 'unknown'}`));
            }
        }, 100);
    });
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

// 初始化应用
async function initApp() {
    try {
        updateStatus(false, '正在连接服务器...');
        
        const response = await fetch(`${API_BASE_URL}/stock_groups`);
        const result = await response.json();
        
        if (result.code === 200) {
            allStockGroups = result.data;
            updateStatus(true, `系统运行正常 - 已加载 ${getTotalStockCount()} 支股票`);
            updateStockList();
        } else {
            throw new Error(result.message || '获取数据失败');
        }
    } catch (error) {
        console.error('初始化失败:', error);
        updateStatus(false, '服务器连接失败');
        document.getElementById('app').innerHTML = `
            <div class="error">
                <h2>❌ 系统初始化失败</h2>
                <p>${error.message}</p>
                <p style="margin-top: 15px; font-size: 14px;">
                    请检查：<br>
                    1. 后端服务是否启动（运行 start.bat）<br>
                    2. 数据库连接是否正常<br>
                    3. 配置是否正确
                </p>
                <button onclick="location.reload()" style="margin-top: 20px; padding: 10px 30px; background: #4a90e2; border: none; border-radius: 5px; color: white; cursor: pointer; font-size: 14px;">
                    重新加载
                </button>
            </div>
        `;
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

// 选择策略
function selectStrategy(strategy) {
    currentStrategy = strategy;
    
    // 切换策略时停止自动刷新
    stopAutoRefresh();
    
    document.querySelectorAll('.strategy-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.textContent.includes(strategy)) {
            btn.classList.add('active');
        }
    });

    updateStockList();
    document.getElementById('stockSelect').value = '';
    document.getElementById('searchInput').value = '';
    showEmptyState();
}

// 更新股票列表
function updateStockList() {
    const stockSelect = document.getElementById('stockSelect');
    const stocks = allStockGroups[currentStrategy] || [];
    
    stockSelect.innerHTML = '<option value="">-- 请选择股票 --</option>';
    
    stocks.forEach(stock => {
        const option = document.createElement('option');
        option.value = stock.code;
        option.textContent = `${stock.name} (${stock.code})`;
        option.dataset.name = stock.name;
        option.dataset.table = stock.table_name;
        stockSelect.appendChild(option);
    });
}

// 筛选股票（搜索功能 - 搜索全部股票）
function filterStocks() {
    const searchText = document.getElementById('searchInput').value.toLowerCase().trim();
    const stockSelect = document.getElementById('stockSelect');
    
    // 如果搜索框为空，显示当前策略下的股票
    if (!searchText) {
        updateStockList();
        return;
    }
    
    // 搜索全部股票
    stockSelect.innerHTML = '<option value="">-- 请选择股票 --</option>';
    
    let matchCount = 0;
    
    // 遍历所有策略组
    for (const [strategyName, stocks] of Object.entries(allStockGroups)) {
        stocks.forEach(stock => {
            const stockText = `${stock.name} ${stock.code}`.toLowerCase();
            
            // 如果匹配搜索词
            if (stockText.includes(searchText)) {
                const option = document.createElement('option');
                option.value = stock.code;
                option.textContent = `${stock.name} (${stock.code}) - ${strategyName}`;
                option.dataset.name = stock.name;
                option.dataset.table = stock.table_name;
                stockSelect.appendChild(option);
                matchCount++;
            }
        });
    }
    
    // 如果没有匹配结果，显示提示
    if (matchCount === 0) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = `未找到匹配 "${searchText}" 的股票`;
        option.disabled = true;
        stockSelect.appendChild(option);
    }
    
    stockSelect.value = '';
}

// 选择股票
async function selectStock() {
    const stockSelect = document.getElementById('stockSelect');
    const selectedOption = stockSelect.options[stockSelect.selectedIndex];
    
    if (!stockSelect.value) {
        showEmptyState();
        stopAutoRefresh(); // 停止自动刷新
        predictedVolume = null; // 清空预测成交量
        predictedVolumeType = null; // 清空预测成交量类型
        return;
    }

    // 切换股票时停止之前的自动刷新
    stopAutoRefresh();
    predictedVolume = null; // 清空预测成交量
    predictedVolumeType = null; // 清空预测成交量类型

    currentStockCode = stockSelect.value;
    const stockName = selectedOption.dataset.name;
    currentTableName = selectedOption.dataset.table;

    renderStockView(currentStockCode, stockName, currentTableName);
    await checkAvailablePeriods(currentTableName);
    const defaultPeriod = selectDefaultPeriod();
    loadStockData(currentStockCode, currentTableName, defaultPeriod);
}

// 显示空状态
function showEmptyState() {
    document.getElementById('app').innerHTML = `
        <div class="empty-state">
            <div class="empty-state-icon">📈</div>
            <div class="empty-state-text">请选择股票策略类型和具体股票</div>
        </div>
    `;
}

// 渲染股票视图
function renderStockView(stockCode, stockName, tableName) {
    const app = document.getElementById('app');
    
    app.innerHTML = `
        <div class="stock-info-bar">
            <div class="stock-info">
                <div class="stock-name-large">${stockName}</div>
                <div class="stock-code-large">${stockCode}</div>
                <div class="strategy-tag ${currentStrategy}">${currentStrategy}</div>
            </div>
            <div class="period-selector">
                <button class="period-btn" onclick="changePeriod('30min')">30分钟</button>
                <button class="period-btn" onclick="changePeriod('day')">日K线</button>
                <button class="period-btn" onclick="changePeriod('week')">周K线</button>
                <button class="period-btn" onclick="changePeriod('month')">月K线</button>
            </div>
        </div>

        <div class="chart-card">
            <div style="position: relative;">
                <div id="mainChart" class="chart-container">
                    <div class="loading">
                        <div class="spinner"></div>
                        <p>加载K线数据中...</p>
                    </div>
                </div>
                <div id="analysisInfo" class="chart-overlay-info">
                    <div class="overlay-item">
                        <span class="overlay-label">益损比:</span>
                        <span class="overlay-value" id="winLoseRatioValue">--</span>
                    </div>
                    <div class="overlay-item">
                        <span class="overlay-label">支撑线:</span>
                        <span class="overlay-value support" id="supportValue">--</span>
                    </div>
                    <div class="overlay-item">
                        <span class="overlay-label">压力线:</span>
                        <span class="overlay-value pressure" id="pressureValue">--</span>
                    </div>
                    <div class="overlay-item">
                        <span class="overlay-label">CR点:</span>
                        <span class="overlay-value" id="crPointsStats">--</span>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="backtest-section">
            <button class="backtest-btn" id="backtestBtn" onclick="runBacktest()">
                📊 运行回测
            </button>
            <div class="backtest-hint" style="text-align: center; color: #8899aa; font-size: 13px; margin-top: 10px;">
                💡 回测功能仅支持日K线，会在切换到日K线时自动启用
            </div>
            <div id="backtestResult" class="backtest-result"></div>
        </div>
    `;
}

// 切换周期
async function changePeriod(period) {
    try {
        if (!currentStockCode || !currentTableName) {
            console.error('未选择股票，无法切换周期');
            alert('请先选择股票');
            return;
        }

        if (!availablePeriods[period]) {
            alert(`该股票暂无${getPeriodName(period)}数据，请选择其他周期`);
            return;
        }

        console.log(`切换周期: ${period}, 股票: ${currentStockCode}, 表: ${currentTableName}`);

        document.querySelectorAll('.period-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.textContent.includes(period) || 
                (period === '30min' && btn.textContent === '30分钟') ||
                (period === 'day' && btn.textContent === '日K线') ||
                (period === 'week' && btn.textContent === '周K线') ||
                (period === 'month' && btn.textContent === '月K线')) {
                btn.classList.add('active');
            }
        });
        
        // 更新回测按钮状态
        updateBacktestButtonState(period);

        await loadStockData(currentStockCode, currentTableName, period);
        
    } catch (error) {
        console.error('切换周期失败:', error);
        const chartDom = document.getElementById('mainChart');
        if (chartDom) {
            chartDom.innerHTML = `
                <div class="error">
                    <p>📊 切换周期失败</p>
                    <p style="font-size: 12px; margin-top: 10px;">${error.message}</p>
                    <button onclick="changePeriod('${period}')" 
                            style="margin-top: 15px; padding: 8px 20px; background: #4a90e2; border: none; border-radius: 5px; color: white; cursor: pointer; font-size: 12px;">
                        重试
                    </button>
                </div>
            `;
        }
    }
}

// 加载股票数据
async function loadStockData(stockCode, tableName, period) {
    console.log(`=== 开始加载股票数据 ===`);
    console.log(`股票代码: ${stockCode}`);
    console.log(`表名: ${tableName}`);
    console.log(`周期: ${period}`);
    
    try {
        if (!stockCode || !tableName || !period) {
            throw new Error(`参数不完整: stockCode=${stockCode}, tableName=${tableName}, period=${period}`);
        }

        if (chart) {
            try {
                console.log(`[${period}] 在加载前销毁旧图表...`);
                chart.dispose();
                chart = null;
                console.log(`[${period}] 旧图表已销毁`);
            } catch (error) {
                console.warn(`[${period}] 销毁旧图表失败:`, error);
                chart = null;
            }
        }

        const chartDom = document.getElementById('mainChart');
        if (!chartDom) {
            throw new Error('找不到图表容器 mainChart');
        }
        
        chartDom.innerHTML = `
            <div class="loading">
                <div class="spinner"></div>
                <p>加载${getPeriodName(period)}数据中...</p>
            </div>
        `;

        console.log(`[${period}] 开始请求K线数据...`);

        const klineResponse = await fetch(`${API_BASE_URL}/kline_data`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                table_name: tableName,
                period_type: period
            })
        });

        console.log(`[${period}] K线数据响应状态: ${klineResponse.status}`);

        if (!klineResponse.ok) {
            throw new Error(`HTTP错误: ${klineResponse.status}`);
        }

        const klineResult = await klineResponse.json();
        console.log(`[${period}] K线数据结果:`, klineResult);

        if (klineResult.code !== 200) {
            throw new Error(klineResult.message);
        }

        // 适配新的返回格式：data现在包含kline_data、macd和ma
        let klineData = klineResult.data.kline_data || klineResult.data;  // 改为 let，允许后续重新赋值
        const macdData = klineResult.data.macd || null;
        const maData = klineResult.data.ma || null;
        
        if (!klineData || klineData.length === 0) {
            document.getElementById('mainChart').innerHTML = `
                <div class="error">
                    <p>📊 暂无${getPeriodName(period)}数据</p>
                    <p style="font-size: 14px; margin-top: 10px;">
                        该股票可能没有${getPeriodName(period)}的K线数据<br>
                        请尝试切换其他周期
                    </p>
                </div>
            `;
            return;
        }

        // 保存MACD数据供图表使用
        if (macdData) {
            window.currentMACDData = macdData;
            console.log(`[${period}] ✅ MACD数据已加载`, macdData);
        }
        
        // 保存MA数据供图表使用
        if (maData) {
            window.currentMAData = maData;
            console.log(`[${period}] ✅ MA数据已加载`, Object.keys(maData));
        }

        console.log(`[${period}] ✅ 立即启动分析数据加载（并行）`);
        const analysisPromise = loadAnalysisData(stockCode, period, klineData).catch(err => {
            console.error(`[${period}] 分析数据加载异常:`, err);
        });

        // 如果是日K线，加载成交量类型数据
        if (period === 'day') {
            console.log(`[${period}] 开始加载成交量类型数据...`);
            loadVolumeTypes(stockCode).catch(err => {
                console.error(`[${period}] 成交量类型数据加载异常:`, err);
            });
        } else {
            // 非日K线，清空成交量类型、赔率总分、多头组合、空头组合、压力线和支撑线数据
            volumeTypeMap = {};
            winRatioScoreMap = {};
            bullishPatternMap = {};
            bearishPatternMap = {};
            supportPriceMap = {};
            pressurePriceMap = {};
            
            // 清空CR点数据（30分钟、周线、月线不应该显示CR点）
            crPointsData = {
                c_points: [],
                r_points: [],
                rejected_c_points: [],
                strategy2_c_points: [],
                strategy2_scores: {},
                strategy1_scores: {}
            };
            console.log(`[${period}] 已清空CR点数据（非日K线）`);
        }

        console.log(`[${period}] 开始渲染K线，数据点数: ${klineData.length}`);
        
        // 如果是日K线，尝试获取最新一天的实时K线数据
        if (period === 'day') {
            console.log('[日K线] 尝试获取最新一天的实时K线数据...');
            try {
                const latestKlineData = await fetchLatestDayKline(tableName);
                if (latestKlineData) {
                    // 将最新一天的K线添加到现有数据中
                    const beforeMergeLength = klineData.length;
                    klineData = mergeLatestKline(klineData, latestKlineData);
                    console.log(`[${period}] ✅ 最新K线数据已合并: ${beforeMergeLength} -> ${klineData.length}`);
                    
                    // 验证klineData是一个有效的数组
                    console.log('[日K线] 验证klineData:', Array.isArray(klineData), '长度:', klineData.length);
                    console.log('[日K线] 最后一条K线:', klineData[klineData.length - 1]);
                    
                    // 重新计算MA和MACD指标
                    console.log('[日K线] 重新计算MA和MACD指标...');
                    console.log('[日K线] 准备计算，K线数据长度:', klineData.length);
                    const newMacdData = calculateMACD(klineData);
                    const newMaData = calculateMA(klineData, [5, 10, 20]);
                    
                    console.log('[日K线] 计算完成后检查:');
                    console.log('[日K线] klineData长度:', klineData.length);
                    console.log('[日K线] MA5长度:', newMaData.ma5?.length, 'MA10长度:', newMaData.ma10?.length, 'MA20长度:', newMaData.ma20?.length);
                    
                    // 验证长度是否一致
                    if (newMaData.ma5 && newMaData.ma5.length === klineData.length) {
                        console.log(`✅ 成功: MA数据长度(${newMaData.ma5.length})与K线数据长度(${klineData.length})匹配！`);
                        // 只有长度匹配时才更新全局数据
                        window.currentMACDData = newMacdData;
                        window.currentMAData = newMaData;
                        console.log(`[${period}] ✅ MA和MACD指标已更新为新计算的数据`);
                    } else {
                        console.error(`❌ 错误: MA数据长度(${newMaData.ma5?.length})与K线数据长度(${klineData.length})不匹配！保留原MA数据`);
                    }
                }
            } catch (error) {
                console.error(`[${period}] 获取最新K线数据失败（继续使用原有数据）:`, error);
                console.error('错误堆栈:', error.stack);
            }
            
            // 获取预测成交量
            try {
                const predicted = await fetchPredictedVolume(tableName);
                predictedVolume = predicted;
                console.log(`[${period}] 预测成交量:`, predictedVolume);
            } catch (error) {
                console.error(`[${period}] 获取预测成交量失败:`, error);
                predictedVolume = null;
                predictedVolumeType = null;
            }
        }
        
        try {
            await renderChart(klineData, {}, period);
            updateActivePeriodButton(period);
            console.log(`[${period}] K线渲染成功`);
            
            // 🔥 自动加载完整的历史CR点数据（从第一天到昨天）+ 最新一天
            if (period === 'day') {
                console.log('[日K线] 开始加载完整的CR点数据（历史+最新）...');
                analyzeCRPoints().catch(err => {
                    console.error('加载CR点失败:', err);
                });
                
                // 启动自动刷新（每分钟更新一次最新K线）
                startAutoRefresh();
            } else {
                // 非日K线，停止自动刷新
                stopAutoRefresh();
                predictedVolume = null; // 清空预测成交量
                predictedVolumeType = null; // 清空预测成交量类型
                // 更新CR点统计显示提示信息
                updateCRPointsStats();
            }
        } catch (error) {
            console.error(`[${period}] K线渲染失败:`, error);
            throw error;
        }

    } catch (error) {
        console.error(`加载${stockCode}数据失败:`, error);
        
        // 判断是否是 ECharts 加载失败
        const isEChartsError = error.message && error.message.includes('ECharts');
        const errorIcon = isEChartsError ? '📊' : '⚠️';
        const errorTitle = isEChartsError ? 'ECharts库加载失败' : '数据加载失败';
        const retryButton = isEChartsError 
            ? '<button onclick="location.reload()" style="margin-top: 15px; padding: 8px 20px; background: #4a90e2; border: none; border-radius: 5px; color: white; cursor: pointer; font-size: 12px;">🔄 刷新页面</button>'
            : '<button onclick="selectStock()" style="margin-top: 15px; padding: 8px 20px; background: #4a90e2; border: none; border-radius: 5px; color: white; cursor: pointer; font-size: 12px;">重试</button>';
        
        document.getElementById('mainChart').innerHTML = `
            <div class="error">
                <p>${errorIcon} ${errorTitle}</p>
                <p style="font-size: 12px; margin-top: 10px; color: #666;">${error.message}</p>
                ${retryButton}
            </div>
        `;
    }
}

// 获取预测的当天成交量
async function fetchPredictedVolume(tableName) {
    try {
        console.log(`[预测成交量] 开始请求: ${tableName}`);
        
        const response = await fetch(`${API_BASE_URL}/predict_volume`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                table_name: tableName
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP错误: ${response.status}`);
        }
        
        const result = await response.json();
        console.log(`[预测成交量] 响应结果:`, result);
        
        if (result.code !== 200) {
            throw new Error(result.message || '获取预测成交量失败');
        }
        
        const data = result.data;
        if (data.predicted_volume) {
            console.log(`[预测成交量] ✅ 成功: 当前=${data.current_volume?.toFixed(2)}, 预测=${data.predicted_volume?.toFixed(2)}, 比例=${data.ratio?.toFixed(2)}`);
            
            // 获取预测成交量后，立即计算成交量类型
            fetchPredictedVolumeType(tableName, data.predicted_volume).catch(err => {
                console.error('[预测成交量类型] 计算失败:', err);
            });
            
            return data.predicted_volume;
        } else {
            console.log(`[预测成交量] 无法预测: ${data.message}`);
            return null;
        }
        
    } catch (error) {
        console.error(`[预测成交量] 获取失败:`, error);
        return null;
    }
}

// 基于预测成交量计算成交量类型
async function fetchPredictedVolumeType(tableName, predictedVol) {
    try {
        console.log(`[预测成交量类型] 开始请求: ${tableName}, 预测成交量=${predictedVol}`);
        
        const response = await fetch(`${API_BASE_URL}/predict_volume_type`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                table_name: tableName,
                predicted_volume: predictedVol
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP错误: ${response.status}`);
        }
        
        const result = await response.json();
        console.log(`[预测成交量类型] 响应结果:`, result);
        
        if (result.code !== 200) {
            throw new Error(result.message || '计算预测成交量类型失败');
        }
        
        const data = result.data;
        // 后端返回空字符串""表示无类型，统一转换为'NONE'
        if (data.volume_type && data.volume_type !== '') {
            predictedVolumeType = data.volume_type;
            console.log(`[预测成交量类型] ✅ 成功: ${predictedVolumeType}`);
        } else {
            predictedVolumeType = 'NONE'; // null或空字符串都转换为'NONE'
            console.log(`[预测成交量类型] ⚠️ 未匹配任何类型（后端返回: ${data.volume_type}）`);
        }
        
    } catch (error) {
        console.error(`[预测成交量类型] 获取失败:`, error);
        predictedVolumeType = null;
    }
}

// 获取最新一天的K线数据（从1分钟数据聚合）
async function fetchLatestDayKline(tableName) {
    try {
        console.log(`[最新K线] 开始请求最新一天K线数据: ${tableName}`);
        
        const response = await fetch(`${API_BASE_URL}/latest_day_kline`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                table_name: tableName
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP错误: ${response.status}`);
        }
        
        const result = await response.json();
        console.log(`[最新K线] 响应结果:`, result);
        
        if (result.code !== 200) {
            throw new Error(result.message || '获取最新K线失败');
        }
        
        const klineData = result.data.kline_data;
        if (!klineData) {
            console.log(`[最新K线] 没有可用的最新K线数据`);
            return null;
        }
        
        console.log(`[最新K线] ✅ 成功获取最新K线数据:`, klineData);
        return klineData;
        
    } catch (error) {
        console.error(`[最新K线] 获取失败:`, error);
        return null;
    }
}

// 合并最新K线数据到现有数据中
function mergeLatestKline(existingKlineData, latestKlineData) {
    if (!latestKlineData) {
        console.log('[mergeLatestKline] 没有最新K线数据，返回原数据');
        return existingKlineData;
    }
    
    console.log('[mergeLatestKline] 开始合并，现有数据长度:', existingKlineData.length);
    console.log('[mergeLatestKline] 最新K线数据:', latestKlineData);
    
    // 获取最新K线的日期（只取日期部分，不包括时间）
    const latestDate = latestKlineData.time.split(' ')[0];
    console.log('[mergeLatestKline] 最新K线日期:', latestDate);
    
    // 检查现有数据中是否已经有这个日期的数据
    const existingIndex = existingKlineData.findIndex(item => {
        const itemDate = item.time.split(' ')[0];
        return itemDate === latestDate;
    });
    
    if (existingIndex >= 0) {
        // 如果已经存在，替换旧数据
        console.log(`[mergeLatestKline] 替换现有数据: 日期=${latestDate}, 索引=${existingIndex}`);
        existingKlineData[existingIndex] = latestKlineData;
    } else {
        // 如果不存在，追加到末尾
        console.log(`[mergeLatestKline] 追加新数据: 日期=${latestDate}`);
        existingKlineData.push(latestKlineData);
    }
    
    console.log('[mergeLatestKline] 合并后数据长度:', existingKlineData.length);
    return existingKlineData;
}

// 计算MACD指标
function calculateMACD(klineData) {
    const closes = klineData.map(item => item.close);
    const shortPeriod = 12;
    const longPeriod = 26;
    const signalPeriod = 9;
    
    // 计算EMA
    function calculateEMA(data, period) {
        const ema = [];
        const multiplier = 2 / (period + 1);
        
        // 第一个EMA使用SMA
        let sum = 0;
        for (let i = 0; i < period && i < data.length; i++) {
            sum += data[i];
        }
        ema.push(sum / period);
        
        // 后续使用EMA公式
        for (let i = period; i < data.length; i++) {
            const value = (data[i] - ema[ema.length - 1]) * multiplier + ema[ema.length - 1];
            ema.push(value);
        }
        
        return ema;
    }
    
    // 计算短期和长期EMA
    const ema12 = calculateEMA(closes, shortPeriod);
    const ema26 = calculateEMA(closes, longPeriod);
    
    // 计算DIF
    const dif = [];
    const startIndex = longPeriod - 1;
    for (let i = 0; i < ema12.length && i < ema26.length; i++) {
        dif.push(ema12[i] - ema26[i]);
    }
    
    // 计算DEA (DIF的9日EMA)
    const dea = calculateEMA(dif, signalPeriod);
    
    // 计算MACD柱
    const macd = [];
    const deaStartIndex = signalPeriod - 1;
    for (let i = 0; i < dea.length; i++) {
        macd.push((dif[i] - dea[i]) * 2);
    }
    
    // 填充前面的空值
    const result = {
        dif: Array(startIndex).fill(null).concat(dif),
        dea: Array(startIndex + deaStartIndex).fill(null).concat(dea),
        macd: Array(startIndex + deaStartIndex).fill(null).concat(macd)
    };
    
    return result;
}

// 计算MA指标
function calculateMA(klineData, periods) {
    const closes = klineData.map(item => item.close);
    const result = {};
    
    console.log(`[calculateMA] 输入K线数据长度: ${klineData.length}, 收盘价数组长度: ${closes.length}`);
    
    periods.forEach(period => {
        const ma = [];
        for (let i = 0; i < closes.length; i++) {
            if (i < period - 1) {
                ma.push(null);
            } else {
                let sum = 0;
                for (let j = 0; j < period; j++) {
                    sum += closes[i - j];
                }
                ma.push(sum / period);
            }
        }
        result[`ma${period}`] = ma;
        console.log(`[calculateMA] MA${period}计算完成，长度: ${ma.length}`);
    });
    
    return result;
}

// 加载成交量类型数据
async function loadVolumeTypes(stockCode) {
    try {
        console.log(`开始加载成交量类型数据: ${stockCode}`);
        
        const response = await fetch(`${API_BASE_URL}/daily_chance`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                stockCode: stockCode
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP错误: ${response.status}`);
        }

        const result = await response.json();
        
        if (result.code !== 200) {
            console.warn(`获取成交量类型数据失败: ${result.message}`);
            return;
        }

        // 将数据转换为日期到成交量类型、赔率总分、多头组合、空头组合、压力线和支撑线的映射
        volumeTypeMap = {};
        winRatioScoreMap = {};
        bullishPatternMap = {};
        bearishPatternMap = {};
        supportPriceMap = {};
        pressurePriceMap = {};
        
        let missingDataCount = 0;
        let totalDataCount = 0;
        
        if (result.data && Array.isArray(result.data)) {
            // 获取今天的日期
            const today = new Date().toISOString().split('T')[0]; // YYYY-MM-DD
            
            result.data.forEach(item => {
                if (item.date) {
                    totalDataCount++;
                    // 处理日期格式，确保是 YYYY-MM-DD 格式
                    const dateStr = item.date.split(' ')[0];
                    
                    // ⚠️ 今天的成交量类型用预测成交量实时计算，其他所有历史日期都从数据库读取
                    if (item.volumeType && dateStr !== today) {
                        volumeTypeMap[dateStr] = item.volumeType;
                    }
                    
                    if (item.totalWinRatioScore !== undefined && item.totalWinRatioScore !== null) {
                        winRatioScoreMap[dateStr] = item.totalWinRatioScore;
                    }
                    if (item.bullishPattern) {
                        bullishPatternMap[dateStr] = item.bullishPattern;
                    }
                    if (item.bearishPattern) {
                        bearishPatternMap[dateStr] = item.bearishPattern;
                    }
                    
                    // 记录缺少压力支撑线数据的日期
                    const hasSupportPrice = item.supportPrice !== undefined && item.supportPrice !== null;
                    const hasPressurePrice = item.pressurePrice !== undefined && item.pressurePrice !== null;
                    
                    if (hasSupportPrice) {
                        supportPriceMap[dateStr] = item.supportPrice;
                    }
                    if (hasPressurePrice) {
                        pressurePriceMap[dateStr] = item.pressurePrice;
                    }
                    
                    // 调试：记录缺少数据的情况
                    if (!hasSupportPrice && !hasPressurePrice) {
                        missingDataCount++;
                        if (missingDataCount <= 5) {  // 只打印前5个
                            console.log(`[压力支撑线] ${dateStr} 缺少数据 - support: ${item.supportPrice}, pressure: ${item.pressurePrice}`);
                        }
                    }
                }
            });
            console.log(`每日机会数据加载成功，总数据: ${totalDataCount} 条`);
            console.log(`  - 成交量类型: ${Object.keys(volumeTypeMap).length} 条`);
            console.log(`  - 赔率总分: ${Object.keys(winRatioScoreMap).length} 条`);
            console.log(`  - 多头组合: ${Object.keys(bullishPatternMap).length} 条`);
            console.log(`  - 空头组合: ${Object.keys(bearishPatternMap).length} 条`);
            console.log(`  - 支撑线: ${Object.keys(supportPriceMap).length} 条`);
            console.log(`  - 压力线: ${Object.keys(pressurePriceMap).length} 条`);
            console.log(`  - ⚠️ 缺少压力/支撑线数据: ${missingDataCount} 条`);
        }
    } catch (error) {
        console.error('加载成交量类型数据失败:', error);
        volumeTypeMap = {};
        winRatioScoreMap = {};
        bullishPatternMap = {};
        bearishPatternMap = {};
        supportPriceMap = {};
        pressurePriceMap = {};
    }
}

// 异步加载分析数据
async function loadAnalysisData(stockCode, period, klineData) {
    console.log(`[${period}] 🔵 loadAnalysisData 函数被调用，股票代码: ${stockCode}`);
    try {
        if (currentAnalysisController) {
            console.log(`[${period}] ⚠️ 取消之前的分析请求`);
            currentAnalysisController.abort();
        }
        
        console.log(`[${period}] 🚀 准备发送 stock_analysis 请求...`);
        
        currentAnalysisController = new AbortController();
        const controller = currentAnalysisController;
        
        const timeoutId = setTimeout(() => {
            if (controller === currentAnalysisController) {
                controller.abort();
            }
        }, 20000);
        
        console.log(`[${period}] 📡 正在发送 stock_analysis 请求到: ${API_BASE_URL}/stock_analysis`);
        const analysisResponse = await fetch(`${API_BASE_URL}/stock_analysis`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                stock_code: stockCode
            }),
            signal: controller.signal
        });
        console.log(`[${period}] ✅ stock_analysis 请求已发送，等待响应...`);

        clearTimeout(timeoutId);

        if (controller !== currentAnalysisController) {
            console.log(`[${period}] 请求已被新请求取消，忽略结果`);
            return;
        }

        const analysisResult = await analysisResponse.json();
        console.log(`[${period}] 分析数据返回:`, analysisResult);
        
        const analysisData = (analysisResult.code === 200 && analysisResult.data && analysisResult.data[period]) 
            ? analysisResult.data[period] : {};

        if (controller !== currentAnalysisController) {
            console.log(`[${period}] 请求已被新请求取消，忽略更新`);
            return;
        }

        if (chart && analysisData && Object.keys(analysisData).length > 0) {
            console.log(`[${period}] 更新分析线...`);
            updateChartWithAnalysis(analysisData, klineData.length);
            updateAnalysisInfo(analysisData, klineData[klineData.length - 1] || {});
            console.log(`[${period}] 分析数据更新完成`);
        } else {
            console.log(`[${period}] 分析数据为空，跳过更新`);
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            console.warn(`[${period}] 分析数据加载已取消或超时`);
        } else {
            console.error(`[${period}] 加载分析数据失败:`, error);
        }
    }
}

// 更新图表添加分析线
function updateChartWithAnalysis(analysisData, dataLength) {
    if (!chart) return;

    const currentOption = chart.getOption();
    let currentSeries = currentOption.series || [];
    
    let supportIndex = currentSeries.findIndex(s => s.name === '支撑线');
    let pressureIndex = currentSeries.findIndex(s => s.name === '压力线');
    
    const supportLine = {
        name: '支撑线',
        type: 'line',
        data: Array(dataLength).fill(analysisData.supportPrice || 0),
        smooth: false,
        lineStyle: {
            color: '#FFD700',
            width: 2,
            type: 'solid'
        },
        symbol: 'none',
        z: 10
    };
    
    const pressureLine = {
        name: '压力线',
        type: 'line',
        data: Array(dataLength).fill(analysisData.pressurePrice || 0),
        smooth: false,
        lineStyle: {
            color: '#FFD700',
            width: 2,
            type: 'solid'
        },
        symbol: 'none',
        z: 10
    };
    
    if (analysisData.supportPrice) {
        if (supportIndex >= 0) {
            currentSeries[supportIndex] = supportLine;
        } else {
            currentSeries.push(supportLine);
        }
    }
    
    if (analysisData.pressurePrice) {
        if (pressureIndex >= 0) {
            currentSeries[pressureIndex] = pressureLine;
        } else {
            currentSeries.push(pressureLine);
        }
    }
    
    chart.setOption({
        series: currentSeries
    });
}

// 检查可用的周期类型
async function checkAvailablePeriods(tableName) {
    try {
        const response = await fetch(`${API_BASE_URL}/available_periods`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                table_name: tableName
            })
        });

        const result = await response.json();
        
        if (result.code === 200) {
            availablePeriods = result.data;
            updatePeriodButtons();
        } else {
            availablePeriods = {
                '30min': 1,
                'day': 1,
                'week': 1,
                'month': 1
            };
        }
    } catch (error) {
        console.error('获取可用周期失败:', error);
        availablePeriods = {
            '30min': 1,
            'day': 1,
            'week': 1,
            'month': 1
        };
    }
}

// 更新周期按钮状态
function updatePeriodButtons() {
    const periodButtons = document.querySelectorAll('.period-btn');
    
    periodButtons.forEach(btn => {
        const btnText = btn.textContent;
        let period = '';
        
        if (btnText.includes('30分钟')) period = '30min';
        else if (btnText.includes('日K线')) period = 'day';
        else if (btnText.includes('周K线')) period = 'week';
        else if (btnText.includes('月K线')) period = 'month';
        
        if (period && !availablePeriods[period]) {
            btn.disabled = true;
            btn.style.opacity = '0.3';
            btn.style.cursor = 'not-allowed';
            btn.title = `暂无${btnText}数据`;
        } else {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.style.cursor = 'pointer';
            btn.title = '';
        }
    });
}

// 选择默认周期
function selectDefaultPeriod() {
    const priorities = ['day', '30min', 'week', 'month'];
    
    for (const period of priorities) {
        if (availablePeriods[period]) {
            return period;
        }
    }
    
    const available = Object.keys(availablePeriods);
    return available.length > 0 ? available[0] : 'day';
}

// 更新激活的周期按钮
function updateActivePeriodButton(period) {
    document.querySelectorAll('.period-btn').forEach(btn => {
        btn.classList.remove('active');
        if ((period === '30min' && btn.textContent === '30分钟') ||
            (period === 'day' && btn.textContent === '日K线') ||
            (period === 'week' && btn.textContent === '周K线') ||
            (period === 'month' && btn.textContent === '月K线')) {
            btn.classList.add('active');
        }
    });
    
    // 更新回测按钮状态
    updateBacktestButtonState(period);
}

// 获取周期名称
function getPeriodName(period) {
    const names = {
        '30min': '30分钟',
        'day': '日K线',
        'week': '周K线',
        'month': '月K线'
    };
    return names[period] || period;
}

// 计算默认显示的数据范围
function calculateStartPercent(totalDataPoints, period) {
    let targetPoints;
    switch(period) {
        case '30min':
            targetPoints = 20 * 16;
            break;
        case 'day':
            targetPoints = 120;
            break;
        case 'week':
            targetPoints = 104;
            break;
        case 'month':
            targetPoints = 36;
            break;
        default:
            targetPoints = 120;
    }
    
    if (totalDataPoints <= targetPoints) {
        return 0;
    }
    
    const startPercent = ((totalDataPoints - targetPoints) / totalDataPoints) * 100;
    return Math.max(0, startPercent);
}

// 渲染图表
async function renderChart(klineData, analysisData, period) {
    try {
        // 等待ECharts加载完成
        await waitForECharts();
        
        // 更新当前周期
        currentPeriod = period;
        
        const chartDom = document.getElementById('mainChart');
        if (!chartDom) {
            console.error('找不到图表容器 mainChart');
            return;
        }
        
        chart = echarts.init(chartDom);
        console.log(`[${period}] ECharts实例已初始化`);

        const dates = klineData.map(item => item.time);
        const values = klineData.map(item => [item.open, item.close, item.low, item.high]);
        const volumes = klineData.map(item => item.volume);
        
        // 使用后端返回的MACD数据
        const macdData = window.currentMACDData || { dif: [], dea: [], macd: [] };
        if (window.currentMACDData) {
            console.log(`[${period}] 使用后端计算的MACD - DIF数:${macdData.dif.length}, DEA数:${macdData.dea.length}, MACD数:${macdData.macd.length}`);
        }
        
        // 使用后端返回的MA数据
        const maData = window.currentMAData || {};
        if (window.currentMAData) {
            console.log(`[${period}] 使用后端计算的MA - ${Object.keys(maData).join(', ')}`);
            console.log(`[${period}] MA数据长度 - MA5:${maData.ma5?.length}, MA10:${maData.ma10?.length}, MA20:${maData.ma20?.length}`);
            console.log(`[${period}] K线数据长度:${dates.length}, MA数据长度:${maData.ma5?.length}`);
            
            // 验证数据长度是否一致
            if (maData.ma5 && maData.ma5.length !== dates.length) {
                console.warn(`[${period}] ⚠️ 警告: MA数据长度(${maData.ma5.length})与K线数据长度(${dates.length})不一致！`);
            }
        }
        
        console.log(`[${period}] 数据准备完成 - 日期数:${dates.length}, K线数:${values.length}, 成交量数:${volumes.length}`);

        const latestData = klineData[klineData.length - 1] || {};
        
        // 记录最新一天的日期（用于tooltip中判断）
        const latestDate = dates.length > 0 ? dates[dates.length - 1].split(' ')[0] : null;
        
        // 找到前一交易日的日期（用于最新一天的tooltip显示）
        let previousTradingDate = null;
        if (dates.length >= 2) {
            previousTradingDate = dates[dates.length - 2].split(' ')[0];
        }
        
        console.log(`[${period}] 最新日期: ${latestDate}, 前一交易日: ${previousTradingDate}`);

        const supportLine = (analysisData && analysisData.supportPrice) ? 
            Array(dates.length).fill(analysisData.supportPrice) : null;
        const pressureLine = (analysisData && analysisData.pressurePrice) ? 
            Array(dates.length).fill(analysisData.pressurePrice) : null;

        const option = {
            backgroundColor: 'transparent',
            animation: false,
            legend: {
                show: false
            },
            tooltip: {
                trigger: 'axis',
                axisPointer: {
                    type: 'cross'
                },
                backgroundColor: 'rgba(26, 35, 56, 0.95)',
                borderColor: '#4a90e2',
                borderWidth: 2,
                textStyle: {
                    color: '#fff',
                    fontSize: 13
                },
                formatter: function(params) {
                    let result = params[0].name + '<br/>';
                    const currentDate = params[0].name;
                    // 提取纯日期部分（去掉时间）
                    const dateOnly = currentDate.split(' ')[0];
                    
                    // 收集MA数据和R点数据，最后显示
                    let maLines = [];
                    let rPointInfo = null;
                    
                    params.forEach(param => {
                        if (param.seriesName === 'K线') {
                            result += `开盘: ${param.value[1]}<br/>`;
                            result += `收盘: ${param.value[2]}<br/>`;
                            result += `最低: ${param.value[3]}<br/>`;
                            result += `最高: ${param.value[4]}<br/>`;
                            
                            // 检查是否是C点，如果是则显示机会概率值
                            let isC点 = false;
                            let strategy1Score = 0;
                            let strategy2Score = 0;
                            let isGoldenC = false;
                            
                            // 从所有C点中查找当前日期的C点
                            if (crPointsData.c_points) {
                                const cPoint = crPointsData.c_points.find(cp => cp.triggerDate === dateOnly);
                                if (cPoint) {
                                    isC点 = true;
                                    strategy1Score = cPoint.strategy1Score || 0;
                                    strategy2Score = cPoint.strategy2Score || 0;
                                    isGoldenC = cPoint.isGolden || false;
                                }
                            }
                            if (!isC点 && crPointsData.strategy2_c_points) {
                                const s2cPoint = crPointsData.strategy2_c_points.find(cp => cp.triggerDate === dateOnly);
                                if (s2cPoint) {
                                    isC点 = true;
                                    strategy1Score = s2cPoint.strategy1Score || 0;
                                    strategy2Score = s2cPoint.strategy2Score || 0;
                                    isGoldenC = s2cPoint.isGolden || false;
                                }
                            }
                            
                            // 如果是C点，计算并显示机会概率值
                            if (isC点) {
                                const maxScore = Math.max(strategy1Score, strategy2Score);
                                const probabilityValue = Math.min(maxScore * 1.2, 99);
                                result += `<span style="color: #FFD700; font-weight: bold; font-size: 12px;">🎯 机会概率值: ${probabilityValue.toFixed(1)}%</span><br/>`;
                                
                                // 如果是金色C点，显示特殊标记
                                if (isGoldenC) {
                                    result += `<span style="color: #FFD700; font-weight: bold; font-size: 11px;">⭐ 金色C点（5日内策略一和策略二都有发C）</span><br/>`;
                                }
                            }
                            
                            // 显示策略1的评分和插件信息（如果存在）
                            // 🔥 调试：查看策略评分数据
                            console.log(`[Tooltip] 当前日期: ${dateOnly}, latestDate: ${latestDate}`);
                            console.log(`[Tooltip] strategy1_scores存在吗?`, !!crPointsData.strategy1_scores);
                            if (crPointsData.strategy1_scores) {
                                console.log(`[Tooltip] strategy1_scores的日期列表:`, Object.keys(crPointsData.strategy1_scores));
                                console.log(`[Tooltip] ${dateOnly}的数据:`, crPointsData.strategy1_scores[dateOnly]);
                            }
                            
                            if (crPointsData.strategy1_scores && crPointsData.strategy1_scores[dateOnly]) {
                                const s1Data = crPointsData.strategy1_scores[dateOnly];
                                result += `<span style="color: #2196F3; font-weight: bold;">📊 策略1评分</span><br/>`;
                                result += `<span style="color: #2196F3; font-size: 11px;">最终分: ${s1Data.score.toFixed(2)}</span><br/>`;
                                result += `<span style="color: #2196F3; font-size: 11px;">基础分: ${s1Data.base_score.toFixed(2)}</span><br/>`;
                                
                                // 显示触发的插件
                                if (s1Data.plugins && s1Data.plugins.length > 0) {
                                    result += `<span style="color: #2196F3; font-size: 11px;">🔌 触发插件:</span><br/>`;
                                    s1Data.plugins.forEach(plugin => {
                                        const icon = plugin.scoreAdjustment < 0 ? '⚠️' : '✅';
                                        result += `<span style="color: #2196F3; font-size: 10px; margin-left: 10px;">${icon} ${plugin.pluginName}</span><br/>`;
                                        result += `<span style="color: #64B5F6; font-size: 9px; margin-left: 15px;">${plugin.reason}</span><br/>`;
                                        if (plugin.scoreAdjustment !== 0 && plugin.scoreAdjustment !== -999) {
                                            const scoreText = plugin.scoreAdjustment > 0 ? `+${plugin.scoreAdjustment}` : plugin.scoreAdjustment;
                                            result += `<span style="color: #64B5F6; font-size: 9px; margin-left: 15px;">分数: ${scoreText}分</span><br/>`;
                                        }
                                    });
                                }
                                
                                // 显示是否触发C点
                                if (s1Data.is_c_point) {
                                    result += `<span style="color: #2196F3; font-size: 11px;">✅ 触发C点</span><br/>`;
                                } else if (s1Data.is_rejected) {
                                    result += `<span style="color: #2196F3; font-size: 11px;">❌ 被插件否决</span><br/>`;
                                } else {
                                    result += `<span style="color: #64B5F6; font-size: 11px;">未触发C点（分数<70）</span><br/>`;
                                }
                            }
                            
                            // 显示赔率总分、成交量总分、成交量类型（仅日K线）
                            if (period === 'day') {
                                // 判断当前日期是否是最新一天
                                const isLatestDate = (dateOnly === latestDate);
                                
                                // 如果是最新一天，使用前一交易日的数据；否则使用当天的数据
                                const dateForData = isLatestDate && previousTradingDate ? previousTradingDate : dateOnly;
                                
                                const winRatioScore = winRatioScoreMap[dateForData];
                                
                                // 成交量类型：最新一天使用实时计算的，历史数据使用数据库的
                                let volumeType = null;
                                let volumeTypeLabel = '成交量类型';
                                
                                if (isLatestDate) {
                                    // 最新一天：使用实时计算的成交量类型
                                    volumeType = predictedVolumeType;
                                    volumeTypeLabel = '成交量类型(实时)';
                                } else {
                                    // 历史数据：使用数据库中的成交量类型
                                    volumeType = volumeTypeMap[dateOnly];
                                    volumeTypeLabel = '成交量类型';
                                }
                                
                                // 显示赔率总分（最新一天显示前一交易日的）
                                if (winRatioScore !== undefined && winRatioScore !== null) {
                                    const label = isLatestDate ? '赔率总分(前一日)' : '赔率总分';
                                    result += `<span style="color: #2196F3;">${label}: ${winRatioScore.toFixed(2)}</span><br/>`;
                                }
                                
                                // 计算并显示成交量总分和类型
                                if (volumeType && volumeType !== 'NONE') {
                                    function calculateVolumeScore(volumeType) {
                                        if (!volumeType) return 0;
                                        const types = volumeType.split(',').map(t => t.trim());
                                        if (types.includes('E') || types.includes('F')) return 0;
                                        if (types.some(t => ['A', 'B', 'C', 'D'].includes(t))) return 40;
                                        if (types.includes('H')) return 28;
                                        return 0;
                                    }
                                    const volumeScore = calculateVolumeScore(volumeType);
                                    result += `<span style="color: #2196F3;">成交量总分: ${volumeScore}分</span><br/>`;
                                    
                                    // 显示成交量类型（只显示字母）
                                    const types = volumeType.split(',').map(t => t.trim());
                                    const displayColor = isLatestDate ? '#FFD700' : '#2196F3'; // 最新一天用金色突出显示
                                    result += `<span style="color: ${displayColor}; font-weight: bold;">${volumeTypeLabel}: ${types.join(', ')}</span><br/>`;
                                } else if (volumeType === 'NONE') {
                                    // 未匹配任何成交量类型
                                    result += `<span style="color: #999;">成交量类型: 无</span><br/>`;
                                } else if (isLatestDate) {
                                    // 最新一天如果还在计算中（null或undefined）
                                    result += `<span style="color: #999;">成交量类型(实时): 计算中...</span><br/>`;
                                }
                            }
                        } else if (param.seriesName === 'MA5' || param.seriesName === 'MA10' || param.seriesName === 'MA20') {
                            // MA均线，收集起来最后显示
                            if (param.value !== null && param.value !== undefined) {
                                // 统一颜色：MA5白色、MA10黄色、MA20紫色
                                let maColor = '#FFFFFF';  // 默认白色
                                if (param.seriesName === 'MA5') {
                                    maColor = '#FFFFFF';  // 白色
                                } else if (param.seriesName === 'MA10') {
                                    maColor = '#FFA500';  // 黄色
                                } else if (param.seriesName === 'MA20') {
                                    maColor = '#9C27B0';  // 紫色
                                }
                                maLines.push(`<span style="color: ${maColor};">${param.seriesName}: ${param.value.toFixed(2)}</span>`);
                            }
                        } else if (param.seriesName === '成交量') {
                            result += `成交量: ${(param.value / 10000).toFixed(2)}万<br/>`;
                        } else if (param.seriesName === '预测成交量') {
                            // 预测成交量也显示为万为单位
                            if (param.value !== null && param.value !== undefined) {
                                result += `<span style="color: #FFD700; font-weight: bold;">预测成交量: ${(param.value / 10000).toFixed(2)}万</span><br/>`;
                            }
                        } else if (param.seriesName === 'C点' || param.seriesName === '被否决C点' || param.seriesName === '策略2C') {
                            // C点标记（不显示详细信息，因为K线部分已经显示了）
                            // 仅保留简单标识
                        } else if (param.seriesName === 'R点') {
                            // R点收集信息，稍后显示
                            if (param.data && param.data.rPointInfo) {
                                rPointInfo = param.data.rPointInfo;
                            } else {
                                rPointInfo = { simple: true };
                            }
                        } else if (param.seriesName !== '支撑线' && param.seriesName !== '压力线') {
                            // 过滤掉支撑线和压力线系列（只显示底部的历史数据）
                            result += `${param.seriesName}: ${param.value}<br/>`;
                        }
                    });
                    
                    // 显示多头组合和空头组合（仅日K线）
                    if (period === 'day' && params[0] && params[0].name) {
                        const dateStr = params[0].name;
                        const dateOnly = dateStr.split(' ')[0];
                        const bullishPattern = bullishPatternMap[dateOnly];
                        const bearishPattern = bearishPatternMap[dateOnly];
                        
                        // 显示多头组合
                        if (bullishPattern) {
                            result += `<span style="color: #26a69a; font-weight: bold;">📈 多头组合:</span><br/>`;
                            const patterns = bullishPattern.split(',');
                            patterns.forEach(p => {
                                const patternLabel = p.trim();
                                result += `<span style="color: #26a69a; margin-left: 10px;">• ${patternLabel}</span><br/>`;
                            });
                        }
                        
                        // 显示空头组合
                        if (bearishPattern) {
                            result += `<span style="color: #ef5350; font-weight: bold;">📉 空头组合:</span><br/>`;
                            const patterns = bearishPattern.split(',');
                            patterns.forEach(p => {
                                const patternLabel = p.trim();
                                result += `<span style="color: #ef5350; margin-left: 10px;">• ${patternLabel}</span><br/>`;
                            });
                        }
                        
                        // 显示策略2评分（所有日K线）
                        if (crPointsData && crPointsData.strategy2_scores && params[0] && params[0].name) {
                            const dateStr = params[0].name;
                            const dateOnly = dateStr.split(' ')[0];
                            const strategy2Score = crPointsData.strategy2_scores[dateOnly];
                            
                            if (strategy2Score) {
                                const triggeredText = strategy2Score.triggered ? ' ✓ 已触发' : '';
                                result += `<span style="color: #9C27B0; font-weight: bold;">策略二: ${strategy2Score.score.toFixed(0)}分${triggeredText}</span><br/>`;
                                if (strategy2Score.reason) {
                                    result += `<span style="color: #B968C7; font-size: 11px; margin-left: 10px;">${strategy2Score.reason}</span><br/>`;
                                }
                            }
                        }
                        
                        // 显示R点信息（在策略2之后、支撑压力线之前）
                        if (rPointInfo) {
                            if (rPointInfo.simple) {
                                result += `<span style="color: #4CAF50;">R点</span><br/>`;
                            } else {
                                result += `<span style="color: #4CAF50; font-weight: bold;">R点触发</span><br/>`;
                                
                                // 显示触发的插件信息
                                if (rPointInfo.plugins && rPointInfo.plugins.length > 0) {
                                    result += `<span style="color: #4CAF50; font-weight: bold;">风险插件:</span><br/>`;
                                    rPointInfo.plugins.forEach(plugin => {
                                        result += `<span style="color: #4CAF50; font-size: 11px; margin-left: 10px;">🛑 ${plugin.pluginName}</span><br/>`;
                                        result += `<span style="color: #81C784; font-size: 10px; margin-left: 20px;">${plugin.reason}</span><br/>`;
                                    });
                                }
                            }
                        }
                        
                        // 显示当天的压力线和支撑线（历史数据，数据库存储为整数，需除以100）
                        if (params[0] && params[0].name) {
                            const dateStr = params[0].name;
                            const dateOnly = dateStr.split(' ')[0];
                            
                            // 判断当前日期是否是最新一天
                            const isLatestDate = (dateOnly === latestDate);
                            
                            // 如果是最新一天，使用前一交易日的数据；否则使用当天的数据
                            const dateForData = isLatestDate && previousTradingDate ? previousTradingDate : dateOnly;
                            
                            const supportPrice = supportPriceMap[dateForData];
                            const pressurePrice = pressurePriceMap[dateForData];
                            
                            if (supportPrice !== undefined || pressurePrice !== undefined) {
                                const labelSuffix = isLatestDate ? '(前一日)' : '';
                                
                                if (supportPrice !== undefined && supportPrice !== null) {
                                    // 数据库存储的是整数，需要除以100转换为实际价格
                                    const actualSupportPrice = supportPrice / 100;
                                    result += `<span style="color: #26a69a; font-weight: bold;">支撑线${labelSuffix}: ${actualSupportPrice.toFixed(2)}</span><br/>`;
                                }
                                
                                if (pressurePrice !== undefined && pressurePrice !== null) {
                                    // 数据库存储的是整数，需要除以100转换为实际价格
                                    const actualPressurePrice = pressurePrice / 100;
                                    result += `<span style="color: #ef5350; font-weight: bold;">压力线${labelSuffix}: ${actualPressurePrice.toFixed(2)}</span><br/>`;
                                }
                            }
                        }
                    }
                    
                    // 最后显示MA均线
                    if (maLines.length > 0) {
                        maLines.forEach(line => {
                            result += line + '<br/>';
                        });
                    }
                    
                    return result;
                }
            },
            grid: [
                {
                    left: '8%',
                    right: '8%',
                    top: '8%',
                    height: '48%'
                },
                {
                    left: '8%',
                    right: '8%',
                    top: '60%',
                    height: '12%'
                },
                {
                    left: '8%',
                    right: '8%',
                    top: '76%',
                    height: '14%'
                }
            ],
            xAxis: [
                {
                    type: 'category',
                    data: dates,
                    scale: true,
                    boundaryGap: false,
                    axisLine: { lineStyle: { color: '#4a90e2' } },
                    axisLabel: {
                        color: '#888',
                        formatter: function(value) {
                            if (period === '30min') {
                                return value.substring(5, 16);
                            } else {
                                return value.substring(0, 10);
                            }
                        }
                    },
                    splitLine: { show: false },
                    min: 'dataMin',
                    max: 'dataMax'
                },
                {
                    type: 'category',
                    gridIndex: 1,
                    data: dates,
                    scale: true,
                    boundaryGap: false,
                    axisLine: { lineStyle: { color: '#4a90e2' } },
                    axisLabel: { show: false },
                    splitLine: { show: false },
                    min: 'dataMin',
                    max: 'dataMax'
                },
                {
                    type: 'category',
                    gridIndex: 2,
                    data: dates,
                    scale: true,
                    boundaryGap: false,
                    axisLine: { lineStyle: { color: '#4a90e2' } },
                    axisLabel: {
                        color: '#888',
                        formatter: function(value) {
                            if (period === '30min') {
                                return value.substring(5, 16);
                            } else {
                                return value.substring(0, 10);
                            }
                        }
                    },
                    splitLine: { show: false },
                    min: 'dataMin',
                    max: 'dataMax'
                }
            ],
            yAxis: [
                {
                    scale: true,
                    splitArea: { show: false },
                    axisLine: { lineStyle: { color: '#4a90e2' } },
                    axisLabel: { color: '#888' },
                    splitLine: {
                        lineStyle: {
                            color: '#2a3f5f'
                        }
                    }
                },
                {
                    scale: true,
                    gridIndex: 1,
                    splitNumber: 2,
                    axisLine: { lineStyle: { color: '#4a90e2' } },
                    axisLabel: { 
                        show: false
                    },
                    splitLine: {
                        lineStyle: {
                            color: '#2a3f5f'
                        }
                    }
                },
                {
                    scale: true,
                    gridIndex: 2,
                    splitNumber: 3,
                    axisLine: { lineStyle: { color: '#4a90e2' } },
                    axisLabel: { 
                        color: '#888',
                        fontSize: 10
                    },
                    splitLine: {
                        lineStyle: {
                            color: '#2a3f5f'
                        }
                    }
                }
            ],
            dataZoom: [
                {
                    type: 'inside',
                    xAxisIndex: [0, 1, 2],
                    start: calculateStartPercent(dates.length, period),
                    end: 100
                },
                {
                    show: true,
                    xAxisIndex: [0, 1, 2],
                    type: 'slider',
                    bottom: '1%',
                    start: calculateStartPercent(dates.length, period),
                    end: 100,
                    backgroundColor: '#1e2a4a',
                    fillerColor: 'rgba(74, 144, 226, 0.25)',
                    borderColor: '#4a90e2',
                    textStyle: {
                        color: '#888'
                    },
                    handleStyle: {
                        color: '#4a90e2'
                    }
                }
            ],
            series: [
                {
                    name: 'K线',
                    type: 'candlestick',
                    data: values,
                    itemStyle: {
                        color: '#ef5350',
                        color0: '#26a69a',
                        borderColor: '#ef5350',
                        borderColor0: '#26a69a'
                    },
                    emphasis: {
                        itemStyle: {
                            borderWidth: 2
                        }
                    }
                },
                // MA5 均线（白色）
                {
                    name: 'MA5',
                    type: 'line',
                    data: maData.ma5 || [],
                    smooth: false,
                    lineStyle: {
                        color: '#FFFFFF',
                        width: 1.5
                    },
                    symbol: 'none',
                    z: 3
                },
                // MA10 均线（黄色）
                {
                    name: 'MA10',
                    type: 'line',
                    data: maData.ma10 || [],
                    smooth: false,
                    lineStyle: {
                        color: '#FFA500',
                        width: 1.5
                    },
                    symbol: 'none',
                    z: 3
                },
                // MA20 均线（紫色）
                {
                    name: 'MA20',
                    type: 'line',
                    data: maData.ma20 || [],
                    smooth: false,
                    lineStyle: {
                        color: '#9C27B0',
                        width: 1.5
                    },
                    symbol: 'none',
                    z: 3
                },
                {
                    name: '成交量',
                    type: 'bar',
                    xAxisIndex: 1,
                    yAxisIndex: 1,
                    data: volumes,
                    itemStyle: {
                        color: function(params) {
                            const dataIndex = params.dataIndex;
                            if (dataIndex === 0) return '#26a69a';
                            return values[dataIndex][1] > values[dataIndex][0] ? '#ef5350' : '#26a69a';
                        }
                    }
                },
                // 预测成交量（虚线标记）- 只在最后一天显示
                {
                    name: '预测成交量',
                    type: 'line',
                    xAxisIndex: 1,
                    yAxisIndex: 1,
                    data: (() => {
                        // 只在最后一天显示预测成交量
                        if (predictedVolume && period === 'day' && dates.length > 0) {
                            const result = new Array(dates.length).fill(null);
                            result[dates.length - 1] = predictedVolume;
                            return result;
                        }
                        return [];
                    })(),
                    lineStyle: {
                        color: '#FFD700',
                        type: 'dashed',
                        width: 2
                    },
                    symbol: 'diamond',  // 菱形符号
                    symbolSize: 8,
                    itemStyle: {
                        color: '#FFD700',
                        borderColor: '#FFD700',
                        borderWidth: 2
                    },
                    label: {
                        show: true,
                        formatter: function(params) {
                            if (params.value !== null) {
                                // 格式化显示：如果大于1万，显示xx万，否则直接显示数字
                                if (params.value >= 10000) {
                                    return `预测: ${(params.value / 10000).toFixed(2)}万`;
                                } else {
                                    return `预测: ${params.value.toFixed(0)}`;
                                }
                            }
                            return '';
                        },
                        position: 'top',
                        color: '#FFD700',
                        fontSize: 11,
                        fontWeight: 'bold',
                        backgroundColor: 'rgba(0, 0, 0, 0.6)',
                        padding: [3, 6],
                        borderRadius: 3
                    },
                    z: 10,
                    showSymbol: true
                },
                // MACD DIF线（快线，白色）
                {
                    name: 'DIF',
                    type: 'line',
                    xAxisIndex: 2,
                    yAxisIndex: 2,
                    data: macdData.dif,
                    smooth: false,
                    lineStyle: {
                        color: '#FFFFFF',
                        width: 1.5
                    },
                    symbol: 'none',
                    z: 5
                },
                // MACD DEA线（慢线/信号线，黄色）
                {
                    name: 'DEA',
                    type: 'line',
                    xAxisIndex: 2,
                    yAxisIndex: 2,
                    data: macdData.dea,
                    smooth: false,
                    lineStyle: {
                        color: '#FFA500',
                        width: 1.5
                    },
                    symbol: 'none',
                    z: 5
                },
                // MACD柱状图
                {
                    name: 'MACD',
                    type: 'bar',
                    xAxisIndex: 2,
                    yAxisIndex: 2,
                    data: macdData.macd,
                    itemStyle: {
                        color: function(params) {
                            return params.value >= 0 ? '#e74c3c' : '#2ecc71';
                        }
                    },
                    barWidth: '60%'
                }
            ]
        };

        // 添加K线的markLine配置（用于动态显示压力/支撑线）
        option.series[0].markLine = {
            silent: true,
            symbol: 'none',
            label: {
                show: true,
                position: 'end',
                formatter: function(params) {
                    return params.name + ': ' + params.value.toFixed(2);
                },
                fontSize: 11,
                color: '#fff',
                backgroundColor: 'rgba(0, 0, 0, 0.6)',
                padding: [4, 8],
                borderRadius: 3
            },
            lineStyle: {
                type: 'solid',
                width: 2
            },
            data: []  // 初始为空，鼠标悬停时动态更新
        };

        if (supportLine) {
            option.series.push({
                name: '支撑线',
                type: 'line',
                data: supportLine,
                smooth: false,
                lineStyle: {
                    color: '#FFD700',
                    width: 2,
                    type: 'solid'
                },
                symbol: 'none',
                z: 10
            });
        }

        if (pressureLine) {
            option.series.push({
                name: '压力线',
                type: 'line',
                data: pressureLine,
                smooth: false,
                lineStyle: {
                    color: '#FFD700',
                    width: 2,
                    type: 'solid'
                },
                symbol: 'none',
                z: 10
            });
        }

        try {
            chart.setOption(option, true);
        } catch (error) {
            console.error('设置图表配置失败:', error);
            throw error;
        }

        // 使用updateAxisPointer来动态显示压力/支撑线（优化后：整个日期区域都能触发）
        let lastHoverDate = null;  // 记录上次悬停的日期，避免重复更新
        
        chart.off('updateAxisPointer');  // 移除旧的监听器
        chart.on('updateAxisPointer', function(event) {
            // 获取当前鼠标指向的数据点
            const xAxisInfo = event.axesInfo[0];
            if (xAxisInfo && xAxisInfo.value !== undefined) {
                const dataIndex = xAxisInfo.value;
                if (dataIndex >= 0 && dataIndex < dates.length) {
                    const dateStr = dates[dataIndex];
                    const dateOnly = dateStr.split(' ')[0];
                    
                    // 如果是同一个日期，不重复更新（性能优化）
                    if (dateOnly === lastHoverDate) {
                        return;
                    }
                    lastHoverDate = dateOnly;
                    
                    const supportPrice = supportPriceMap[dateOnly];
                    const pressurePrice = pressurePriceMap[dateOnly];
                    
                    const markLineData = [];
                    
                    // 添加支撑线（黄色）
                    if (supportPrice !== undefined && supportPrice !== null) {
                        const actualSupportPrice = supportPrice / 100;
                        markLineData.push({
                            name: '支撑',
                            yAxis: actualSupportPrice,
                            lineStyle: {
                                color: '#FFD700',
                                width: 2
                            },
                            label: {
                                color: '#000',
                                backgroundColor: '#FFD700'
                            }
                        });
                        console.log(`[压力支撑线] 支撑: ${actualSupportPrice.toFixed(2)} (日期: ${dateOnly})`);
                    }
                    
                    // 添加压力线（黄色）
                    if (pressurePrice !== undefined && pressurePrice !== null) {
                        const actualPressurePrice = pressurePrice / 100;
                        markLineData.push({
                            name: '压力',
                            yAxis: actualPressurePrice,
                            lineStyle: {
                                color: '#FFD700',
                                width: 2
                            },
                            label: {
                                color: '#000',
                                backgroundColor: '#FFD700'
                            }
                        });
                        console.log(`[压力支撑线] 压力: ${actualPressurePrice.toFixed(2)} (日期: ${dateOnly})`);
                    } else {
                        // 调试：没有数据的情况（降低日志频率）
                        if (Math.random() < 0.1) {  // 只打印10%的情况，避免刷屏
                            console.log(`[压力支撑线] 日期 ${dateOnly} 没有压力/支撑线数据`);
                        }
                    }
                    
                    // 更新markLine
                    chart.setOption({
                        series: [{
                            markLine: {
                                data: markLineData
                            }
                        }]
                    });
                }
            }
        });

        // 监听鼠标移出图表区域，清除markLine
        chart.off('globalout');
        chart.on('globalout', function() {
            lastHoverDate = null;  // 重置记录
            chart.setOption({
                series: [{
                    markLine: {
                        data: []
                    }
                }]
            });
        });

        if (analysisData && Object.keys(analysisData).length > 0) {
            updateAnalysisInfo(analysisData, latestData);
        } else {
            updateAnalysisInfo({}, latestData);
        }

        const resizeHandler = () => {
            if (chart) {
                chart.resize();
            }
        };
        
        window.removeEventListener('resize', resizeHandler);
        window.addEventListener('resize', resizeHandler);
        
    } catch (error) {
        console.error(`[${period}] renderChart异常:`, error);
        
        // 显示友好的错误提示
        const chartDom = document.getElementById('mainChart');
        if (chartDom && error.message && error.message.includes('ECharts')) {
            chartDom.innerHTML = `
                <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;padding:40px;text-align:center;background:#fff5f5;border-radius:8px;">
                    <div style="font-size:48px;margin-bottom:20px;">📊</div>
                    <div style="font-size:18px;color:#e53e3e;margin-bottom:10px;font-weight:bold;">图表加载失败</div>
                    <div style="font-size:14px;color:#666;margin-bottom:20px;">${error.message}</div>
                    <button onclick="location.reload()" style="padding:10px 20px;background:#4a90e2;color:white;border:none;border-radius:6px;cursor:pointer;font-size:14px;">🔄 刷新页面</button>
                </div>
            `;
        }
        
        throw error;
    }
}

// 更新分析信息
function updateAnalysisInfo(analysisData, latestData) {
    const winLoseRatioEl = document.getElementById('winLoseRatioValue');
    if (winLoseRatioEl) {
        const winLoseRatio = (analysisData && analysisData.winLoseRatio) || '--';
        winLoseRatioEl.textContent = typeof winLoseRatio === 'number' ? winLoseRatio.toFixed(2) : winLoseRatio;
    }
    
    const supportEl = document.getElementById('supportValue');
    if (supportEl) {
        const supportPrice = (analysisData && analysisData.supportPrice) || '--';
        supportEl.textContent = typeof supportPrice === 'number' ? supportPrice.toFixed(2) : supportPrice;
    }
    
    const pressureEl = document.getElementById('pressureValue');
    if (pressureEl) {
        const pressurePrice = (analysisData && analysisData.pressurePrice) || '--';
        pressureEl.textContent = typeof pressurePrice === 'number' ? pressurePrice.toFixed(2) : pressurePrice;
    }
}

// ============ CR点分析功能 ============

let crPointsData = { 
    c_points: [], 
    r_points: [], 
    rejected_c_points: [],
    strategy2_c_points: [],
    strategy2_scores: {},
    strategy1_scores: {}  // 添加策略1评分数据
};
let showCRPoints = true; // 默认显示CR点

// 自动获取最新一天的策略评分（快速版，不分析历史CR点）
async function analyzeCRPointsAuto() {
    if (!currentStockCode || !currentTableName) {
        return;
    }
    
    try {
        console.log('[快速加载] 开始获取最新一天的策略评分...', { stockCode: currentStockCode });
        
        // 🔥 只调用最新一天的CR点接口，不分析483天的历史数据
        const response = await fetch(`${API_BASE_URL}/latest_cr_points`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                stockCode: currentStockCode,
                tableName: currentTableName
            })
        });
        
        const result = await response.json();
        console.log('[快速加载] 最新一天策略评分结果:', result);
        
        // 🔥 后端返回的code是200，不是0！
        if (result.code === 200 && result.data && result.data.success) {
            const latestData = result.data;
            
            // 保存最新一天的策略评分到crPointsData
            if (latestData.date) {
                console.log(`✅ [快速加载] 获取到最新一天(${latestData.date})的策略评分`);
                
                // 初始化策略评分对象
                crPointsData.strategy1_scores = crPointsData.strategy1_scores || {};
                crPointsData.strategy2_scores = crPointsData.strategy2_scores || {};
                
                // 保存策略1评分
                if (latestData.strategy1) {
                    crPointsData.strategy1_scores[latestData.date] = latestData.strategy1;
                    console.log(`  ✅ 策略1评分: ${latestData.strategy1.score.toFixed(2)}`);
                }
                
                // 保存策略2评分
                if (latestData.strategy2) {
                    crPointsData.strategy2_scores[latestData.date] = latestData.strategy2;
                    console.log(`  ✅ 策略2评分: ${latestData.strategy2.score.toFixed(2)}`);
                }
                
                console.log('[快速加载] 策略评分已保存到crPointsData，可以显示tooltip');
            }
        } else {
            console.warn('[快速加载] 获取最新一天策略评分失败（可能今天没有数据）:', result.message || '未知错误');
        }
    } catch (error) {
        console.error('[快速加载] 获取最新一天策略评分失败:', error);
    }
}

// 手动分析CR点（带提示）
async function analyzeCRPoints() {
    if (!currentStockCode || !currentTableName) {
        console.warn('⚠️ 请先选择股票');
        return;
    }
    
    const stockSelect = document.getElementById('stockSelect');
    const selectedOption = stockSelect.options[stockSelect.selectedIndex];
    const stockName = selectedOption.dataset.name || '';
    
    const analyzeBtn = document.getElementById('analyzeCRBtn');
    if (analyzeBtn) {
        analyzeBtn.disabled = true;
        analyzeBtn.textContent = '分析中...';
    }
    
    try {
        console.log('开始分析CR点...', { stockCode: currentStockCode, stockName, tableName: currentTableName });
        
        const response = await fetch(`${API_BASE_URL}/cr_points/analyze`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                stockCode: currentStockCode,
                stockName: stockName,
                tableName: currentTableName,
                period: 'day'
            })
        });
        
        const result = await response.json();
        console.log('CR点分析结果:', result);
        
        // 调试：检查strategy1_scores
        if (result.data && result.data.strategy1_scores) {
            console.log('✅ strategy1_scores存在，数量:', Object.keys(result.data.strategy1_scores).length);
            const firstDate = Object.keys(result.data.strategy1_scores)[0];
            console.log('示例数据:', firstDate, result.data.strategy1_scores[firstDate]);
        } else {
            console.log('❌ strategy1_scores不存在或为空');
        }
        
        if (result.code === 200) {
            const cCount = result.data.c_points_count || 0;
            const rCount = result.data.r_points_count || 0;
            
            // 保存MACD数据（如果有）
            if (result.data.macd) {
                window.currentMACDData = result.data.macd;
                console.log('MACD数据已更新');
            }
            
            // 保存MA数据（如果有）
            if (result.data.ma) {
                window.currentMAData = result.data.ma;
                console.log('MA数据已更新', Object.keys(result.data.ma));
            }
            
            // 🔥 获取最新一天的CR点（如果有预测数据的话）
            try {
                console.log('正在获取最新一天的CR点...');
                const latestResponse = await fetch(`${API_BASE_URL}/latest_cr_points`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        stockCode: currentStockCode,
                        tableName: currentTableName
                    })
                });
                
                const latestResult = await latestResponse.json();
                console.log('最新一天CR点结果:', latestResult);
                
                // 🔥 后端返回的code是200，不是0！
                if (latestResult.code === 200 && latestResult.data && latestResult.data.success) {
                    const latestData = latestResult.data;
                    
                    // 合并最新一天的策略评分到历史数据中
                    if (latestData.date) {
                        console.log(`✅ 合并最新一天(${latestData.date})的CR点数据`);
                        
                        // 合并策略1评分
                        if (latestData.strategy1) {
                            result.data.strategy1_scores = result.data.strategy1_scores || {};
                            result.data.strategy1_scores[latestData.date] = latestData.strategy1;
                            console.log(`  ✅ 策略1评分: ${latestData.strategy1.score.toFixed(2)}`);
                            console.log(`  🔥 合并后strategy1_scores的日期:`, Object.keys(result.data.strategy1_scores));
                        }
                        
                        // 合并策略2评分
                        if (latestData.strategy2) {
                            result.data.strategy2_scores = result.data.strategy2_scores || {};
                            result.data.strategy2_scores[latestData.date] = latestData.strategy2;
                            console.log(`  ✅ 策略2评分: ${latestData.strategy2.score.toFixed(2)}`);
                            console.log(`  🔥 合并后strategy2_scores的日期:`, Object.keys(result.data.strategy2_scores));
                        }
                    }
                }
            } catch (latestError) {
                console.warn('获取最新一天CR点失败（可能今天没有数据）:', latestError);
            }
            
            // 🔥 自动加载时不弹提示框，控制台输出即可
            console.log(`✅ CR点加载完成！C点(买入信号): ${cCount}个, R点(卖出信号): ${rCount}个`);
            
            // 使用实时计算的结果直接显示
            await loadCRPoints(result.data);
        } else {
            console.error(`❌ CR点分析失败: ${result.message}`);
        }
    } catch (error) {
        console.error('❌ 分析CR点失败:', error);
    } finally {
        if (analyzeBtn) {
            analyzeBtn.disabled = false;
            analyzeBtn.textContent = '🎯 分析CR点';
        }
    }
}

// 加载CR点数据（实时计算）
async function loadCRPoints(existingData = null) {
    if (!currentStockCode) return;
    
    try {
        let c_points = [];
        let r_points = [];
        let rejected_c_points = [];
        
        // 如果传入了已有数据，直接使用
        if (existingData) {
            c_points = existingData.c_points || [];
            r_points = existingData.r_points || [];
            rejected_c_points = existingData.rejected_c_points || [];
            
            // 添加策略2相关数据
            if (existingData.strategy2_c_points) {
                crPointsData.strategy2_c_points = existingData.strategy2_c_points;
            }
            if (existingData.strategy2_scores) {
                crPointsData.strategy2_scores = existingData.strategy2_scores;
            }
            
            // 添加策略1评分数据
            if (existingData.strategy1_scores) {
                crPointsData.strategy1_scores = existingData.strategy1_scores;
                console.log('✅ 保存strategy1_scores到crPointsData，数量:', Object.keys(existingData.strategy1_scores).length);
            }
            
            console.log('使用已有的CR点数据:', { 
                c_points: c_points.length, 
                r_points: r_points.length,
                rejected_c_points: rejected_c_points.length,
                strategy2_c_points: (existingData.strategy2_c_points || []).length,
                strategy2_scores: Object.keys(existingData.strategy2_scores || {}).length
            });
        } else {
            // 否则进行实时计算
            const stockSelect = document.getElementById('stockSelect');
            const selectedOption = stockSelect.options[stockSelect.selectedIndex];
            const stockName = selectedOption.dataset.name || '';
            
            console.log('实时计算CR点...', { stockCode: currentStockCode, stockName });
            
            const response = await fetch(`${API_BASE_URL}/cr_points/analyze`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    stockCode: currentStockCode,
                    stockName: stockName,
                    tableName: currentTableName,
                    period: 'day'
                })
            });
            
            const result = await response.json();
            console.log('实时计算CR点结果:', result);
            
            if (result.code === 200) {
                c_points = result.data.c_points || [];
                r_points = result.data.r_points || [];
                rejected_c_points = result.data.rejected_c_points || [];
                
                // 保存策略2相关数据
                if (result.data.strategy2_c_points) {
                    crPointsData.strategy2_c_points = result.data.strategy2_c_points;
                }
                if (result.data.strategy2_scores) {
                    crPointsData.strategy2_scores = result.data.strategy2_scores;
                }
                
                // 🔥 获取最新一天的CR点（如果有预测数据的话）
                try {
                    console.log('正在获取最新一天的CR点...');
                    const latestResponse = await fetch(`${API_BASE_URL}/latest_cr_points`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            stockCode: currentStockCode,
                            tableName: currentTableName
                        })
                    });
                    
                    const latestResult = await latestResponse.json();
                    console.log('最新一天CR点结果:', latestResult);
                    
                    if (latestResult.code === 0 && latestResult.data && latestResult.data.success) {
                        const latestData = latestResult.data;
                        
                        // 合并最新一天的策略评分
                        if (latestData.date) {
                            console.log(`✅ 合并最新一天(${latestData.date})的CR点数据`);
                            
                            // 合并策略1评分
                            if (latestData.strategy1) {
                                result.data.strategy1_scores = result.data.strategy1_scores || {};
                                result.data.strategy1_scores[latestData.date] = latestData.strategy1;
                                crPointsData.strategy1_scores = result.data.strategy1_scores;
                                console.log(`  ✅ 策略1评分: ${latestData.strategy1.score.toFixed(2)}`);
                            }
                            
                            // 合并策略2评分
                            if (latestData.strategy2) {
                                result.data.strategy2_scores = result.data.strategy2_scores || {};
                                result.data.strategy2_scores[latestData.date] = latestData.strategy2;
                                crPointsData.strategy2_scores = result.data.strategy2_scores;
                                console.log(`  ✅ 策略2评分: ${latestData.strategy2.score.toFixed(2)}`);
                            }
                        }
                    }
                } catch (latestError) {
                    console.warn('获取最新一天CR点失败（可能今天没有数据）:', latestError);
                }
            } else {
                console.error('实时计算CR点失败:', result.message);
                return;
            }
        }
        
        // 保存CR点数据
        crPointsData.c_points = c_points;
        crPointsData.r_points = r_points;
        crPointsData.rejected_c_points = rejected_c_points;
        
        // 默认显示CR点，更新图表
        if (chart) {
            updateChartWithCRPoints();
        }
        
        // 更新统计信息
        updateCRPointsStats();
        
        // 如果有C点数据且当前是日K线，更新回测提示
        if (c_points.length > 0 && currentPeriod === 'day') {
            const backtestHint = document.querySelector('.backtest-hint');
            if (backtestHint) {
                backtestHint.innerHTML = `✅ 已加载${c_points.length}个C点和${r_points.length}个R点，现在可以运行回测了！`;
                backtestHint.style.color = '#28a745';
            }
        }
        
    } catch (error) {
        console.error('加载CR点失败:', error);
    }
}

// 切换CR点显示
function toggleCRPoints() {
    showCRPoints = !showCRPoints;
    
    const toggleBtn = document.getElementById('toggleCRBtn');
    if (toggleBtn) {
        toggleBtn.textContent = showCRPoints ? '✅ 隐藏CR点' : '👁️ 显示CR点';
        toggleBtn.style.background = showCRPoints ? '#26a69a' : '#4a90e2';
    }
    
    if (chart) {
        updateChartWithCRPoints();
    }
}

// 更新图表显示CR点
function updateChartWithCRPoints() {
    if (!chart) return;
    
    // 只在日K线时显示CR点，30分钟、周线、月线不显示
    if (currentPeriod !== 'day') {
        console.log(`[${currentPeriod}] 非日K线，跳过CR点渲染`);
        return;
    }
    
    const currentOption = chart.getOption();
    let currentSeries = currentOption.series || [];
    
    // 移除旧的CR点标记系列
    currentSeries = currentSeries.filter(s => s.name !== 'C点' && s.name !== 'R点' && s.name !== '被否决C点' && s.name !== '策略2C');
    
    if (showCRPoints && crPointsData) {
        const dates = currentOption.xAxis[0].data;
        
        // 创建一个日期映射，将K线的日期转换为日期字符串（去掉时间部分）用于匹配
        const dateMap = new Map();
        dates.forEach((dateStr, index) => {
            // K线日期格式可能是 '2024-01-01 00:00:00' 或 '2024-01-01'
            const dateOnly = dateStr.substring(0, 10); // 取前10个字符 'YYYY-MM-DD'
            if (!dateMap.has(dateOnly)) {
                dateMap.set(dateOnly, index);
            }
        });
        
        // 添加C点标记（金色或红色，在K线下方）
        if (crPointsData.c_points && crPointsData.c_points.length > 0) {
            const cPointData = crPointsData.c_points.map(point => {
                const dateStr = point.triggerDate; // CR点日期格式是 'YYYY-MM-DD'
                const index = dateMap.get(dateStr);
                if (index !== undefined && index >= 0) {
                    // 判断是否为金色C点
                    const isGolden = point.isGolden || false;
                    const cColor = isGolden ? '#FFD700' : '#ff0000';  // 金色或红色
                    
                    return {
                        value: [index, point.lowPrice],
                        cPointInfo: {
                            score: point.score || 0,
                            strategy: point.strategyName || '策略一',
                            date: point.triggerDate,
                            plugins: point.plugins || [],
                            isGolden: isGolden
                        },
                        itemStyle: {
                            color: cColor,
                            borderColor: '#fff',
                            borderWidth: 2
                        },
                        symbolSize: 25,
                        label: {
                            show: true,
                            formatter: 'C',
                            position: 'inside',
                            color: '#ffffff',
                            fontSize: 14,
                            fontWeight: 'bold'
                        }
                    };
                }
                return null;
            }).filter(item => item !== null);
            
            if (cPointData.length > 0) {
                const cPointSeries = {
                    name: 'C点',
                    type: 'scatter',
                    data: cPointData,
                    symbol: 'circle',
                    symbolSize: 25,
                    z: 100
                };
                currentSeries.push(cPointSeries);
            }
        }
        
        // 被否决的C点不显示在图表上（隐藏）
        // 如果需要显示，取消下面的注释
        /*
        if (crPointsData.rejected_c_points && crPointsData.rejected_c_points.length > 0) {
            const rejectedCPointData = crPointsData.rejected_c_points.map(point => {
                const dateStr = point.triggerDate;
                const index = dateMap.get(dateStr);
                if (index !== undefined && index >= 0) {
                    return {
                        value: [index, point.lowPrice],
                        cPointInfo: {
                            score: point.score || 0,
                            strategy: point.strategyName || '策略一 (被插件否决)',
                            date: point.triggerDate,
                            plugins: point.plugins || [],
                            isRejected: true
                        },
                        itemStyle: {
                            color: '#ff9800',
                            borderColor: '#fff',
                            borderWidth: 2
                        },
                        symbolSize: 25,
                        label: {
                            show: true,
                            formatter: 'C?',
                            position: 'inside',
                            color: '#ffffff',
                            fontSize: 12,
                            fontWeight: 'bold'
                        }
                    };
                }
                return null;
            }).filter(item => item !== null);
            
            if (rejectedCPointData.length > 0) {
                const rejectedCPointSeries = {
                    name: '被否决C点',
                    type: 'scatter',
                    data: rejectedCPointData,
                    symbol: 'circle',
                    symbolSize: 25,
                    z: 99
                };
                currentSeries.push(rejectedCPointSeries);
            }
        }
        */
        
        // 添加策略2 C点标记（金色或紫色矩形，在K线下方，标记为"C"）
        if (crPointsData.strategy2_c_points && crPointsData.strategy2_c_points.length > 0) {
            const strategy2CPointData = crPointsData.strategy2_c_points.map(point => {
                const dateStr = point.triggerDate;
                const index = dateMap.get(dateStr);
                if (index !== undefined && index >= 0) {
                    // 判断是否为金色C点
                    const isGolden = point.isGolden || false;
                    const s2Color = isGolden ? '#FFD700' : '#9C27B0';  // 金色或紫色
                    
                    return {
                        value: [index, point.lowPrice * 0.995],  // 略微降低位置，避免与策略1重叠
                        cPointInfo: {
                            score: point.score || 0,
                            strategy: point.strategyName || '策略二',
                            date: point.triggerDate,
                            plugins: [],
                            isGolden: isGolden
                        },
                        itemStyle: {
                            color: s2Color,  // 金色或紫色
                            borderColor: '#fff',
                            borderWidth: 2
                        },
                        symbolSize: 24,
                        label: {
                            show: true,
                            formatter: 'C',
                            position: 'inside',
                            color: '#ffffff',
                            fontSize: 12,
                            fontWeight: 'bold'
                        }
                    };
                }
                return null;
            }).filter(item => item !== null);
            
            if (strategy2CPointData.length > 0) {
                const strategy2CPointSeries = {
                    name: '策略2C',
                    type: 'scatter',
                    data: strategy2CPointData,
                    symbol: 'rect',  // 使用紫色矩形区分策略1
                    symbolSize: [24, 18],
                    z: 101  // 比普通C点稍高一层
                };
                currentSeries.push(strategy2CPointSeries);
            }
        }
        
        // 添加R点标记（绿色，在K线上方）
        if (crPointsData.r_points && crPointsData.r_points.length > 0) {
            const rPointData = crPointsData.r_points.map(point => {
                const dateStr = point.triggerDate;
                const index = dateMap.get(dateStr);
                if (index !== undefined && index >= 0) {
                    return {
                        value: [index, point.highPrice],
                        rPointInfo: {
                            strategy: point.strategyName || 'R点策略',
                            date: point.triggerDate,
                            plugins: point.plugins || []
                        },
                        itemStyle: {
                            color: '#00cc00',  // 绿色（卖出信号）
                            borderColor: '#fff',
                            borderWidth: 2
                        },
                        symbolSize: 25,
                        label: {
                            show: true,
                            formatter: 'R',
                            position: 'inside',
                            color: '#ffffff',
                            fontSize: 14,
                            fontWeight: 'bold'
                        }
                    };
                }
                return null;
            }).filter(item => item !== null);
            
            if (rPointData.length > 0) {
                const rPointSeries = {
                    name: 'R点',
                    type: 'scatter',
                    data: rPointData,
                    symbol: 'circle',
                    symbolSize: 25,
                    z: 100
                };
                currentSeries.push(rPointSeries);
            }
        }
    }
    
    chart.setOption({
        series: currentSeries
    });
}

// 更新CR点统计信息
function updateCRPointsStats() {
    const statsEl = document.getElementById('crPointsStats');
    if (statsEl) {
        // 只在日K线时显示CR点统计
        if (currentPeriod !== 'day') {
            statsEl.textContent = '仅日K线支持';
            return;
        }
        
        // c_points现在只包含策略1的C点
        const strategy1Count = crPointsData.c_points ? crPointsData.c_points.length : 0;
        const strategy2Count = crPointsData.strategy2_c_points ? crPointsData.strategy2_c_points.length : 0;
        const totalCCount = strategy1Count + strategy2Count;
        const rCount = crPointsData.r_points ? crPointsData.r_points.length : 0;
        
        // 显示C点和R点数量，区分策略1和策略2
        let text = `C点(买入): ${totalCCount}`;
        if (strategy2Count > 0) {
            text += ` (策略1:${strategy1Count}, 策略2:${strategy2Count})`;
        }
        text += ` | R点(卖出): ${rCount}`;
        statsEl.textContent = text;
    }
}

// 更新回测按钮状态
function updateBacktestButtonState(period) {
    const backtestBtn = document.getElementById('backtestBtn');
    const backtestHint = document.querySelector('.backtest-hint');
    
    if (!backtestBtn) return;
    
    if (period === 'day') {
        backtestBtn.disabled = false;
        backtestBtn.style.opacity = '1';
        backtestBtn.style.cursor = 'pointer';
        if (backtestHint) {
            backtestHint.innerHTML = '💡 当前为日K线，可以运行回测';
            backtestHint.style.color = '#28a745';
        }
    } else {
        backtestBtn.disabled = true;
        backtestBtn.style.opacity = '0.5';
        backtestBtn.style.cursor = 'not-allowed';
        if (backtestHint) {
            backtestHint.innerHTML = '⚠️ 回测功能仅支持日K线，请切换到日K线周期';
            backtestHint.style.color = '#ffc107';
        }
    }
}

// 回测功能
async function runBacktest() {
    try {
        // 检查是否有股票数据
        if (!currentStockCode || !currentTableName) {
            alert('请先选择股票');
            return;
        }
        
        // 检查是否是日K线
        if (currentPeriod !== 'day') {
            alert('回测功能仅支持日K线，请切换到日K线周期后再试');
            return;
        }
        
        // 检查是否有CR点数据（策略1或策略2的C点）
        const hasCPoints = crPointsData && (
            (crPointsData.c_points && crPointsData.c_points.length > 0) ||
            (crPointsData.strategy2_c_points && crPointsData.strategy2_c_points.length > 0)
        );
        
        if (!hasCPoints) {
            alert('当前没有C点数据，无法进行回测\n\n提示：\n1. 请确保已切换到日K线\n2. 系统会自动分析日K线的CR点\n3. 等待CR点加载完成后再点击回测');
            return;
        }
        
        const backtestResult = document.getElementById('backtestResult');
        backtestResult.innerHTML = `
            <div class="loading" style="padding: 20px;">
                <div class="spinner"></div>
                <p>正在计算回测结果...</p>
            </div>
        `;
        
        console.log('='.repeat(60));
        console.log('开始回测:');
        console.log('  股票代码:', currentStockCode);
        console.log('  表名:', currentTableName);
        
        // 合并策略1和策略2的C点
        const allCPoints = [
            ...(crPointsData.c_points || []),
            ...(crPointsData.strategy2_c_points || [])
        ];
        
        console.log('  策略1 C点数量:', (crPointsData.c_points || []).length);
        console.log('  策略2 C点数量:', (crPointsData.strategy2_c_points || []).length);
        console.log('  总C点数量:', allCPoints.length);
        console.log('  R点数量:', crPointsData.r_points.length);
        console.log('  所有C点详情:', allCPoints);
        console.log('  R点详情:', crPointsData.r_points);
        
        // 调用回测API
        const response = await fetch(`${API_BASE_URL}/backtest`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                stockCode: currentStockCode,
                tableName: currentTableName,
                cPoints: allCPoints,
                rPoints: crPointsData.r_points
            })
        });
        
        const result = await response.json();
        console.log('回测响应:', result);
        
        // 检查业务逻辑是否成功（无论HTTP状态码）
        if (result.code !== 200 || !response.ok) {
            // 显示详细的错误信息
            backtestResult.innerHTML = `
                <div class="error" style="padding: 30px; text-align: center;">
                    <h3>❌ 回测失败</h3>
                    <p style="margin-top: 15px; font-size: 14px; color: #ff6b6b; line-height: 1.6;">
                        ${result.message || '回测失败'}
                    </p>
                    <div style="margin-top: 20px; padding: 15px; background: rgba(255,107,107,0.1); border-radius: 8px; font-size: 13px; color: #ffa07a;">
                        <strong>💡 提示：</strong><br>
                        1. 该股票可能没有30分钟K线数据<br>
                        2. 尝试选择其他股票进行回测<br>
                        3. 或联系管理员检查数据同步
                    </div>
                </div>
            `;
            return;
        }
        
        // 显示回测结果
        displayBacktestResult(result.data);
        
    } catch (error) {
        console.error('回测失败:', error);
        const backtestResult = document.getElementById('backtestResult');
        backtestResult.innerHTML = `
            <div class="error" style="padding: 20px;">
                <h3>❌ 回测失败</h3>
                <p>${error.message}</p>
            </div>
        `;
    }
}

// 显示回测结果
function displayBacktestResult(data) {
    const backtestResult = document.getElementById('backtestResult');
    const summary = data.summary;
    const trades = data.trades;
    
    // 如果没有任何交易数据
    if (!trades || trades.length === 0) {
        backtestResult.innerHTML = `
            <div class="error" style="padding: 30px; text-align: center;">
                <h3>⚠️ 无法生成回测数据</h3>
                <p style="margin-top: 15px; font-size: 14px; color: #8899aa;">
                    可能的原因：<br><br>
                    1. 该股票数据库中没有30分钟K线数据<br>
                    2. C点触发日期之后没有30分钟K线数据<br>
                    3. 数据不完整<br><br>
                    回测需要30分钟K线数据来计算买卖价格
                </p>
            </div>
        `;
        return;
    }
    
    let html = `
        <div class="backtest-summary">
            <h3>📊 回测汇总</h3>
            <div class="summary-grid">
                <div class="summary-item">
                    <span class="summary-label">总交易次数</span>
                    <span class="summary-value">${summary.total_trades || 0}</span>
                </div>
                <div class="summary-item">
                    <span class="summary-label">已完成</span>
                    <span class="summary-value">${summary.completed_trades || 0}</span>
                </div>
                <div class="summary-item">
                    <span class="summary-label">持仓中</span>
                    <span class="summary-value">${summary.holding_trades || 0}</span>
                </div>
                <div class="summary-item ${summary.win_rate >= 50 ? 'positive' : 'negative'}">
                    <span class="summary-label">胜率</span>
                    <span class="summary-value">${summary.win_rate || 0}%</span>
                </div>
                <div class="summary-item ${summary.avg_return >= 0 ? 'positive' : 'negative'}">
                    <span class="summary-label">平均收益率</span>
                    <span class="summary-value">${summary.avg_return >= 0 ? '+' : ''}${summary.avg_return || 0}%</span>
                </div>
                <div class="summary-item ${summary.total_return >= 0 ? 'positive' : 'negative'}">
                    <span class="summary-label">累计收益率</span>
                    <span class="summary-value">${summary.total_return >= 0 ? '+' : ''}${summary.total_return || 0}%</span>
                </div>
                <div class="summary-item positive">
                    <span class="summary-label">最大收益</span>
                    <span class="summary-value">+${summary.max_return || 0}%</span>
                </div>
                <div class="summary-item negative">
                    <span class="summary-label">最大亏损</span>
                    <span class="summary-value">${summary.min_return || 0}%</span>
                </div>
                <div class="summary-item">
                    <span class="summary-label">平均持仓天数</span>
                    <span class="summary-value">${summary.avg_holding_days || 0}天</span>
                </div>
                <div class="summary-item positive">
                    <span class="summary-label">盈利笔数</span>
                    <span class="summary-value">${summary.win_count || 0}</span>
                </div>
                <div class="summary-item negative">
                    <span class="summary-label">亏损笔数</span>
                    <span class="summary-value">${summary.loss_count || 0}</span>
                </div>
                <div class="summary-item ${summary.holding_return >= 0 ? 'positive' : 'negative'}">
                    <span class="summary-label">持仓浮动盈亏</span>
                    <span class="summary-value">${summary.holding_return >= 0 ? '+' : ''}${summary.holding_return || 0}%</span>
                </div>
            </div>
        </div>
        
        <div class="backtest-trades">
            <h3>📋 交易明细</h3>
            <div class="trades-table-container">
                <table class="trades-table">
                    <thead>
                        <tr>
                            <th>序号</th>
                            <th>C点日期</th>
                            <th>策略</th>
                            <th>买入价</th>
                            <th>R点日期</th>
                            <th>卖出价</th>
                            <th>收益率</th>
                            <th>持仓天数</th>
                            <th>状态</th>
                        </tr>
                    </thead>
                    <tbody>
    `;
    
    trades.forEach((trade, index) => {
        const returnClass = trade.return_rate > 0 ? 'positive' : (trade.return_rate < 0 ? 'negative' : '');
        const statusText = trade.status === 'holding' ? '持仓中' : '已完成';
        const statusClass = trade.status === 'holding' ? 'holding' : 'completed';
        
        html += `
            <tr>
                <td>${index + 1}</td>
                <td>${trade.c_date}</td>
                <td>${trade.c_strategy}</td>
                <td>¥${trade.buy_price}</td>
                <td>${trade.r_date || '-'}</td>
                <td>${trade.sell_price ? '¥' + trade.sell_price : '-'}</td>
                <td class="${returnClass}">${trade.return_rate !== null ? (trade.return_rate >= 0 ? '+' : '') + trade.return_rate + '%' : '-'}</td>
                <td>${trade.days !== null ? trade.days + '天' : '-'}</td>
                <td><span class="status-badge ${statusClass}">${statusText}${trade.status === 'holding' && trade.return_rate !== null ? ' (浮盈亏' + (trade.return_rate >= 0 ? '+' : '') + trade.return_rate + '%)' : ''}</span></td>
            </tr>
        `;
    });
    
    html += `
                    </tbody>
                </table>
            </div>
        </div>
    `;
    
    backtestResult.innerHTML = html;
}

// 启动自动刷新（每分钟更新一次最新K线）
function startAutoRefresh() {
    // 清除已有的定时器
    stopAutoRefresh();
    
    console.log('[自动刷新] 启动定时器，每60秒更新一次最新K线');
    
    // 设置定时器，每60秒更新一次
    autoRefreshInterval = setInterval(async () => {
        if (currentPeriod === 'day' && currentTableName && chart) {
            console.log('[自动刷新] 开始更新最新K线数据...');
            try {
                await refreshLatestKline();
            } catch (error) {
                console.error('[自动刷新] 更新失败:', error);
            }
        } else {
            console.log('[自动刷新] 条件不满足，跳过更新');
            stopAutoRefresh();
        }
    }, 60000); // 60秒
}

// 停止自动刷新
function stopAutoRefresh() {
    if (autoRefreshInterval) {
        console.log('[自动刷新] 停止定时器');
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}

// 刷新最新K线数据
async function refreshLatestKline() {
    try {
        console.log('[刷新最新K线] 获取最新数据...');
        const latestKlineData = await fetchLatestDayKline(currentTableName);
        
        if (!latestKlineData || !chart) {
            console.log('[刷新最新K线] 没有新数据或图表不存在');
            return;
        }
        
        // 获取当前图表配置
        const currentOption = chart.getOption();
        const currentDates = currentOption.xAxis[0].data;
        const currentValues = currentOption.series[0].data;
        
        // 【修复】找到成交量series（通过name查找）
        let volumeSeries = null;
        for (let series of currentOption.series) {
            if (series.name === '成交量') {
                volumeSeries = series;
                break;
            }
        }
        
        if (!volumeSeries) {
            console.error('[刷新最新K线] 找不到成交量series');
            return;
        }
        
        console.log('[刷新最新K线] 找到成交量series，数据长度:', volumeSeries.data.length);
        
        // 获取最新K线的日期
        const latestDate = latestKlineData.time.split(' ')[0];
        
        // 查找该日期在当前数据中的位置
        const existingIndex = currentDates.findIndex(date => {
            return date.split(' ')[0] === latestDate;
        });
        
        let needUpdate = false;
        let klineData = [];
        
        if (existingIndex >= 0) {
            // 如果已存在，检查数据是否有变化
            const existingValue = currentValues[existingIndex];
            const existingVolume = volumeSeries.data[existingIndex];
            
            if (existingValue[0] !== latestKlineData.open || 
                existingValue[1] !== latestKlineData.close ||
                existingValue[2] !== latestKlineData.low ||
                existingValue[3] !== latestKlineData.high ||
                existingVolume !== latestKlineData.volume) {  // 【新增】也检查成交量变化
                
                console.log('[刷新最新K线] 数据有变化，更新图表');
                needUpdate = true;
                
                // 重建完整的K线数据
                klineData = currentDates.map((date, index) => {
                    if (index === existingIndex) {
                        return latestKlineData;
                    } else {
                        const value = currentValues[index];
                        const volumeData = volumeSeries.data[index];  // 【修复】使用找到的成交量series
                        return {
                            time: date,
                            open: value[0],
                            close: value[1],
                            low: value[2],
                            high: value[3],
                            volume: volumeData,
                            liangbi: 0,  // 历史数据的liangbi和weibi不重要，设为0
                            weibi: 0
                        };
                    }
                });
                
                // 验证成交量数据
                const volumeCount = klineData.filter(k => k.volume && k.volume > 0).length;
                console.log('[刷新最新K线] 重建后K线数据量:', klineData.length, '有成交量的数据:', volumeCount);
            } else {
                console.log('[刷新最新K线] 数据未变化，跳过更新');
            }
        } else {
            // 如果不存在，说明是新的交易日
            console.log('[刷新最新K线] 发现新交易日，追加数据');
            needUpdate = true;
            
            // 重建完整的K线数据并追加
            klineData = currentDates.map((date, index) => {
                const value = currentValues[index];
                const volumeData = volumeSeries.data[index];  // 【修复】使用找到的成交量series
                return {
                    time: date,
                    open: value[0],
                    close: value[1],
                    low: value[2],
                    high: value[3],
                    volume: volumeData,
                    liangbi: 0,  // 历史数据的liangbi和weibi不重要，设为0
                    weibi: 0
                };
            });
            klineData.push(latestKlineData);
            
            // 验证成交量数据
            const volumeCount = klineData.filter(k => k.volume && k.volume > 0).length;
            console.log('[刷新最新K线] 重建后K线数据量:', klineData.length, '有成交量的数据:', volumeCount);
        }
        
        if (needUpdate) {
            // 重新计算MA和MACD
            console.log('[刷新最新K线] 重新计算技术指标...');
            console.log('[刷新最新K线] K线数据长度:', klineData.length);
            const macdData = calculateMACD(klineData);
            const maData = calculateMA(klineData, [5, 10, 20]);
            console.log('[刷新最新K线] MA5长度:', maData.ma5?.length, 'MA10长度:', maData.ma10?.length, 'MA20长度:', maData.ma20?.length);
            
            // 更新全局数据
            window.currentMACDData = macdData;
            window.currentMAData = maData;
            
            // 更新预测成交量
            try {
                const predicted = await fetchPredictedVolume(currentTableName);
                predictedVolume = predicted;
                console.log('[刷新最新K线] 预测成交量已更新:', predictedVolume);
            } catch (error) {
                console.error('[刷新最新K线] 更新预测成交量失败:', error);
            }
            
            // 获取最新的CR点数据（仅获取当天的，不重新计算历史数据）
            try {
                const latestResponse = await fetch(`${API_BASE_URL}/latest_cr_points`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        stockCode: currentStockCode,
                        tableName: currentTableName
                    })
                });
                
                const latestResult = await latestResponse.json();
                console.log('[刷新最新K线] 获取最新CR点数据成功:', latestResult);
                
                if (latestResult.code === 200 && latestResult.data && latestResult.data.success) {
                    const latestData = latestResult.data;
                    
                    // 更新策略评分（如果有）
                    if (latestData.date) {
                        // 更新策略1评分
                        if (latestData.strategy1) {
                            if (!crPointsData.strategy1_scores) {
                                crPointsData.strategy1_scores = {};
                            }
                            crPointsData.strategy1_scores[latestData.date] = latestData.strategy1;
                            console.log(`[刷新最新K线] 更新策略1评分: ${latestData.strategy1.score.toFixed(2)}`);
                        }
                        
                        // 更新策略2评分
                        if (latestData.strategy2) {
                            if (!crPointsData.strategy2_scores) {
                                crPointsData.strategy2_scores = {};
                            }
                            crPointsData.strategy2_scores[latestData.date] = latestData.strategy2;
                            console.log(`[刷新最新K线] 更新策略2评分: ${latestData.strategy2.score.toFixed(2)}`);
                        }
                    }
                }
            } catch (latestError) {
                console.warn('[刷新最新K线] 获取最新CR点失败:', latestError);
            }
            
            // 重新渲染图表，保留现有的CR点数据
            console.log('[刷新最新K线] 重新渲染图表...');
            await renderChart(klineData, {}, 'day');
            
            // 更新CR点显示
            if (chart) {
                updateChartWithCRPoints();
            }
            
            console.log('[刷新最新K线] ✅ 更新完成');
        }
        
    } catch (error) {
        console.error('[刷新最新K线] 刷新失败:', error);
    }
}

// 页面加载时初始化
window.onload = initApp;

// 页面卸载时清理定时器
window.onbeforeunload = () => {
    stopAutoRefresh();
};

