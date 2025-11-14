// 阿尔法策略2.0系统 - 主应用脚本
const API_BASE_URL = 'http://localhost:5000/api';
let allStockGroups = {};
let currentStrategy = '波段';
let currentStockCode = '';
let currentTableName = '';
let availablePeriods = {};
let chart = null;
let currentAnalysisController = null;
let volumeTypeMap = {}; // 存储成交量类型数据，key为日期字符串，value为成交量类型
let winRatioScoreMap = {}; // 存储赔率总分数据，key为日期字符串，value为total_win_ratio_score
let bullishPatternMap = {}; // 存储多头组合数据，key为日期字符串，value为多头组合

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
        option.dataset.table = stock.table;
        stockSelect.appendChild(option);
    });
}

// 筛选股票（搜索功能）
function filterStocks() {
    const searchText = document.getElementById('searchInput').value.toLowerCase();
    const stockSelect = document.getElementById('stockSelect');
    const options = stockSelect.querySelectorAll('option');
    
    options.forEach((option, index) => {
        if (index === 0) return;
        
        const text = option.textContent.toLowerCase();
        if (text.includes(searchText)) {
            option.style.display = '';
        } else {
            option.style.display = 'none';
        }
    });

    if (!searchText) {
        stockSelect.value = '';
    }
}

// 选择股票
async function selectStock() {
    const stockSelect = document.getElementById('stockSelect');
    const selectedOption = stockSelect.options[stockSelect.selectedIndex];
    
    if (!stockSelect.value) {
        showEmptyState();
        return;
    }

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

        if (!klineResult.data || klineResult.data.length === 0) {
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

        console.log(`[${period}] ✅ 立即启动分析数据加载（并行）`);
        const analysisPromise = loadAnalysisData(stockCode, period, klineResult.data).catch(err => {
            console.error(`[${period}] 分析数据加载异常:`, err);
        });

        // 如果是日K线，加载成交量类型数据
        if (period === 'day') {
            console.log(`[${period}] 开始加载成交量类型数据...`);
            loadVolumeTypes(stockCode).catch(err => {
                console.error(`[${period}] 成交量类型数据加载异常:`, err);
            });
        } else {
            // 非日K线，清空成交量类型、赔率总分和多头组合数据
            volumeTypeMap = {};
            winRatioScoreMap = {};
            bullishPatternMap = {};
        }

        console.log(`[${period}] 开始渲染K线，数据点数: ${klineResult.data.length}`);
        try {
            renderChart(klineResult.data, {}, period);
            updateActivePeriodButton(period);
            console.log(`[${period}] K线渲染成功`);
            
            // 实时计算并加载CR点数据（仅日K线支持）
            if (period === 'day') {
                console.log('[日K线] 开始实时计算C点...');
                analyzeCRPointsAuto().catch(err => {
                    console.error('实时计算C点失败:', err);
                });
            }
        } catch (error) {
            console.error(`[${period}] K线渲染失败:`, error);
            throw error;
        }

    } catch (error) {
        console.error(`加载${stockCode}数据失败:`, error);
        document.getElementById('mainChart').innerHTML = `
            <div class="error">
                <p>📊 数据加载失败</p>
                <p style="font-size: 12px; margin-top: 10px;">${error.message}</p>
                <button onclick="selectStock()" 
                        style="margin-top: 15px; padding: 8px 20px; background: #4a90e2; border: none; border-radius: 5px; color: white; cursor: pointer; font-size: 12px;">
                    重试
                </button>
            </div>
        `;
    }
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

        // 将数据转换为日期到成交量类型、赔率总分和多头组合的映射
        volumeTypeMap = {};
        winRatioScoreMap = {};
        bullishPatternMap = {};
        if (result.data && Array.isArray(result.data)) {
            result.data.forEach(item => {
                if (item.date) {
                    // 处理日期格式，确保是 YYYY-MM-DD 格式
                    const dateStr = item.date.split(' ')[0];
                    if (item.volumeType) {
                        volumeTypeMap[dateStr] = item.volumeType;
                    }
                    if (item.totalWinRatioScore !== undefined && item.totalWinRatioScore !== null) {
                        winRatioScoreMap[dateStr] = item.totalWinRatioScore;
                    }
                    if (item.bullishPattern) {
                        bullishPatternMap[dateStr] = item.bullishPattern;
                    }
                }
            });
            console.log(`每日机会数据加载成功，成交量类型: ${Object.keys(volumeTypeMap).length} 条，赔率总分: ${Object.keys(winRatioScoreMap).length} 条，多头组合: ${Object.keys(bullishPatternMap).length} 条`);
        }
    } catch (error) {
        console.error('加载成交量类型数据失败:', error);
        volumeTypeMap = {};
        winRatioScoreMap = {};
        bullishPatternMap = {};
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
function renderChart(klineData, analysisData, period) {
    try {
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
        
        console.log(`[${period}] 数据准备完成 - 日期数:${dates.length}, K线数:${values.length}, 成交量数:${volumes.length}`);

        const latestData = klineData[klineData.length - 1] || {};

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
                    params.forEach(param => {
                        if (param.seriesName === 'K线') {
                            result += `开盘: ${param.value[1]}<br/>`;
                            result += `收盘: ${param.value[2]}<br/>`;
                            result += `最低: ${param.value[3]}<br/>`;
                            result += `最高: ${param.value[4]}<br/>`;
                        } else if (param.seriesName === '成交量') {
                            result += `成交量: ${(param.value / 10000).toFixed(2)}万<br/>`;
                        } else if (param.seriesName === 'C点' || param.seriesName === '被否决C点') {
                            // C点显示得分信息
                            if (param.data && param.data.cPointInfo) {
                                const isRejected = param.data.cPointInfo.isRejected;
                                const titleColor = isRejected ? '#ff9800' : '#ff4444';
                                const titleText = isRejected ? '⚠️ 被插件否决的C点' : '⚫ C点触发';
                                
                                result += `<span style="color: ${titleColor}; font-weight: bold;">${titleText}</span><br/>`;
                                result += `<span style="color: #ffa500;">得分: ${param.data.cPointInfo.score.toFixed(2)} / 70</span><br/>`;
                                result += `<span style="color: #888; font-size: 11px;">${param.data.cPointInfo.strategy}</span><br/>`;
                                
                                // 显示触发的插件信息
                                if (param.data.cPointInfo.plugins && param.data.cPointInfo.plugins.length > 0) {
                                    result += `<br/><span style="color: #ffeb3b; font-weight: bold;">🔌 触发的插件:</span><br/>`;
                                    param.data.cPointInfo.plugins.forEach(plugin => {
                                        const icon = plugin.scoreAdjustment < 0 ? '⚠️' : '✓';
                                        const color = plugin.scoreAdjustment < 0 ? '#ff9800' : '#4caf50';
                                        result += `<span style="color: ${color}; font-size: 11px; margin-left: 10px;">${icon} ${plugin.pluginName}</span><br/>`;
                                        result += `<span style="color: #999; font-size: 10px; margin-left: 20px;">${plugin.reason}</span><br/>`;
                                        if (plugin.scoreAdjustment !== 0 && plugin.scoreAdjustment !== -999) {
                                            const scoreText = plugin.scoreAdjustment > 0 ? `+${plugin.scoreAdjustment}` : plugin.scoreAdjustment;
                                            result += `<span style="color: #999; font-size: 10px; margin-left: 20px;">分数调整: ${scoreText}分</span><br/>`;
                                        }
                                    });
                                }
                                
                                if (isRejected) {
                                    result += `<br/><span style="color: #ff5722; font-size: 11px;">💡 基础分达标但被插件规则否决</span>`;
                                }
                            } else {
                                result += `<span style="color: #ff4444;">⚫ C点</span><br/>`;
                            }
                        } else {
                            result += `${param.seriesName}: ${param.value}<br/>`;
                        }
                    });
                    
                    // 显示赔率总分、成交量类型和多头组合（仅日K线）
                    if (period === 'day' && params[0] && params[0].name) {
                        const dateStr = params[0].name;
                        // 处理日期格式，可能是 "2025-09-23 00:00:00" 或 "2025-09-23"
                        const dateOnly = dateStr.split(' ')[0];
                        
                        // 显示赔率总分
                        const winRatioScore = winRatioScoreMap[dateOnly];
                        if (winRatioScore !== undefined && winRatioScore !== null) {
                            result += `<br/><span style="color: #FFD700; font-weight: bold;">赔率总分: ${winRatioScore.toFixed(2)}</span>`;
                        }
                        
                        // 显示成交量类型
                        const volumeType = volumeTypeMap[dateOnly];
                        if (volumeType) {
                            // 将成交量类型列表格式化显示，每种类型换行
                            const types = volumeType.split(',');
                            const typeNames = {
                                'A': 'A(前1日2-3倍)',
                                'B': 'B(前3日均量2倍+)',
                                'C': 'C(前5日均量2倍+)',
                                'D': 'D(前5日ABC放量后1.2倍+)',
                                'E': 'E(前1日及前5日均值4倍+)',
                                'F': 'F(前5日ABCD放量后3倍+)',
                                'G': 'G(前5日ABCD放量后0.7倍+)',
                                'H': 'H(前5日ABCD放量后大于)',
                                'X': 'X(前3日均量1.5倍+)',
                                'Y': 'Y(前5日均量1.5倍+)',
                                'Z': 'Z(前10日ABC放量+昨日1.3倍+今日1.08倍)'
                            };
                            result += `<br/><span style="color: #4a90e2; font-weight: bold;">成交量类型:</span>`;
                            types.forEach(t => {
                                const typeLabel = typeNames[t.trim()] || t.trim();
                                result += `<br/><span style="color: #4a90e2; margin-left: 10px;">• ${typeLabel}</span>`;
                            });
                        }
                        
                        // 显示多头组合
                        const bullishPattern = bullishPatternMap[dateOnly];
                        if (bullishPattern) {
                            // 将多头组合列表格式化显示，每种组合换行
                            const patterns = bullishPattern.split(',');
                            result += `<br/><span style="color: #26a69a; font-weight: bold;">多头组合:</span>`;
                            patterns.forEach(p => {
                                const patternLabel = p.trim();
                                result += `<br/><span style="color: #26a69a; margin-left: 10px;">• ${patternLabel}</span>`;
                            });
                        }
                    }
                    
                    return result;
                }
            },
            grid: [
                {
                    left: '8%',
                    right: '8%',
                    top: '12%',
                    height: '52%'
                },
                {
                    left: '8%',
                    right: '8%',
                    top: '72%',
                    height: '18%'
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
                }
            ],
            dataZoom: [
                {
                    type: 'inside',
                    xAxisIndex: [0, 1],
                    start: calculateStartPercent(dates.length, period),
                    end: 100
                },
                {
                    show: true,
                    xAxisIndex: [0, 1],
                    type: 'slider',
                    bottom: '2%',
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
                }
            ]
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

let crPointsData = { c_points: [], r_points: [], rejected_c_points: [] };
let showCRPoints = true; // 默认显示CR点

// 自动实时计算CR点（不显示提示）
async function analyzeCRPointsAuto() {
    if (!currentStockCode || !currentTableName) {
        return;
    }
    
    const stockSelect = document.getElementById('stockSelect');
    const selectedOption = stockSelect.options[stockSelect.selectedIndex];
    const stockName = selectedOption.dataset.name || '';
    
    try {
        console.log('[实时计算] 开始计算C点...', { stockCode: currentStockCode, stockName });
        
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
        console.log('[实时计算] C点计算结果:', result);
        
        if (result.code === 200) {
            console.log(`[实时计算] 找到C点: ${result.data.c_points_count}个`);
            
            // 使用实时计算的结果直接显示
            await loadCRPoints(result.data);
        } else {
            console.error('[实时计算] C点计算失败:', result.message);
        }
    } catch (error) {
        console.error('[实时计算] C点计算失败:', error);
    }
}

// 手动分析CR点（带提示）
async function analyzeCRPoints() {
    if (!currentStockCode || !currentTableName) {
        alert('请先选择股票');
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
        
        if (result.code === 200) {
            alert(`CR点分析完成！\n找到C点(买入点): ${result.data.c_points_count}个`);
            
            // 使用实时计算的结果直接显示
            await loadCRPoints(result.data);
        } else {
            alert(`CR点分析失败: ${result.message}`);
        }
    } catch (error) {
        console.error('分析CR点失败:', error);
        alert(`分析CR点失败: ${error.message}`);
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
            console.log('使用已有的CR点数据:', { 
                c_points: c_points.length, 
                r_points: r_points.length,
                rejected_c_points: rejected_c_points.length
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
    
    const currentOption = chart.getOption();
    let currentSeries = currentOption.series || [];
    
    // 移除旧的CR点标记系列
    currentSeries = currentSeries.filter(s => s.name !== 'C点' && s.name !== 'R点' && s.name !== '被否决C点');
    
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
        
        // 添加C点标记（红色，在K线下方）
        if (crPointsData.c_points && crPointsData.c_points.length > 0) {
            const cPointData = crPointsData.c_points.map(point => {
                const dateStr = point.triggerDate; // CR点日期格式是 'YYYY-MM-DD'
                const index = dateMap.get(dateStr);
                if (index !== undefined && index >= 0) {
                    return {
                        value: [index, point.lowPrice],
                        cPointInfo: {
                            score: point.score || 0,
                            strategy: point.strategyName || '策略一',
                            date: point.triggerDate,
                            plugins: point.plugins || []
                        },
                        itemStyle: {
                            color: '#ff0000',
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
        
        // R点暂时不显示（等待后续需求）
        /*
        if (crPointsData.r_points && crPointsData.r_points.length > 0) {
            const rPointData = crPointsData.r_points.map(point => {
                const dateStr = point.triggerDate;
                const index = dateMap.get(dateStr);
                if (index !== undefined && index >= 0) {
                    return {
                        value: [index, point.highPrice],
                        itemStyle: {
                            color: '#00ff00',
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
        */
    }
    
    chart.setOption({
        series: currentSeries
    });
}

// 更新CR点统计信息
function updateCRPointsStats() {
    const statsEl = document.getElementById('crPointsStats');
    if (statsEl) {
        const cCount = crPointsData.c_points ? crPointsData.c_points.length : 0;
        // 只显示C点数量（被否决的不显示）
        statsEl.textContent = `C点: ${cCount}`;
    }
}

// 页面加载时初始化
window.onload = initApp;

