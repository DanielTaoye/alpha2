# CR点分析系统使用说明

## 概述

CR点分析系统是阿尔法策略2.0的核心功能模块，用于识别股票K线图中的买入点(C点)和卖出点(R点)。

## 功能特点

### 1. K线ABC分解

系统将每根日K线分解为三个部分：
- **a (上引线)**: 最高价 - max(开盘价, 收盘价)
- **b (实体)**: max(开盘价, 收盘价) - min(开盘价, 收盘价)
- **c (下引线)**: min(开盘价, 收盘价) - 最低价

### 2. C点识别策略

**策略1：上下影线均衡小实体**

触发条件：
1. `a/c = 0.9~1.1` - 上下影线比例接近1:1
2. `b / 最低价 < 1%` - 实体很小，小于最低价的1%
3. `a ≠ 0 且 c ≠ 0` - 上下影线都存在

这种形态通常表示多空力量均衡，且实体很小，可能是底部十字星形态。

### 3. R点识别策略

**策略1：上下影线均衡小实体(卖出)**

与C点策略类似，但使用最高价作为参考。

## 数据库结构

CR点数据存储在 `cr_points` 表中，包含以下字段：

- `stock_code`: 股票代码
- `stock_name`: 股票名称  
- `point_type`: C或R (C表示买入点，R表示卖出点)
- `trigger_date`: 触发日期
- `trigger_price`: 触发价格
- `a_value`, `b_value`, `c_value`: ABC三个值
- `score`: 策略得分 (0-1之间，越高表示信号越强)
- `strategy_name`: 触发的策略名称

## API接口

### 1. 分析CR点

```
POST /api/cr_points/analyze
```

请求参数：
```json
{
  "stockCode": "sh600000",
  "stockName": "浦发银行",
  "period": "day"
}
```

响应：
```json
{
  "code": 200,
  "message": "CR点分析完成，发现C点3个，R点2个",
  "data": {
    "c_points_count": 3,
    "r_points_count": 2,
    "c_points": [...],
    "r_points": [...]
  }
}
```

### 2. 获取CR点列表

```
POST /api/cr_points
```

请求参数：
```json
{
  "stockCode": "sh600000",
  "pointType": "C"  // 可选，不传则返回所有类型
}
```

响应：
```json
{
  "code": 200,
  "message": "查询到5个CR点",
  "data": [
    {
      "id": 1,
      "stockCode": "sh600000",
      "stockName": "浦发银行",
      "pointType": "C",
      "triggerDate": "2025-10-15",
      "triggerPrice": 8.56,
      "aValue": 0.05,
      "bValue": 0.02,
      "cValue": 0.05,
      "score": 0.95,
      "strategyName": "策略1-上下影线均衡小实体"
    }
  ]
}
```

## 前端使用

1. **选择股票**: 在股票列表中选择要分析的股票
2. **分析CR点**: 点击"🎯 分析CR点"按钮，系统会分析该股票所有日K线数据
3. **显示CR点**: 点击"👁️ 显示CR点"按钮，在K线图上显示识别出的CR点
   - C点：绿色圆点，标记在K线下方
   - R点：红色圆点，标记在K线上方
4. **查看统计**: 在右上角可以看到C点和R点的数量统计

## 技术架构

- **DDD架构**: 采用领域驱动设计
  - Domain Layer: `CRPoint`实体, `CRStrategyService`领域服务
  - Application Layer: `CRPointService`应用服务
  - Infrastructure Layer: `CRPointRepositoryImpl`仓储实现
  - Interface Layer: `CRPointController`控制器

- **数据库**: MySQL 8.0
- **后端**: Python Flask
- **前端**: HTML5 + JavaScript + ECharts

## 扩展开发

### 添加新策略

1. 在 `backend/domain/services/cr_strategy_service.py` 中添加新的策略方法：

```python
@staticmethod
def check_c_point_strategy_2(abc: ABCComponents, ...) -> Tuple[bool, float, str]:
    """检查是否满足C点策略2"""
    strategy_name = "策略2-XXX"
    
    # 实现你的策略逻辑
    if 满足条件:
        return True, score, strategy_name
    
    return False, 0, strategy_name
```

2. 在 `backend/application/services/cr_point_service.py` 中调用新策略：

```python
# 检查C点策略2
is_c_point_2, c_score_2, c_strategy_2 = self.strategy_service.check_c_point_strategy_2(...)
if is_c_point_2:
    # 保存C点
    ...
```

## 测试

运行测试程序：
```bash
python test_cr_strategy.py
```

## 初始化数据库

```bash
cd backend
python scripts/init_cr_table.py
```

## 注意事项

1. 目前只支持日K线的CR点分析
2. 策略得分越高，信号越可靠
3. 建议结合其他技术指标综合判断
4. 投资有风险，系统仅供参考

## 未来规划

- [ ] 支持更多K线周期（周K、月K）
- [ ] 添加更多识别策略
- [ ] 增加回测功能，计算CR点的准确率
- [ ] 支持批量分析多个股票
- [ ] 增加邮件/推送提醒功能

