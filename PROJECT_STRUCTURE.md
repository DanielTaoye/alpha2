# 项目结构说明

## 📁 目录结构

```
alpha_strategy_v2/
│
├── backend/                    # 后端目录
│   └── app.py                 # Flask主应用
│
├── frontend/                   # 前端目录
│   ├── index.html             # 主页面
│   └── favicon.ico            # 网站图标
│
├── config.py                   # 配置文件
├── config_example.py           # 配置示例
├── requirements.txt            # Python依赖列表
│
├── database_check.py           # 数据库检查工具
│
├── install.bat                 # Windows安装脚本
├── start.bat                  # Windows启动脚本
├── start.sh                   # Linux/Mac启动脚本
│
├── README.md                   # 项目说明
├── QUICKSTART.md              # 快速开始指南
├── USAGE.md                   # 详细使用指南
├── PROJECT_STRUCTURE.md       # 本文件
│
└── .gitignore                 # Git忽略文件
```

## 📄 文件说明

### 核心文件

#### backend/app.py
Flask后端应用的主文件，包含：
- 数据库连接配置
- API路由定义
- 股票分组配置
- K线数据查询
- 外部API调用（获取分析数据）

**主要API接口：**
- `GET /` - 返回首页
- `GET /api/stock_groups` - 获取股票分组
- `POST /api/kline_data` - 获取K线数据
- `POST /api/stock_analysis` - 获取股票分析数据

#### frontend/index.html
前端页面，单页面应用，包含：
- 页面布局和样式
- ECharts图表集成
- 数据请求和渲染逻辑
- 用户交互功能

**主要功能：**
- 股票分组显示
- K线图渲染
- 周期切换
- 支撑线/压力线显示
- 分析指标展示

### 配置文件

#### config.py
主配置文件（需要手动配置）：
- 数据库连接信息
- API配置
- 服务器配置

#### config_example.py
配置示例文件，包含：
- 配置项说明
- 默认值示例
- 股票表名映射

### 工具脚本

#### database_check.py
数据库检查工具，用于：
- 验证数据库连接
- 检查表是否存在
- 验证表结构
- 检查数据完整性

**使用方法：**
```bash
python database_check.py
```

#### install.bat (Windows)
自动安装脚本：
- 检查Python环境
- 安装依赖包
- 显示安装状态

#### start.bat (Windows)
启动脚本：
- 切换到backend目录
- 启动Flask应用

#### start.sh (Linux/Mac)
Linux/Mac启动脚本（功能同start.bat）

### 文档文件

#### README.md
项目主文档，包含：
- 项目介绍
- 功能特性
- 技术栈
- 安装步骤
- API接口说明

#### QUICKSTART.md
快速开始指南，包含：
- 最简化的启动步骤
- 常见问题快速解决
- 基本使用说明

#### USAGE.md
详细使用指南，包含：
- 完整的安装步骤
- 功能详细说明
- 故障排除
- 性能优化建议
- 部署指南

#### PROJECT_STRUCTURE.md
本文件，说明项目结构

### 依赖文件

#### requirements.txt
Python依赖列表：
```
Flask==3.0.0          # Web框架
Flask-CORS==4.0.0     # 跨域支持
pymysql==1.1.0        # MySQL连接
requests==2.31.0      # HTTP请求
```

#### .gitignore
Git忽略文件，排除：
- Python缓存文件
- 虚拟环境
- IDE配置
- 日志文件
- 本地配置

## 🔧 技术架构

### 后端架构

```
Flask Application
    │
    ├── Routes (路由)
    │   ├── / (首页)
    │   └── /api/* (API接口)
    │
    ├── Database (数据库)
    │   └── MySQL Connection
    │       └── Stock Tables (股票表)
    │
    └── External API (外部API)
        └── Stock Analysis Service
```

### 前端架构

```
Single Page Application
    │
    ├── UI Layer (界面层)
    │   ├── Header (头部)
    │   ├── Stock Groups (股票分组)
    │   │   └── Stock Cards (股票卡片)
    │   └── Footer (底部)
    │
    ├── Chart Layer (图表层)
    │   └── ECharts
    │       ├── Candlestick (K线)
    │       ├── Volume (成交量)
    │       ├── Support Line (支撑线)
    │       └── Pressure Line (压力线)
    │
    └── Data Layer (数据层)
        ├── Fetch API (数据请求)
        └── State Management (状态管理)
```

### 数据流

```
用户操作
    ↓
前端 JavaScript
    ↓
发送 HTTP 请求
    ↓
Flask 后端
    ↓
    ├─→ MySQL 数据库 (K线数据)
    │
    └─→ 外部 API (分析数据)
    ↓
返回 JSON 数据
    ↓
前端渲染
    ↓
ECharts 图表展示
```

## 📊 数据库结构

### 表命名规则

```
basic_data_{市场代码}{股票代码小写}

示例：
- SH600004 → basic_data_sh600004
- SZ300188 → basic_data_sz300188
```

### 周期类型映射

| peroid_type | 说明 | 英文标识 |
|------------|------|---------|
| 4 | 30分钟K线 | 30min |
| 6 | 日K线 | day |
| 7 | 周K线 | week |
| 8 | 月K线 | month |

### 关键字段

**价格字段：**
- `kai_pan_jia` - 开盘价
- `zui_gao_jia` - 最高价
- `zui_di_jia` - 最低价
- `shou_pan_jia` - 收盘价

**成交字段：**
- `cheng_jiao_liang` - 成交量
- `cheng_jiao_e` - 成交额

**分析字段：**
- `liang_bi` - 量比
- `wei_bi` - 委比

**时间字段：**
- `shi_jian` - 时间（datetime）

## 🔌 API接口详解

### 1. 获取股票分组

**接口：** `GET /api/stock_groups`

**返回格式：**
```json
{
  "code": 200,
  "data": {
    "波段": [...],
    "短线": [...],
    "中长线": [...]
  },
  "message": "success"
}
```

### 2. 获取K线数据

**接口：** `POST /api/kline_data`

**请求参数：**
```json
{
  "table_name": "basic_data_sh600004",
  "period_type": "day"
}
```

**返回格式：**
```json
{
  "code": 200,
  "data": [
    {
      "time": "2024-01-01 00:00:00",
      "open": 10.5,
      "high": 11.2,
      "low": 10.3,
      "close": 11.0,
      "volume": 1000000,
      "liangbi": 1.2,
      "weibi": 0.5
    },
    ...
  ],
  "message": "success"
}
```

### 3. 获取股票分析

**接口：** `POST /api/stock_analysis`

**请求参数：**
```json
{
  "stock_code": "SH600004"
}
```

**返回格式：**
```json
{
  "code": 200,
  "data": {
    "30min": {
      "winLoseRatio": 1.5,
      "supportPrice": 40.5,
      "pressurePrice": 42.0
    },
    "day": {...},
    "week": {...},
    "month": {...}
  },
  "message": "success"
}
```

## 🎨 前端组件

### 股票卡片组件

每个股票卡片包含：
- 股票名称和代码
- 周期切换按钮
- K线图表
- 成交量图
- 分析指标（益损比、支撑线、压力线、量比、委比）

### 图表功能

**交互功能：**
- 鼠标滚轮缩放
- 拖动查看历史数据
- 悬停显示详细信息
- 图例控制显示/隐藏

**视觉元素：**
- 红绿K线（涨跌）
- 红绿成交量柱
- 绿色支撑线（虚线）
- 红色压力线（虚线）

## 🚀 扩展建议

### 功能扩展

1. **实时数据推送**
   - 使用WebSocket
   - 实现tick级数据

2. **更多技术指标**
   - MA（移动平均线）
   - MACD
   - KDJ
   - RSI
   - BOLL

3. **用户系统**
   - 登录注册
   - 自选股票
   - 个人配置

4. **预警功能**
   - 价格预警
   - 指标预警
   - 邮件/短信通知

### 性能优化

1. **数据缓存**
   - Redis缓存
   - 浏览器缓存

2. **数据压缩**
   - Gzip压缩
   - 数据抽样

3. **异步加载**
   - 懒加载
   - 分页加载

### 部署优化

1. **容器化**
   - Docker
   - Docker Compose

2. **负载均衡**
   - Nginx
   - 多实例部署

3. **数据库优化**
   - 读写分离
   - 分库分表

## 📝 开发规范

### 代码风格

- Python: PEP 8
- JavaScript: ESLint
- HTML/CSS: Prettier

### 命名规范

- 变量名：小写下划线（Python）/ 驼峰命名（JavaScript）
- 函数名：动词开头
- 类名：大驼峰命名

### 注释规范

- 函数：说明功能、参数、返回值
- 复杂逻辑：解释原因
- TODO: 标记待办事项

## 🐛 调试技巧

### 后端调试

1. 启用DEBUG模式
2. 查看控制台输出
3. 使用Python调试器

### 前端调试

1. 打开浏览器开发者工具（F12）
2. Console查看JavaScript错误
3. Network查看API请求
4. Elements检查DOM结构

### 数据库调试

1. 使用database_check.py检查
2. 直接查询数据库
3. 检查SQL日志

## 📮 联系方式

如有问题，请查看其他文档或检查：
- 系统日志
- 错误提示
- 配置文件

祝使用愉快！

