# MACD指标实现说明

## 📊 功能概述

MACD（Moving Average Convergence Divergence，平滑异同移动平均线）是一种常用的技术分析指标，用于判断股票的买卖时机和趋势强度。

### MACD组成
- **DIF（差离值）**：快线EMA(12) - 慢线EMA(26)
- **DEA（信号线）**：DIF的9日EMA
- **MACD柱**：2 × (DIF - DEA)

## 🏗️ 架构设计

### 后端计算（推荐方式）
MACD计算逻辑放在**后端基础设施层**（Domain Services），由后端统一计算后返回给前端。

#### 优势
✅ 统一计算逻辑，避免前后端差异  
✅ 可以利用后端缓存机制  
✅ 前端只负责展示，减少计算负担  
✅ 易于维护和扩展

## 📁 文件结构

```
backend/
├── domain/services/
│   └── macd_service.py          # MACD计算服务（核心逻辑）
├── application/services/
│   └── kline_service.py         # K线服务（附带MACD计算）
└── interfaces/controllers/
    ├── kline_controller.py      # K线控制器（返回MACD数据）
    └── cr_point_controller.py   # CR点控制器（CR分析时也返回MACD）

frontend/
└── js/
    └── app.js                   # 前端展示（从API获取MACD数据）
```

## 🔧 核心实现

### 1. MACD计算服务 (`macd_service.py`)

```python
class MACDService:
    """MACD技术指标计算服务"""
    
    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> List[Optional[float]]:
        """计算指数移动平均线(EMA)"""
        # EMA = 前一日EMA × (period-1)/(period+1) + 今日价格 × 2/(period+1)
        pass
    
    @staticmethod
    def calculate_macd(close_prices: List[float], 
                      fast_period: int = 12, 
                      slow_period: int = 26, 
                      signal_period: int = 9) -> Dict:
        """
        计算MACD指标
        返回: {'dif': [...], 'dea': [...], 'macd': [...]}
        """
        pass
```

### 2. K线服务返回格式修改

**修改前：**
```python
def get_kline_data(...) -> List[Dict]:
    return [kline.to_dict() for kline in kline_list]
```

**修改后：**
```python
def get_kline_data(...) -> Dict[str, any]:
    kline_data = [kline.to_dict() for kline in kline_list]
    macd_data = self.macd_service.calculate_macd_for_kline_data(kline_data)
    
    return {
        'kline_data': kline_data,
        'macd': macd_data  # 新增MACD数据
    }
```

### 3. 前端数据处理

```javascript
// 从API响应中提取数据
const klineData = klineResult.data.kline_data || klineResult.data;
const macdData = klineResult.data.macd || null;

// 保存MACD数据供图表使用
if (macdData) {
    window.currentMACDData = macdData;
}
```

### 4. ECharts图表配置

```javascript
grid: [
    { top: '8%', height: '48%' },    // K线区域
    { top: '60%', height: '12%' },   // 成交量区域
    { top: '76%', height: '14%' }    // MACD区域（新增）
],

series: [
    // ... K线和成交量
    
    // MACD DIF线（蓝色）
    {
        name: 'DIF',
        type: 'line',
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: macdData.dif,
        lineStyle: { color: '#3498db', width: 1.5 }
    },
    
    // MACD DEA线（橙色）
    {
        name: 'DEA',
        type: 'line',
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: macdData.dea,
        lineStyle: { color: '#e67e22', width: 1.5 }
    },
    
    // MACD柱状图（红/绿）
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
        }
    }
]
```

## 📊 显示效果

### 图表布局（从上到下）
1. **K线图区域**（48%高度）- 显示蜡烛图、支撑压力线、CR点
2. **成交量区域**（12%高度）- 显示成交量柱状图
3. **MACD区域**（14%高度）- 显示DIF线、DEA线、MACD柱

### Tooltip信息
鼠标悬停时显示：
```
日期：2025-11-14
开盘：100.00
收盘：105.00
最低：99.50
最高：106.00
成交量：1234.56万

MACD指标:
  DIF: 0.1234
  DEA: 0.0987
  MACD: 0.0494
```

## 🧪 测试验证

### 测试脚本
```bash
python backend/scripts/test_macd.py
```

### 测试结果示例
```
=== 测试MACD计算 ===

收盘价数据: 50个
收盘价范围: 10.0 - 18.0

MACD计算结果:
- DIF数据点: 50
- DEA数据点: 50
- MACD数据点: 50

有效数据数量: DIF=25, DEA=17, MACD=17

最后10个MACD值:
Day 41: Close=16.20, DIF=1.0911, DEA=1.1138, MACD=-0.0455
Day 42: Close=16.70, DIF=1.0945, DEA=1.1100, MACD=-0.0309
...

[OK] MACD计算测试完成!
```

## 📈 数据要求

### 最小数据量
- **DIF**：至少需要 **26个** 收盘价（慢线EMA周期）
- **DEA**：至少需要 **34个** 收盘价（26 + 9 - 1）
- **MACD**：与DEA相同，**34个** 收盘价

### 建议数据量
- **日K线**：至少 **60个** 交易日（约3个月）
- **30分钟K线**：至少 **200个** 数据点
- **周K线**：至少 **60周**（约14个月）

## 🎨 颜色配置

| 元素 | 颜色 | 说明 |
|------|------|------|
| DIF线 | `#3498db` (蓝色) | 快线，反应灵敏 |
| DEA线 | `#e67e22` (橙色) | 慢线/信号线 |
| MACD柱(正) | `#e74c3c` (红色) | DIF > DEA，多头信号 |
| MACD柱(负) | `#2ecc71` (绿色) | DIF < DEA，空头信号 |

## 🔍 MACD信号解读

### 金叉（买入信号）
- DIF线从下方上穿DEA线
- MACD柱由负转正
- 建议关注配合成交量放大

### 死叉（卖出信号）
- DIF线从上方下穿DEA线
- MACD柱由正转负
- 建议关注R点（风险信号）

### 背离
- **顶背离**：价格创新高，MACD未创新高（卖出信号）
- **底背离**：价格创新低，MACD未创新低（买入信号）

## 🚀 使用方式

### 前端自动加载
1. 选择股票后，系统自动加载K线数据
2. 后端计算并返回MACD数据
3. 前端自动在图表底部显示MACD指标

### API响应格式
```json
{
    "code": 200,
    "data": {
        "kline_data": [...],
        "macd": {
            "dif": [null, null, ..., 1.0911, 1.0945],
            "dea": [null, null, ..., 1.1138, 1.1100],
            "macd": [null, null, ..., -0.0455, -0.0309]
        }
    }
}
```

## 💡 扩展建议

### 可添加的功能
1. **MACD参数配置**：允许用户自定义12、26、9参数
2. **MACD信号提示**：自动检测金叉/死叉，标记在图表上
3. **MACD与CR点结合**：C点 + MACD金叉 = 强买入信号
4. **MACD背离检测**：自动识别顶背离和底背离
5. **其他技术指标**：KDJ、RSI、BOLL等

## ✅ 完成清单

- [x] 后端MACD计算服务实现
- [x] K线服务集成MACD计算
- [x] 控制器适配新数据格式
- [x] 前端API数据解析
- [x] ECharts图表配置（3区域布局）
- [x] MACD系列显示（DIF、DEA、柱状图）
- [x] Tooltip信息展示
- [x] 测试脚本验证
- [x] 文档编写

## 📝 注意事项

1. **数据对齐**：MACD数据与K线数据索引一一对应
2. **null处理**：前期数据不足时为null，前端需要正确处理
3. **性能优化**：MACD计算已在后端完成，避免重复计算
4. **缓存机制**：K线服务可考虑缓存MACD结果
5. **周期适配**：不同周期（30min/day/week/month）自动计算对应MACD

---

**实现日期**：2025-11-14  
**版本**：v1.0  
**状态**：✅ 已完成并测试通过

