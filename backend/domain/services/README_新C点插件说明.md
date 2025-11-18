# 新增C点插件说明（插件6-8）

## 概述

新增了3个C点插件，用于在特定条件下直接发出C点信号（买入信号）。这些插件通过返回 `force_c_point=True` 标志来强制发C，而不调整原始分数。

---

## 插件6: R后回支撑位发C

### 触发条件

1. **时间窗口**：在个股出R后的3日内
2. **支撑位判断**：重新回到支撑位上方或原本未跌破支撑
   - 检查当日收盘价 >= 支撑价 或 最低价 >= 支撑价
3. **多头K线组合**：出现多头K线组合（1234任意一种）
4. **成交量放大**：当日成交量放大（ABCD任意一种）

### 实现逻辑

```python
def _check_r_back_to_support(self, stock_code, date, historical_r_points):
    # 1. 查找最近3日内的R点
    # 2. 检查是否在支撑位上方（从daily_chance获取support_price）
    # 3. 检查是否有多头K线组合（1234）
    # 4. 检查成交量是否放大（ABCD）
    # 5. 全部满足则返回插件结果（triggered=True），通过force_c_point标志强制发C
```

### 支撑价来源

支撑价格从 `daily_chance` 表的 `support_price` 字段获取。

---

## 插件7: 阳包阴发C

### 触发条件

1. **时间范围**：从当日往前数15根K线
2. **R点查找**：若出现R点
3. **R日放量**：R日成交量类型为XYZH任意一种
4. **阳包阴形态**：当日收盘价 > R日开盘价
5. **叠加条件**（满足其一即可）：
   - 当日成交量 > R日成交量的0.85倍
   - 前一日为多头组合（任意）

### 实现逻辑

```python
def _check_yang_bao_yin(self, stock_code, date, historical_r_points):
    # 1. 获取前15个交易日
    # 2. 在前15日中查找R点，且R日放量（XYZH）
    # 3. 检查阳包阴：当日收盘价 > R日开盘价
    # 4. 检查叠加条件1：当日成交量 > R日成交量*0.85
    # 5. 检查叠加条件2：前一日为多头组合
    # 6. 满足条件则返回插件结果（triggered=True），通过force_c_point标志强制发C
```

---

## 插件8: 横盘修整后突破发C

### 触发条件

1. **时间范围**：往前数30个交易日
2. **R点查找**：发现R点且R后无C
3. **横盘特征**：R后的成交量均小于R日
4. **放量突破**：今日成交量出现放量（AXYHZ任意一种）
5. **价格突破**：股价突破R日收盘价

### 实现逻辑

```python
def _check_consolidation_breakout(self, stock_code, date, historical_r_points, historical_c_points):
    # 1. 获取前30个交易日
    # 2. 查找R点，且R后无C点
    # 3. 检查R后所有交易日的成交量均小于R日成交量
    # 4. 检查今日是否放量（AXYHZ）
    # 5. 检查股价是否突破R日收盘价
    # 6. 满足条件则返回插件结果（triggered=True），通过force_c_point标志强制发C
```

---

## 技术实现

### 修改的文件

1. **backend/domain/services/c_point_plugin_service.py**
   - 修改 `apply_plugins` 方法：
     - 接收历史R点和C点参数
     - 返回值增加 `force_c_point` 标志（第3个返回值）
   - 新增 `_check_r_back_to_support` 方法
   - 新增 `_check_yang_bao_yin` 方法
   - 新增 `_check_consolidation_breakout` 方法
   - 修改所有"强制发C"插件，返回 `score_adjustment=0`（不调整分数）

2. **backend/domain/services/cr_strategy_service.py**
   - 修改 `check_c_point_strategy_1` 方法：
     - 接收并传递历史CR点参数
     - 接收插件返回的 `force_c_point` 标志
     - 当 `force_c_point=True` 时，直接触发C点（忽略分数）

3. **backend/application/services/cr_point_service.py**
   - 修改 `analyze_cr_points` 方法中的调用，传入历史CR点列表

### 数据依赖

- **daily_chance 表**：
  - `support_price`: 支撑价格（插件6）
  - `volume_type`: 成交量类型（所有插件）
  - `bullish_pattern`: 多头K线组合（插件6、插件7）

- **历史CR点**：
  - 实时计算的R点列表（所有插件）
  - 实时计算的C点列表（插件8）

### 执行顺序

新插件在现有插件之后执行：
1. 插件1: 阴线检查（一票否决）
2. 插件2: 赔率高胜率低（扣分）
3. 插件3: 风险K线（一票否决）
4. 插件4: 不追涨（扣分）
5. 插件5: 急跌抢反弹（直接发C）
6. **插件6: R后回支撑位（直接发C）** ← 新增
7. **插件7: 阳包阴（直接发C）** ← 新增
8. **插件8: 横盘修整后突破（直接发C）** ← 新增

---

## 测试方法

使用测试脚本：

```bash
cd backend
python scripts/test_new_c_plugins.py <股票代码>
```

例如：
```bash
python scripts/test_new_c_plugins.py SH600004
```

---

## 注意事项

1. **CR点实时计算**：CR点不存储在数据库中，而是实时计算的
2. **历史CR点传递**：通过修改调用链，将历史CR点列表传递给插件
3. **缓存机制**：使用缓存优化性能，避免重复查询数据库
4. **强制发C机制**：新插件通过 `force_c_point=True` 标志强制发C，不调整原始分数
5. **支撑价格**：需要确保 `daily_chance` 表中有 `support_price` 数据

## 核心逻辑变更

### 旧逻辑（已废弃）
```python
# 插件返回999分来强制发C
return 999, triggered_plugins
```

### 新逻辑
```python
# 插件返回force_c_point标志来强制发C，保持原分数不变
return adjusted_score, triggered_plugins, True  # force_c_point=True
```

**优点**：
- 逻辑更清晰：通过标志位而不是魔法数字999
- 分数更准确：保留实际的分数，便于调试和分析
- 易于维护：强制发C的逻辑集中在标志位判断

---

## 开发日期

2025-11-18

