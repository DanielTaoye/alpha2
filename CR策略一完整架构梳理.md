# CR策略一完整架构梳理

## 目录
1. [系统概述](#系统概述)
2. [整体架构](#整体架构)
3. [数据流程](#数据流程)
4. [C点逻辑](#c点逻辑)
5. [R点逻辑](#r点逻辑)
6. [代码结构](#代码结构)
7. [性能优化](#性能优化)
8. [前端展示](#前端展示)

---

## 系统概述

### 核心概念
- **C点（Chance Point）**：买入信号点，基于赔率分+胜率分+插件系统
- **R点（Risk Point）**：卖出信号点，基于风险插件检测
- **策略一**：CR点的主策略，结合基础评分和插件规则

### 技术栈
- **后端**：Python + Flask
- **前端**：JavaScript + ECharts
- **数据库**：MySQL
- **架构模式**：DDD（领域驱动设计）

---

## 整体架构

### 分层架构

```
┌─────────────────────────────────────────────────┐
│              Frontend (前端)                     │
│  - ECharts 图表展示                              │
│  - CR点标记显示                                   │
│  - 插件信息弹窗                                   │
└────────────────┬────────────────────────────────┘
                 │ HTTP API
┌────────────────┴────────────────────────────────┐
│         Interface Layer (接口层)                 │
│  - CRPointController                            │
│  - 请求参数验证                                   │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────┴────────────────────────────────┐
│       Application Layer (应用层)                 │
│  - CRPointService                               │
│  - 业务流程编排                                   │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────┴────────────────────────────────┐
│         Domain Layer (领域层)                    │
│  ┌─────────────────┬──────────────────┐        │
│  │ CRStrategyService│ RPointPluginService│       │
│  │  (C点策略)        │   (R点插件)        │       │
│  └─────────────────┴──────────────────┘        │
│  │                                               │
│  │ CPointPluginService (C点插件)                │
│  └───────────────────────────────────┘        │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────┴────────────────────────────────┐
│     Infrastructure Layer (基础设施层)            │
│  - DailyRepositoryImpl                          │
│  - DailyChanceRepositoryImpl                    │
│  - KLineRepositoryImpl                          │
│  - DatabaseConnection                           │
└─────────────────────────────────────────────────┘
```

---

## 数据流程

### 1. 完整流程图

```
用户点击"分析CR点"
        ↓
[前端] app.js: analyzeCRPoints()
        ↓
POST /api/cr_points/analyze
        ↓
[接口层] CRPointController.analyze_cr_points()
        ↓
[应用层] CRPointService.analyze_cr_points()
        ↓
    ┌───┴───┐
    ↓       ↓
初始化缓存  遍历K线
    ↓       ↓
    │   检查C点 ← CRStrategyService
    │       ↓
    │   C点插件 ← CPointPluginService
    │       ↓
    │   检查R点 ← RPointPluginService
    │       ↓
    └───┬───┘
        ↓
    清空缓存
        ↓
    返回结果
        ↓
[前端] 显示C点和R点标记
```

### 2. 详细数据流

#### 步骤1：接口调用
```javascript
// frontend/js/app.js
fetch('/api/cr_points/analyze', {
    method: 'POST',
    body: JSON.stringify({
        stockCode: 'SH600000',
        stockName: '浦发银行',
        tableName: 'basic_data_sh600000',
        period: 'day'
    })
})
```

#### 步骤2：控制器处理
```python
# backend/interfaces/controllers/cr_point_controller.py
def analyze_cr_points(self):
    # 1. 获取请求参数
    data = request.get_json()
    
    # 2. 获取K线数据
    kline_data_list = self.kline_service.get_kline_data(
        table_name, period
    )
    
    # 3. 调用应用服务
    result = self.cr_service.analyze_cr_points(
        stock_code, stock_name, kline_objects
    )
    
    # 4. 返回结果
    return jsonify(ResponseBuilder.success(result))
```

#### 步骤3：应用服务编排
```python
# backend/application/services/cr_point_service.py
def analyze_cr_points(self, stock_code, stock_name, kline_data):
    # 1. 初始化缓存
    self.strategy_service.init_cache(stock_code, start_date, end_date)
    self.r_point_service.init_cache(stock_code, start_date, end_date)
    
    # 2. 遍历每个K线
    for kline in kline_data:
        # 检查C点
        is_c_point, c_score, ... = self.strategy_service.check_c_point_strategy_1(...)
        
        # 检查R点
        is_r_point, r_plugins = self.r_point_service.check_r_point(...)
    
    # 3. 清空缓存
    self.strategy_service.clear_cache()
    self.r_point_service.clear_cache()
    
    # 4. 返回结果
    return {
        'c_points': [...],
        'r_points': [...]
    }
```

---

## C点逻辑

### 核心公式

```
C点触发条件：最终分数 ≥ 70分

基础分 = 赔率分 + 胜率分

最终分 = 基础分 + 插件调整

其中：
- 赔率分：来自 daily_chance.total_win_ratio_score
- 胜率分：根据成交量类型计算
  * 温和放量(ABCD)：40分
  * 特殊型(H)：28分
  * 异常量(EF)：0分
```

### 代码实现结构

```python
# backend/domain/services/cr_strategy_service.py
class CRStrategyService:
    def check_c_point_strategy_1(self, stock_code, date):
        # 1. 获取基础数据
        daily_chance = self.daily_chance_repo.find_by_stock_and_date(stock_code, date)
        
        # 2. 计算基础分
        win_ratio_score = daily_chance.total_win_ratio_score  # 赔率分
        win_rate_score = self._calculate_win_rate_score(volume_type)  # 胜率分
        base_score = win_ratio_score + win_rate_score
        
        # 3. 应用插件（调整分数）
        final_score, triggered_plugins = self.plugin_service.apply_plugins(
            stock_code, date, base_score
        )
        
        # 4. 判断是否触发
        is_triggered = final_score >= 70
        
        return is_triggered, final_score, strategy_name, plugins, base_score, is_rejected
```

### C点插件系统

```python
# backend/domain/services/c_point_plugin_service.py
class CPointPluginService:
    def apply_plugins(self, stock_code, date, base_score):
        adjusted_score = base_score
        triggered_plugins = []
        
        # 插件1: 阴线检查（一票否决）
        if 阴线:
            return 0, [插件1]
        
        # 插件2: 赔率高胜率低（扣分-30）
        if 触发:
            adjusted_score -= 30
            triggered_plugins.append(插件2)
        
        # 插件3: 风险K线（一票否决）
        if 触发:
            return 0, [插件3]
        
        # 插件4: 不追涨（扣分-50）
        if 触发:
            adjusted_score -= 50
            triggered_plugins.append(插件4)
        
        # 插件5: 急跌抢反弹（直接发C）
        if 触发:
            return 999, [插件5]
        
        return adjusted_score, triggered_plugins
```

### C点插件详情

| 插件 | 类型 | 效果 | 说明 |
|-----|------|------|------|
| **插件1：阴线** | 一票否决 | 返回0分 | 任意阴线当日不发C |
| **插件2：赔率高胜率低** | 扣分 | -30分 | 赔率高但成交量不足 |
| **插件3：风险K线** | 一票否决 | 返回0分 | 冲高回落带上影线 |
| **插件4：不追涨** | 扣分 | -50分 | 连续涨停/涨幅过大 |
| **插件5：急跌抢反弹** | 直接发C | 999分 | 急跌后出现反弹信号 |

---

## R点逻辑

### 核心思想

R点不基于评分，而是基于**风险插件检测**。任一插件触发即发出R点信号。

### 代码实现结构

```python
# backend/domain/services/r_point_plugin_service.py
class RPointPluginService:
    def check_r_point(self, stock_code, date, c_point_date):
        triggered_plugins = []
        
        # 插件1: 乖离率偏离
        plugin1 = self._check_deviation(stock_code, date)
        if plugin1.triggered:
            return True, [plugin1]
        
        # 插件2: 临近压力位滞涨
        plugin2 = self._check_pressure_stagnation(stock_code, date)
        if plugin2.triggered:
            return True, [plugin2]
        
        # 插件3: 基本面突发利空
        plugin3 = self._check_fundamental_negative(stock_code, date)
        if plugin3.triggered:
            return True, [plugin3]
        
        # 插件4: 上冲乏力
        if c_point_date:
            plugin4 = self._check_weak_breakout(stock_code, date, c_point_date)
            if plugin4.triggered:
                return True, [plugin4]
        
        return False, []
```

### R点插件详情

#### 插件1：乖离率偏离（6个子条件）

| 子条件 | 主要条件 | 叠加条件 |
|-------|---------|---------|
| 1.1 | 连续2个涨停 | 放量(XYH) + 空头K线 |
| 1.2 | 前3日涨幅>(15%/20%) | 放量(XYH) + 空头K线 |
| 1.3 | 前5日涨幅>(20%/25%) | 放量(XYH) + 空头K线 |
| 1.4 | 连续5连阳+涨幅>(20%/25%) | 放量(XYH) + 空头K线 |
| 1.5 | 前15日涨幅>50% | 放量(XYZH) + 空头信号 |
| 1.6 | 前20日涨幅>50% | 放量(XYZH) + 空头信号 |

#### 插件2：临近压力位滞涨

```
前提条件（共同条件）：
- 前一交易日日线赔率得分不等于0
- 当前股价距离压力线：0% < (压力线-股价)/股价 < 10%

条件1: 前提条件 + 放量(XYZH) + 特定空头K线 + C点日开盘价<当日收盘价
条件2(熊市): 前提条件 + 前3日无AXYZ放量 + 空头组合 + C点日开盘价<当日收盘价
```

#### 插件3：基本面突发利空

```
一字跌停/T字跌停
TODO: 需要AI检测基本面利空
```

#### 插件4：上冲乏力

```
条件（需同时满足）：
- 从C点涨幅>15%
- 前一交易日日线赔率得分：短线<15分、波段<12分、中长线<10分（且不等于0）
- 当前股价距离压力线：0% < (压力线-股价)/股价 < 8%
- 昨日涨幅>6%/8%（主板/非主板）
- 今日放量(AXYZH)
- 空头K线
```

#### 插件5：X日爆量（TODO）

```
待实现
```

#### 插件6：高位发R

```
条件（需同时满足）：
1. 均线多头排列判断：
   - 当前是多头排列（5日>10日>20日>30日>60日），或
   - 前3个交易日出现过多头排列但当前不是多头排列
2. 从当前往前20个交易日的最低价涨幅 > 18%
3. 当前股价 > 10日均线价格（确认目前是短期高点）
4. 目前股价跌破前一日支撑位
5. 当天MACD出现死叉，或已经出现死叉（之前5个交易日内出现死叉也算）
```

#### 插件7：箱体回踩被跌破

```
条件（需同时满足）：
1. 从当前往前20个交易日找到最高价日X日，X日最高价距离当前价格 > 18%
2. X日往前推22个交易日，X日应该是这23天的前30%高位区域（相对高点）
3. X-22日到X日这23天，最低价到最高价的涨幅 >= 18%
4. 当前股价跌破前一日支撑位
5. MACD出现死叉（前5个交易日内）或已形成死叉且当前未出现金叉
```

---

## 代码结构

### 目录结构

```
alpha_strategy_v2/
├── backend/
│   ├── application/
│   │   └── services/
│   │       ├── cr_point_service.py          # CR点应用服务（核心编排）
│   │       └── kline_service.py             # K线数据服务
│   ├── domain/
│   │   ├── models/
│   │   │   ├── cr_point.py                  # CR点领域模型
│   │   │   ├── kline.py                     # K线领域模型
│   │   │   └── daily_chance.py              # 每日机会模型
│   │   ├── repositories/
│   │   │   ├── cr_point_repository.py       # CR点仓储接口
│   │   │   └── kline_repository.py          # K线仓储接口
│   │   └── services/
│   │       ├── cr_strategy_service.py       # C点策略服务
│   │       ├── c_point_plugin_service.py    # C点插件服务
│   │       ├── r_point_plugin_service.py    # R点插件服务
│   │       └── period_service.py            # 周期服务
│   ├── infrastructure/
│   │   ├── config/
│   │   │   └── app_config.py                # 应用配置
│   │   ├── logging/
│   │   │   └── logger.py                    # 日志工具
│   │   └── persistence/
│   │       ├── cr_point_repository_impl.py  # CR点仓储实现
│   │       ├── kline_repository_impl.py     # K线仓储实现
│   │       ├── daily_repository_impl.py     # 日线仓储实现
│   │       ├── daily_chance_repository_impl.py # 机会仓储实现
│   │       └── database.py                  # 数据库连接
│   ├── interfaces/
│   │   ├── controllers/
│   │   │   └── cr_point_controller.py       # CR点控制器
│   │   └── dto/
│   │       └── response.py                  # 响应DTO
│   └── app.py                               # Flask应用入口
└── frontend/
    ├── index.html                            # 主页面
    └── js/
        └── app.js                            # 前端主逻辑
```

### 核心类关系

```
┌─────────────────────────────────────────────────┐
│          CRPointController                      │
│  + analyze_cr_points()                          │
└────────────────┬────────────────────────────────┘
                 │ 调用
┌────────────────▼────────────────────────────────┐
│           CRPointService                        │
│  + analyze_cr_points()                          │
│  - strategy_service: CRStrategyService          │
│  - r_point_service: RPointPluginService         │
└────────┬───────────────────┬────────────────────┘
         │                   │
         ▼                   ▼
┌────────────────┐  ┌──────────────────────┐
│CRStrategyService│  │RPointPluginService   │
│+ check_c_point │  │+ check_r_point       │
│  _strategy_1() │  │- _check_deviation()  │
│- plugin_service│  │- _check_pressure_... │
└────────┬───────┘  └──────────────────────┘
         │
         ▼
┌────────────────────────────┐
│   CPointPluginService      │
│ + apply_plugins()          │
│ - _check_bearish_line()    │
│ - _check_high_ratio_...()  │
│ - _check_risk_kline()      │
│ - _check_no_chase_high()   │
│ - _check_sharp_drop_...()  │
└────────────────────────────┘
```

### 数据模型

#### CRPoint（CR点模型）
```python
class CRPoint:
    stock_code: str          # 股票代码
    stock_name: str          # 股票名称
    point_type: str          # 'C' 或 'R'
    trigger_date: datetime   # 触发日期
    trigger_price: float     # 触发价格
    open_price: float        # 开盘价
    high_price: float        # 最高价
    low_price: float         # 最低价
    close_price: float       # 收盘价
    volume: int              # 成交量
    a_value: float           # ABC中的A
    b_value: float           # ABC中的B
    c_value: float           # ABC中的C
    score: float             # 得分（C点有效，R点为0）
    strategy_name: str       # 策略名称
    plugins: List[Dict]      # 插件信息
```

---

## 性能优化

### 核心优化：批量缓存机制

#### 优化前问题
```
每个K线点都查询数据库：
- 250个K线 × 12次查询/K线 = 3000+次查询
- 响应时间：数十秒
```

#### 优化后方案
```
批量预加载数据到内存：
- 初始化时：3次批量查询
- 分析时：直接从缓存读取
- 响应时间：5-10秒（2年数据）
```

### 缓存实现

```python
# 1. 初始化缓存
def init_cache(self, stock_code, start_date, end_date):
    # 批量查询 daily 数据
    daily_list = self.daily_repo.find_by_date_range(...)
    self._daily_cache = {date: data for date, data in daily_list}
    
    # 批量查询 daily_chance 数据
    daily_chance_list = self.daily_chance_repo.find_by_stock_code(...)
    self._daily_chance_cache = {date: data for date, data in daily_chance_list}

# 2. 使用缓存
def _check_plugin(self, stock_code, date):
    # 优先使用缓存
    data = self._daily_cache.get(date)
    if not data:
        # 缓存未命中，查询数据库
        data = self.daily_repo.find_by_date(stock_code, date)
    return data

# 3. 清空缓存
def clear_cache(self):
    self._daily_cache = {}
    self._daily_chance_cache = {}
```

### 性能对比

| 指标 | 优化前 | 优化后 | 提升 |
|-----|--------|--------|------|
| 数据库查询次数 | 6000+ | 6次 | 99.9% ↓ |
| 响应时间（2年数据） | 30秒+ | 5-10秒 | 70% ↓ |
| 内存使用 | 低 | 中（用完释放） | - |

---

## 前端展示

### ECharts图表配置

```javascript
// C点标记（红色圆圈，K线下方）
{
    name: 'C点',
    type: 'scatter',
    data: [
        {
            value: [index, lowPrice],  // [x轴索引, y轴价格]
            cPointInfo: {
                score: 75.5,
                strategy: '策略一-赔率+胜率+插件',
                plugins: [...]
            },
            itemStyle: {
                color: '#ff0000',      // 红色
                borderColor: '#fff',
                borderWidth: 2
            },
            symbolSize: 25,
            label: {
                show: true,
                formatter: 'C',
                color: '#ffffff'
            }
        }
    ]
}

// R点标记（绿色圆圈，K线上方）
{
    name: 'R点',
    type: 'scatter',
    data: [
        {
            value: [index, highPrice],
            rPointInfo: {
                strategy: '乖离率偏离',
                plugins: [...]
            },
            itemStyle: {
                color: '#00cc00',      // 绿色
                borderColor: '#fff',
                borderWidth: 2
            },
            symbolSize: 25,
            label: {
                show: true,
                formatter: 'R',
                color: '#ffffff'
            }
        }
    ]
}
```

### Tooltip提示框

```javascript
// 鼠标悬停显示详情
tooltip: {
    formatter: function(params) {
        if (params.seriesName === 'C点') {
            return `
                <b>C点触发（买入信号）</b><br/>
                得分: ${score} / 70<br/>
                策略: ${strategy}<br/>
                <br/>
                触发的插件:<br/>
                ${plugins.map(p => `- ${p.name}: ${p.reason}`).join('<br/>')}
            `;
        }
        if (params.seriesName === 'R点') {
            return `
                <b>R点触发（卖出信号）</b><br/>
                策略: ${strategy}<br/>
                <br/>
                风险插件:<br/>
                ${plugins.map(p => `- ${p.name}: ${p.reason}`).join('<br/>')}
                <br/>
                💡 建议考虑卖出或止盈
            `;
        }
    }
}
```

### 统计信息显示

```javascript
// 更新统计信息
function updateCRPointsStats() {
    const cCount = crPointsData.c_points.length;
    const rCount = crPointsData.r_points.length;
    statsEl.textContent = `C点(买入): ${cCount} | R点(卖出): ${rCount}`;
}
```

---

## 完整调用链示例

### 用户操作：点击"分析CR点"

```
1. [前端] app.js
   ↓ analyzeCRPoints()
   
2. [HTTP] POST /api/cr_points/analyze
   {
     "stockCode": "SH600000",
     "stockName": "浦发银行",
     "tableName": "basic_data_sh600000",
     "period": "day"
   }
   
3. [接口层] cr_point_controller.py
   ↓ CRPointController.analyze_cr_points()
   ↓ 获取K线数据（kline_service）
   
4. [应用层] cr_point_service.py
   ↓ CRPointService.analyze_cr_points()
   ↓ 初始化缓存
   ↓ 遍历K线数据
   
5. [领域层] cr_strategy_service.py
   ↓ 对每个K线检查C点
   ↓ CRStrategyService.check_c_point_strategy_1()
   ↓ 计算基础分（赔率分+胜率分）
   
6. [领域层] c_point_plugin_service.py
   ↓ CPointPluginService.apply_plugins()
   ↓ 插件1：阴线检查
   ↓ 插件2：赔率高胜率低
   ↓ 插件3：风险K线
   ↓ 插件4：不追涨
   ↓ 插件5：急跌抢反弹
   ↓ 返回最终分数和插件列表
   
7. [领域层] r_point_plugin_service.py
   ↓ 对每个K线检查R点
   ↓ RPointPluginService.check_r_point()
   ↓ 插件1：乖离率偏离
   ↓ 插件2：临近压力位滞涨
   ↓ 插件3：基本面突发利空
   ↓ 插件4：上冲乏力
   ↓ 返回是否触发和插件列表
   
8. [应用层] 汇总结果
   ↓ 清空缓存
   ↓ 返回JSON
   
9. [接口层] 返回HTTP响应
   {
     "code": 200,
     "message": "CR点实时分析完成",
     "data": {
       "c_points_count": 5,
       "r_points_count": 3,
       "c_points": [...],
       "r_points": [...]
     }
   }
   
10. [前端] 显示结果
    ↓ 在ECharts图表上标记C点和R点
    ↓ 更新统计信息
    ↓ 弹出完成提示
```

---

## 关键配置

### 时间范围配置
```python
# backend/infrastructure/config/app_config.py
TIME_RANGE_CONFIG = {
    'day': 730,     # 日K线：最近2年
    'week': 1095,   # 周K线：最近3年
    'month': 1825   # 月K线：最近5年
}
```

### 评分阈值
```python
# C点触发阈值
C_POINT_THRESHOLD = 70  # 分数 >= 70 触发C点

# 胜率分
WIN_RATE_SCORES = {
    'ABCD': 40,  # 温和放量
    'H': 28,     # 特殊型
    'EF': 0      # 异常量
}

# 插件扣分
PLUGIN_DEDUCTIONS = {
    '赔率高胜率低': -30,
    '不追涨': -50
}
```

### 主板/非主板阈值
```python
# 判断是否主板
is_main_board = stock_code.startswith((
    'SH600', 'SH601', 'SH603', 'SH605', 
    'SZ000', 'SZ001'
))

# 不同阈值
thresholds = {
    '涨停': (9.9, 19.8),      # (主板, 非主板)
    '振幅': (6, 8),
    '前3日涨幅': (15, 20),
    '前5日涨幅': (20, 25)
}
```

---

## 日志追踪

### 关键日志点

```python
# 1. 初始化
logger.info(f"初始化C点和R点缓存: {stock_code} {start_date} 至 {end_date}")

# 2. C点触发
logger.info(f"策略一: 触发C点！股票={stock_code}, 日期={date}, "
           f"赔率分={win_ratio_score:.2f}, 胜率分={win_rate_score:.2f}, "
           f"基础分={base_score:.2f}, 最终分={final_score:.2f}")

# 3. C点插件
logger.info(f"[插件-急跌抢反弹] {stock_code} {date}: {reason}, 直接发C")

# 4. R点触发
logger.info(f"[R点插件-乖离率偏离] {stock_code} {date}: {reason}")

# 5. 完成统计
logger.info(f"CR点实时分析完成: {stock_code} - "
           f"C点:{len(c_points)}个, R点:{len(r_points)}个")
```

---

## 总结

### 系统特点
1. ✅ **分层清晰**：接口层、应用层、领域层、基础设施层
2. ✅ **插件化**：C点和R点都使用插件系统，易于扩展
3. ✅ **性能优化**：批量缓存机制，响应快速
4. ✅ **可维护性**：代码结构清晰，职责明确
5. ✅ **可扩展性**：新增插件无需修改核心代码

### 技术亮点
1. **DDD架构**：领域驱动设计，业务逻辑内聚
2. **缓存优化**：查询次数从6000+降到6次
3. **插件系统**：灵活的规则引擎
4. **实时计算**：不存储，每次实时分析
5. **前后端分离**：RESTful API

### 扩展方向
1. 添加更多C点/R点插件
2. 接入AI进行基本面分析
3. 回测系统验证策略效果
4. 参数可配置化
5. 实时推送服务

---

**文档版本**: v1.0  
**更新时间**: 2024-11-14  
**维护者**: CR策略团队

