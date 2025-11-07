# DDD架构说明

## 项目结构

本项目已重构为DDD（领域驱动设计）架构，分为4层：

```
backend/
├── interfaces/              # 用户接口层（User Interface Layer）
│   ├── controllers/         # API控制器
│   │   ├── stock_controller.py       # 股票控制器
│   │   ├── kline_controller.py       # K线数据控制器
│   │   └── analysis_controller.py    # 分析控制器
│   └── dto/                 # 数据传输对象
│       └── response.py      # 响应DTO
│
├── application/             # 应用层（Application Layer）
│   ├── services/            # 应用服务
│   │   ├── stock_service.py          # 股票应用服务
│   │   ├── kline_service.py          # K线应用服务
│   │   └── analysis_service.py       # 分析应用服务
│   └── use_cases/           # 用例编排
│
├── domain/                  # 领域层（Domain Layer）
│   ├── models/              # 领域模型
│   │   ├── stock.py         # 股票实体和值对象
│   │   └── kline.py         # K线数据实体
│   ├── repositories/        # 仓储接口
│   │   ├── kline_repository.py              # K线仓储接口
│   │   └── stock_analysis_repository.py     # 分析仓储接口
│   └── services/            # 领域服务
│       └── period_service.py         # 周期服务
│
├── infrastructure/          # 基础设施层（Infrastructure Layer）
│   ├── persistence/         # 数据持久化
│   │   ├── database.py                      # 数据库连接
│   │   └── kline_repository_impl.py         # K线仓储实现
│   ├── external_apis/       # 外部API
│   │   ├── stock_analysis_api.py            # 股票分析API客户端
│   │   └── stock_analysis_repository_impl.py # 分析仓储实现
│   └── config/              # 配置
│       ├── database_config.py       # 数据库配置
│       ├── api_config.py            # API配置
│       └── app_config.py            # 应用配置
│
├── app_new.py               # 新的应用入口（DDD版）
└── app.py                   # 旧的应用入口（保留）

frontend/
├── css/
│   └── styles.css           # 样式文件
├── js/
│   └── app.js               # 主应用脚本
├── index_new.html           # 新的主页（分离版）
└── index.html               # 旧的主页（保留）
```

## 各层职责

### 1. 用户接口层（interfaces/）
- **职责**：处理HTTP请求和响应，提供RESTful API
- **包含**：
  - 控制器（Controllers）：处理路由请求
  - DTO（Data Transfer Objects）：数据传输对象

### 2. 应用层（application/）
- **职责**：协调领域层完成业务用例，处理流程控制
- **特点**：
  - 不包含业务规则
  - 负责事务管理
  - 编排领域服务和仓储

### 3. 领域层（domain/）
- **职责**：核心业务逻辑层，体现业务规则和状态
- **包含**：
  - 实体（Entities）：具有唯一标识的业务对象
  - 值对象（Value Objects）：没有唯一标识的业务对象
  - 聚合根（Aggregate Roots）：聚合的根实体
  - 仓储接口（Repository Interfaces）：数据访问抽象
  - 领域服务（Domain Services）：跨实体的业务逻辑

### 4. 基础设施层（infrastructure/）
- **职责**：提供技术能力支持
- **包含**：
  - 数据库访问
  - 外部API调用
  - 配置管理
  - 仓储接口的具体实现

## 依赖关系

```
用户接口层 → 应用层 → 领域层 ← 基础设施层
```

- **依赖原则**：依赖方向应该是从外层指向内层
- **核心原则**：领域层不依赖任何外层，是整个应用的核心

## 运行方式

### 使用新架构
```bash
cd backend
python app_new.py
```

### 使用旧架构（向后兼容）
```bash
cd backend
python app.py
```

## 主要改进

1. **关注点分离**：各层职责明确，易于维护
2. **可测试性**：领域逻辑独立，便于单元测试
3. **可扩展性**：新增功能时遵循开闭原则
4. **复用性**：领域模型和服务可以在不同场景复用
5. **依赖倒置**：通过接口解耦，基础设施层实现领域层定义的接口

## 迁移说明

### 后端迁移
1. 旧的`app.py`文件已保留，可继续使用
2. 新的`app_new.py`使用DDD架构
3. 配置文件已迁移到`infrastructure/config/`

### 前端迁移
1. 旧的`index.html`已保留（包含内联CSS和JS）
2. 新的`index_new.html`使用外部CSS和JS文件
3. CSS文件：`frontend/css/styles.css`
4. JS文件：`frontend/js/app.js`

## 配置说明

所有配置文件位于`backend/infrastructure/config/`：

- `database_config.py`：数据库连接配置
- `api_config.py`：外部API配置
- `app_config.py`：应用配置（服务器、周期映射等）

