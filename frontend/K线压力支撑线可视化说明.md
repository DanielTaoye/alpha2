# K线压力支撑线可视化功能说明

## 📋 功能概述

在K线图上实现了**动态可视化显示压力线和支撑线**的功能。当鼠标悬停在某根K线上时，会在对应的价格位置显示水平线，让压力位和支撑位一目了然。

---

## ✨ 功能特性

### 1️⃣ 动态显示
- ✅ 鼠标悬停在K线上时，自动显示当日的压力/支撑线
- ✅ 鼠标移开时，压力/支撑线自动消失
- ✅ 不影响原有的tooltip信息显示

### 2️⃣ 视觉设计
| 线条类型 | 颜色 | 宽度 | 标签背景 |
|---------|------|------|----------|
| **支撑线** | 🟢 绿色 (#26a69a) | 2px | 绿色 |
| **压力线** | 🔴 红色 (#ef5350) | 2px | 红色 |

### 3️⃣ 标签显示
- 显示位置：线条末端
- 显示内容：`支撑: 10.25` 或 `压力: 12.50`
- 样式：白色文字，半透明背景
- 字体大小：11px

---

## 🎯 实现原理

### 1. 数据来源

压力线和支撑线数据来自 `b_daily_chance` 表：
```javascript
// 全局变量存储每日的压力/支撑线数据
let supportPriceMap = {};   // 支撑线价格Map, key: 日期, value: 价格*100
let pressurePriceMap = {};  // 压力线价格Map, key: 日期, value: 价格*100
```

### 2. ECharts markLine

使用 ECharts 的 `markLine` 功能绘制水平线：

```javascript
// 在K线series中添加markLine配置
option.series[0].markLine = {
    silent: true,          // 不响应鼠标事件
    symbol: 'none',        // 不显示端点符号
    label: {               // 标签配置
        show: true,
        position: 'end',
        formatter: '{b}: {c}'
    },
    lineStyle: {
        type: 'solid',
        width: 2
    },
    data: []  // 初始为空，动态更新
};
```

### 3. 事件监听

监听鼠标悬停和移出事件：

```javascript
// 鼠标悬停在K线上
chart.on('mouseover', function(params) {
    if (params.componentType === 'series' && 
        params.seriesName === 'K线' && 
        params.name) {
        
        const dateOnly = params.name.split(' ')[0];
        const supportPrice = supportPriceMap[dateOnly] / 100;
        const pressurePrice = pressurePriceMap[dateOnly] / 100;
        
        // 更新markLine数据
        const markLineData = [
            { name: '支撑', yAxis: supportPrice, ... },
            { name: '压力', yAxis: pressurePrice, ... }
        ];
        
        chart.setOption({ series: [{ markLine: { data: markLineData } }] });
    }
});

// 鼠标移出图表
chart.on('globalout', function() {
    chart.setOption({ series: [{ markLine: { data: [] } }] });
});
```

---

## 📊 使用效果

### 场景1：查看支撑位

```
鼠标悬停在某根K线上
→ K线图上出现绿色水平线
→ 标签显示："支撑: 10.25"
→ Tooltip显示详细信息
```

### 场景2：同时显示压力和支撑

```
鼠标悬停在某根K线上
→ K线图上出现两条水平线：
  - 🟢 绿色支撑线（下方）
  - 🔴 红色压力线（上方）
→ 清晰显示当日的价格区间
```

### 场景3：切换K线

```
鼠标移动到另一根K线
→ 水平线位置自动更新
→ 显示新日期的压力/支撑价格
```

---

## 🎨 视觉对比

### 修改前
- ❌ 只在tooltip中显示价格数字
- ❌ 需要想象价格位置
- ❌ 不够直观

### 修改后
- ✅ 直接在图表上画出水平线
- ✅ 价格位置一目了然
- ✅ 视觉效果更直观

---

## 💡 技术细节

### 1. 价格转换

数据库中存储的是整数（实际价格×100），需要转换：

```javascript
// 数据库存储: 1025 (表示 10.25元)
// 显示时转换: 1025 / 100 = 10.25
const actualSupportPrice = supportPrice / 100;
```

### 2. 事件优化

```javascript
// 移除旧的监听器，避免重复绑定
chart.off('mouseover');
chart.on('mouseover', ...);

chart.off('globalout');
chart.on('globalout', ...);
```

### 3. 条件渲染

只有当价格数据存在时才显示线条：

```javascript
if (supportPrice !== undefined && supportPrice !== null) {
    markLineData.push({ ... });  // 添加支撑线
}

if (pressurePrice !== undefined && pressurePrice !== null) {
    markLineData.push({ ... });  // 添加压力线
}
```

---

## 🔄 兼容性

### 支持的周期
- ✅ 日K线（主要使用场景）
- ⚠️ 其他周期（30分钟、周K、月K）需要数据支持

### 浏览器兼容
- ✅ Chrome / Edge (推荐)
- ✅ Firefox
- ✅ Safari
- ✅ 移动端浏览器

---

## 🐛 已知问题与解决方案

### 问题1：某些K线没有压力/支撑线

**原因：** 数据库中该日期没有计算压力/支撑线数据

**解决：** 运行 `calculate_daily_chance` 脚本更新数据

### 问题2：线条闪烁

**原因：** 鼠标快速移动导致频繁更新

**解决：** 已通过 `silent: true` 配置优化

### 问题3：移动端触摸不显示

**原因：** 移动端没有 `mouseover` 事件

**待优化：** 可以考虑添加 `touch` 事件支持

---

## 📝 代码位置

**文件：** `frontend/js/app.js`

**主要修改：**
1. 添加 markLine 配置（约1190-1220行）
2. 添加鼠标事件监听（约1340-1410行）

**相关变量：**
- `supportPriceMap` - 支撑线价格Map
- `pressurePriceMap` - 压力线价格Map
- `chart` - ECharts实例

---

## 🚀 未来优化方向

### 1. 增强交互
- [ ] 支持点击固定显示压力/支撑线
- [ ] 添加移动端触摸支持
- [ ] 显示历史压力/支撑线的变化

### 2. 视觉优化
- [ ] 可配置颜色和样式
- [ ] 添加动画效果
- [ ] 显示更多信息（如赔率、胜率等）

### 3. 数据扩展
- [ ] 显示多级支撑位/压力位
- [ ] 显示支撑/压力强度
- [ ] 预测未来压力/支撑位

---

## 📞 反馈与建议

如有问题或建议，请：
1. 查看浏览器控制台错误信息
2. 确认数据库中有压力/支撑线数据
3. 验证 ECharts 版本兼容性 (5.4.3+)

