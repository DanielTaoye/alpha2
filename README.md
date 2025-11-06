# 阿尔法策略2.0系统

一个基于Flask + ECharts的股票K线分析系统，支持多周期K线展示和智能分析。

## 功能特性

- 📊 支持30分钟、日K、周K、月K四种周期切换
- 📈 实时显示K线图和成交量
- 🎯 智能分析：益损比、支撑线、压力线
- 📱 响应式设计，支持各种屏幕尺寸
- 🔄 股票分组管理：波段、短线、中长线三种策略

## 技术栈

**后端：**
- Flask 3.0.0
- PyMySQL 1.1.0
- Flask-CORS 4.0.0

**前端：**
- HTML5 + CSS3 + JavaScript
- ECharts 5.4.3

**数据库：**
- MySQL

## 股票列表

### 波段策略
- 国投智能 (SZ300188)
- 海兴电力 (SH603556)
- 沃尔核材 (SZ002130)
- 歌华有线 (SH600037)
- 中集车辆 (SZ301039)

### 短线策略
- 白云机场 (SH600004)
- 金雷股份 (SZ300443)
- 南京化纤 (SH600889)
- 慧智微-U (SH688512)
- 锴威特 (SH688693)

### 中长线策略
- 立讯精密 (SZ002475)
- 宁德时代 (SZ300750)
- 农业银行 (SH601288)
- 中国石油 (SH601857)
- 紫金矿业 (SH601899)

## 安装步骤

### 1. 克隆项目
```bash
cd alpha_strategy_v2
```

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 配置数据库
修改 `backend/app.py` 中的数据库配置：
```python
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'your_password',  # 修改为实际密码
    'database': 'your_database',  # 修改为实际数据库名
    'charset': 'utf8mb4'
}
```

### 4. 确保数据库表存在
系统需要以下数据表（每个股票一张表）：
- basic_data_sh600004 (白云机场)
- basic_data_sz300188 (国投智能)
- ... （其他股票表）

表结构参考 `peroid_type` 字段映射：
- 4: 30分钟K线
- 6: 日K线
- 7: 周K线
- 8: 月K线

### 5. 启动服务
```bash
cd backend
python app.py
```

服务将在 http://localhost:5000 启动

### 6. 访问系统
在浏览器中打开：http://localhost:5000

## 项目结构

```
alpha_strategy_v2/
├── backend/
│   └── app.py              # Flask后端服务
├── frontend/
│   └── index.html          # 前端页面
├── config.py               # 配置文件
├── requirements.txt        # Python依赖
└── README.md              # 项目文档
```

## API接口

### 1. 获取股票分组
```
GET /api/stock_groups
```

### 2. 获取K线数据
```
POST /api/kline_data
Body: {
    "table_name": "basic_data_sh600004",
    "period_type": "day"
}
```

### 3. 获取股票分析数据
```
POST /api/stock_analysis
Body: {
    "stock_code": "SH600004"
}
```

## 数据说明

### K线数据字段
- `shi_jian`: 时间
- `kai_pan_jia`: 开盘价
- `zui_gao_jia`: 最高价
- `zui_di_jia`: 最低价
- `shou_pan_jia`: 收盘价
- `cheng_jiao_liang`: 成交量
- `liang_bi`: 量比
- `wei_bi`: 委比

### 分析数据字段
- `winLoseRatio`: 益损比
- `supportPrice`: 支撑价格
- `pressurePrice`: 压力价格

## 注意事项

1. 确保MySQL数据库服务正常运行
2. 确保数据库中有最近3年的K线数据
3. 外部API的token可能需要更新
4. 如果表名不一致，需要在代码中修改对应的表名映射

## 常见问题

**Q: 图表不显示数据？**
A: 检查数据库连接配置和表名是否正确

**Q: 支撑线/压力线不显示？**
A: 检查外部API是否可用，token是否有效

**Q: 跨域问题？**
A: 已使用Flask-CORS处理，如仍有问题请检查浏览器控制台

## 后续优化方向

- [ ] 添加实时数据推送功能
- [ ] 增加更多技术指标（MA、MACD、KDJ等）
- [ ] 添加用户登录和权限管理
- [ ] 优化大数据量加载性能
- [ ] 添加数据导出功能
- [ ] 移动端适配优化

## 开发者

阿尔法策略团队

## 许可证

MIT License
