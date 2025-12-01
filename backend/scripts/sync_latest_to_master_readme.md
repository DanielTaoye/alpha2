# 同步数据到主库说明

## 脚本说明

`sync_latest_daily_chance_to_production.py` - 将最新一周的每日机会数据同步到生产数据库主库

## 功能

1. 从外部API获取59支股票的每日机会数据
2. 计算最新一天的成交量类型（基于预测成交量）
3. 只保存最近7天的数据到数据库
4. 包含：赔率总分、支撑线、压力线、成交量类型

## 运行环境要求

⚠️ **重要**: 此脚本需要连接到主库（172.17.16.30:3306），只能在以下环境运行：

1. **腾讯云服务器上** - 直接内网访问
2. **通过VPN连接** - 需要配置VPN访问腾讯云内网
3. **通过跳板机** - SSH隧道方式

## 运行方法

### 在腾讯云服务器上运行

```bash
cd /path/to/alpha_strategy_v2/backend
python scripts/sync_latest_daily_chance_to_production.py
```

### 在本地通过SSH隧道运行

```bash
# 1. 先建立SSH隧道（映射远程主库到本地端口）
ssh -L 3307:172.17.16.30:3306 user@your-server-ip

# 2. 修改脚本配置使用本地端口3307

# 3. 运行脚本
cd backend
python scripts/sync_latest_daily_chance_to_production.py
```

## 数据库说明

- **从库（只读）**: sh-cdbrg-8f14w39q.sql.tencentcdb.com:25924 - 本地开发用
- **主库（可写）**: 172.17.16.30:3306 - 生产数据写入

## 同步的股票

共59支股票，分为三组：
- 波段：20支
- 短线：20支  
- 中长线：19支

## 注意事项

1. 只同步最近7天的数据，避免全量同步
2. 使用 `ON DUPLICATE KEY UPDATE` 语句，相同日期会更新
3. 成交量类型只计算最新一天（基于实时预测成交量）
4. 压力线和支撑线存储为整数（乘以100）

