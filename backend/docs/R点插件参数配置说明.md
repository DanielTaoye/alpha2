# R点插件参数配置说明

## 概述

现在支持通过调参平台动态配置R点插件的关键参数，无需修改代码即可调整插件的触发条件。

## 可配置参数

### 1. 临近压力位滞涨 - 距离阈值 (pressure_distance_threshold)

**位置**: 插件2 - 临近压力位滞涨

**作用**: 控制股价距离压力线的百分比范围

**逻辑**: 
- 当 `0% < (压力线 - 股价) / 股价 < 距离阈值%` 时，满足临近压力位的条件
- 配合其他条件（赔率得分、放量、K线形态等）共同触发R点

**默认值**: 10.0%

**推荐范围**:
- 保守型: 5-8% (要求股价非常接近压力位)
- 默认: 10% (平衡准确性和触发频率)
- 宽松型: 12-15% (更早发出预警信号)

**配置示例**:
```json
{
  "r_point_plugins": {
    "pressure_stagnation": {
      "distance_threshold_pct": 10.0
    }
  }
}
```

**影响**:
- 阈值越小：越严格要求股价接近压力位，R点触发更精准但可能错过一些机会
- 阈值越大：更宽松的触发范围，可能产生更多R点信号但误报率可能增加

---

### 2. 高位发R - 涨幅阈值 (high_position_gain_threshold)

**位置**: 插件6 - 高位发R

**作用**: 控制从前20个交易日最低价到当前价格的涨幅要求

**逻辑**:
- 从当前往前找20个交易日的最低价（该日为X日）
- 计算 `(当前价格 - X日最低价) / X日最低价 * 100%`
- 当涨幅 > 涨幅阈值% 时，满足高位条件

**默认值**: 8.0%

**推荐范围**:
- 保守型: 12-15% (要求有较大涨幅才触发)
- 默认: 8% (平衡准确性和及时性)
- 灵敏型: 5-6% (更早发出卖出信号)

**配置示例**:
```json
{
  "r_point_plugins": {
    "high_position_r": {
      "gain_threshold_pct": 8.0
    }
  }
}
```

**影响**:
- 阈值越高：要求股价有更大涨幅才触发，避免过早卖出但可能错过最佳卖点
- 阈值越低：更早发出卖出信号，及时止盈但可能卖早

---

## 如何配置

### 方法1: 通过Web界面 (推荐)

1. 访问调参平台: `http://your-host:port/config.html`
2. 找到"R点插件配置"section
3. 调整滑块或直接输入数值
4. 点击"保存配置"按钮
5. 配置立即生效，无需重启服务

### 方法2: 通过API

```bash
curl -X POST http://your-host:port/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "pressure_distance_threshold": 10.0,
    "high_position_gain_threshold": 8.0
  }'
```

### 方法3: 直接编辑配置文件

编辑 `backend/config/strategy_config.json`:

```json
{
  "strategy1": {
    "c_point_threshold": 70.0
  },
  "strategy2": {
    "c_point_threshold": 85.0
  },
  "r_point_plugins": {
    "pressure_stagnation": {
      "distance_threshold_pct": 10.0,
      "description": "临近压力位滞涨插件-股价距离压力线的百分比阈值"
    },
    "high_position_r": {
      "gain_threshold_pct": 8.0,
      "description": "高位发R插件-前20个交易日最低价到当前价格的涨幅阈值"
    }
  },
  "market_type": "bull"
}
```

然后通过API重新加载配置:
```bash
curl -X POST http://your-host:port/api/config/reload
```

---

## 调参建议

### 根据市场环境调整

**牛市环境**:
- 临近压力位滞涨: 可适当降低阈值(5-8%)，严格要求股价接近压力位
- 高位发R: 可适当提高阈值(10-12%)，避免过早卖出错过主升浪

**熊市环境**:
- 临近压力位滞涨: 可适当提高阈值(12-15%)，更早发出预警
- 高位发R: 可适当降低阈值(5-6%)，及时止盈避免回撤

### 根据股票特性调整

**活跃股/题材股**:
- 波动大，建议适当放宽阈值避免频繁触发

**稳健股/蓝筹股**:
- 波动小，建议收紧阈值提高精度

### 回测验证

建议通过批量回测功能验证参数调整的效果：
1. 调整参数后进行批量回测
2. 对比不同参数下的胜率、盈亏比等指标
3. 根据回测结果优化参数设置

---

## 技术实现

### 代码位置

- **配置文件**: `backend/config/strategy_config.json`
- **配置服务**: `backend/domain/services/config_service.py`
- **R点插件服务**: `backend/domain/services/r_point_plugin_service.py`
- **配置控制器**: `backend/interfaces/controllers/config_controller.py`
- **前端界面**: `frontend/config.html`

### 参数读取

配置参数通过ConfigService读取:

```python
# 临近压力位滞涨 - 距离阈值
distance_threshold = self.config_service.get_pressure_stagnation_distance_threshold()

# 高位发R - 涨幅阈值
gain_threshold = self.config_service.get_high_position_gain_threshold()
```

### 热更新

配置更新后立即生效，无需重启服务。ConfigService使用缓存机制，每次更新配置后自动刷新缓存。

---

## 常见问题

**Q: 修改参数后需要重启服务吗？**
A: 不需要。配置更新后立即生效。

**Q: 如何恢复默认参数？**
A: 在Web界面点击"默认"预设按钮，或手动设置为10%和8%。

**Q: 参数调整会影响历史数据吗？**
A: 不会。参数只影响后续的分析和回测，不改变历史已保存的数据。

**Q: 可以为不同股票设置不同参数吗？**
A: 当前版本是全局参数，应用于所有股票。未来版本可能支持按股票分组设置。

---

## 更新日志

### 2025-12-04
- ✅ 新增临近压力位滞涨距离阈值可配置
- ✅ 新增高位发R涨幅阈值可配置
- ✅ 前端界面添加R点插件配置section
- ✅ API支持新参数的读取和更新

