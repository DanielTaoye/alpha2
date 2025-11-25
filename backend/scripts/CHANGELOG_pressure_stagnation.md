# 临近压力位滞涨插件改造说明

## 📋 改造时间
2025-11-25

## 🎯 改造目标
对R点插件中的"临近压力位滞涨"进行改造，使其：
1. 根据股性判断是否临近压力位（不同股性有不同的赔率阈值）
2. 重新定义K线形态判断逻辑
3. 在tooltip中显示所有命中的K线形态

## 📊 主要改动

### 1. 股性化的压力位判断

**原逻辑：**
```python
# 所有股票统一使用 6 分作为阈值
is_near_pressure = day_win_ratio_score < 6
```

**新逻辑：**
```python
# 根据股性获取不同的阈值
def _get_pressure_threshold(self, stock_nature: str) -> float:
    thresholds = {
        "短线": 6.0,      # 短线股赔率<6分视为临近压力位
        "波段": 4.8,      # 波段股赔率<4.8分视为临近压力位  
        "中长线": 3.6     # 中长线股赔率<3.6分视为临近压力位
    }
    return thresholds.get(stock_nature, 4.8)  # 默认波段

# 使用股性化的阈值
stock_nature = current_chance.stock_nature or "波段"
pressure_threshold = self._get_pressure_threshold(stock_nature)
is_near_pressure = day_win_ratio_score < pressure_threshold
```

### 2. 重新定义K线形态

#### 2.1 冲高回落阳线
```python
def _check_bullish_high_fallback(self, A, B, C, O, close, L) -> bool:
    """
    条件：
    - A >= 2C
    - A >= 2B
    - 1% < B/最低价 < 3.3%
    - 开盘价 < 收盘价
    """
```

#### 2.2 冲高回落阴线
```python
def _check_bearish_high_fallback(self, A, B, C, O, close, L) -> bool:
    """
    条件：
    - A >= 2C
    - A >= 2B
    - 1% < B/最低价 < 3.3%
    - 开盘价 > 收盘价
    """
```

#### 2.3 冲高回落阳十字星
```python
def _check_bullish_doji_high_fallback(self, A, B, C, O, close, L) -> bool:
    """
    条件：
    - 开盘价 < 收盘价
    - B/最低价 < 2%
    - C > 0
    - A > 2C
    """
```

#### 2.4 冲高回落阴十字星
```python
def _check_bearish_doji_high_fallback(self, A, B, C, O, close, L) -> bool:
    """
    条件：
    - 开盘价 > 收盘价
    - B/最低价 < 2%
    - C > 0
    - A > 2C
    """
```

#### 2.5 高开低走
```python
def _check_high_open_low_close_new(self, A, B, C, O, close) -> bool:
    """
    条件：
    - 开盘价 > 收盘价
    - A = 0（无上影线）
    - C < 2B
    """
```

#### 2.6 阴线跌幅>3%
```python
def _check_bearish_line_3pct_new(self, O, close, prev_close) -> bool:
    """
    条件：
    - 跌幅相对昨收 > 3%
    """
```

### 3. 返回所有命中的形态

**原逻辑：**
```python
# 只要任一形态命中就返回，不显示具体是哪个形态
if is_bearish_divergence or is_bearish_doji or ...:
    return RPointPluginResult(
        "临近压力位滞涨",
        True,
        f"条件1: 距压力位近(赔率{day_win_ratio_score:.1f}<6)+放量+空头K线"
    )
```

**新逻辑：**
```python
# 返回所有命中的形态列表
matched_patterns = self._check_bearish_kline_patterns(current_data)

if matched_patterns:
    pattern_desc = "、".join(matched_patterns)  # 如 "冲高回落阳线、高开低走"
    return RPointPluginResult(
        "临近压力位滞涨",
        True,
        f"条件1: 距压力位近(股性:{stock_nature},赔率{day_win_ratio_score:.1f}<{pressure_threshold})+放量+空头K线({pattern_desc})"
    )
```

### 4. 同步更新的其他插件

#### 4.1 乖离率偏离插件
- 使用新的 `_check_bearish_kline_patterns()` 方法
- 适配返回的形态列表

#### 4.2 上冲乏力插件
- 使用新的 `_check_bearish_kline_patterns()` 方法
- 在tooltip中显示具体命中的K线形态

## 🔍 示例输出

### 条件1触发时的tooltip：
```
条件1: 距压力位近(股性:波段,赔率3.5<4.8)+放量+空头K线(冲高回落阳线、阴线跌幅>3%)
```

### 条件2触发时的tooltip（仅熊市）：
```
条件2(熊市): 距压力位近(股性:短线,赔率5.2<6)+前3日无放量+空头组合
```

## 📌 技术要点

### ABC的定义
- **A (上影线)**: `最高价 - max(开盘价, 收盘价)`
- **B (实体)**: `abs(收盘价 - 开盘价)`
- **C (下影线)**: `min(开盘价, 收盘价) - 最低价`

### 注意事项
1. 所有计算都基于日K线数据（`peroid_type='1day'`）
2. `prev_close` 为0时，跳过跌幅计算
3. 默认股性为"波段"（当 `stock_nature` 为空时）
4. 形态命中采用"或"逻辑，只要命中任一形态即触发

## ✅ 测试建议

1. **股性测试**：测试短线、波段、中长线三种股性的压力位判断
2. **K线形态测试**：针对每种K线形态创建测试用例
3. **边界条件测试**：
   - `prev_close = 0` 的情况
   - `L = 0` 的情况（虽然实际不太可能）
   - `A = 0` 的精确匹配（高开低走）
4. **组合测试**：同时命中多个K线形态的情况

## 📝 影响范围

### 修改的文件
- `backend/domain/services/r_point_plugin_service.py`

### 新增的方法
- `_get_pressure_threshold()` - 根据股性获取压力位阈值
- `_check_bearish_kline_patterns()` - 检查所有空头K线形态
- `_check_bullish_high_fallback()` - 冲高回落阳线
- `_check_bearish_high_fallback()` - 冲高回落阴线
- `_check_bullish_doji_high_fallback()` - 冲高回落阳十字星
- `_check_bearish_doji_high_fallback()` - 冲高回落阴十字星
- `_check_high_open_low_close_new()` - 高开低走
- `_check_bearish_line_3pct_new()` - 阴线跌幅>3%

### 删除的方法
- `_check_bearish_divergence_kline()` - 旧的空头分歧K线检查
- `_check_bearish_doji()` - 旧的空头十字星检查
- `_check_high_open_low_close()` - 旧的高开低走检查
- `_check_bearish_line_above_threshold()` - 旧的阴线跌幅检查

## 🚀 部署步骤

1. 备份当前版本的 `r_point_plugin_service.py`
2. 应用新代码
3. 重启后端服务
4. 验证R点检测是否正常工作
5. 观察tooltip中是否正确显示股性和K线形态

## 🔗 相关文档
- R点插件设计文档
- K线形态定义文档
- 股性分类说明

