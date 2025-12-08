# Scheduler 定时任务脚本清单

## 📋 总览

项目中有 **3个主要的定时任务脚本**，它们会在不同时间执行不同的任务。

---

## 1. `daily_chance_scheduler.py` ⭐ 主要脚本

### 执行时间
- **每天 17:00**（下午5点）

### 功能
更新生产数据库的**最新一天**的每日机会数据，包括：

1. **从API获取数据**
   - 调用外部API：`http://121.5.174.81:8005/stock/getDailyChanceWithBeauty`
   - 获取59支代表性股票的最新数据

2. **保存到数据库** (`b_daily_chance` 表)
   - ✅ 赔率总分 (`total_win_ratio_score`)
   - ✅ 日线赔率得分 (`day_win_ratio_score`)
   - ✅ 周线赔率得分 (`week_win_ratio_score`)
   - ✅ 支撑价格 (`support_price`)
   - ✅ 压力价格 (`pressure_price`)
   - ✅ **成交量类型** (`volume_type`) - 实时计算

3. **刷新多空组合**
   - ✅ **多头组合** (`bullish_pattern`) - 实时计算
   - ✅ **空头组合** (`bearish_pattern`) - 实时计算

### 处理范围
- **股票数量**：59支（从 `stock_config.json` 读取）
- **数据范围**：只处理**最新1天**的数据

### 启动方式
```bash
# 方式1：直接运行（会启动定时任务）
python backend/scripts/daily_chance_scheduler.py

# 方式2：立即执行一次（不启动定时任务）
python backend/scripts/daily_chance_scheduler.py --now

# 方式3：使用启动脚本
bash backend/scripts/start_daily_chance_scheduler.sh  # Linux
backend\scripts\start_daily_chance_scheduler.bat      # Windows
```

### 日志文件
- `backend/scripts/logs/daily_chance_scheduler.log`

---

## 2. `schedule_daily_chance.py` ⚠️ 备用脚本

### 执行时间
- **每天 16:00**（下午4点）

### 功能
同步每日机会数据（使用 `DailyChanceService`）

### 处理范围
- 调用 `service.sync_all_stocks_daily_chance()` 同步所有股票

### 启动方式
```bash
python backend/scripts/schedule_daily_chance.py
```

### 说明
⚠️ **注意**：这个脚本与 `daily_chance_scheduler.py` 功能类似，但执行时间不同（16:00 vs 17:00）。建议只使用其中一个。

---

## 3. `refresh_volume_type_production.py` 📊 历史数据刷新

### 执行时间
- **每天 17:00**（下午5点）- 需要 `--scheduler` 参数

### 功能
刷新生产库 `b_daily_chance` 表的**历史数据**（最近90天）：

1. **成交量类型** (`volume_type`)
2. **多头K线组合** (`bullish_pattern`)
3. **空头K线组合** (`bearish_pattern`)

### 处理范围
- **股票数量**：所有股票（从 `all_stock` 表读取）
- **数据范围**：最近 **90天**（可配置）

### 启动方式
```bash
# 方式1：定时任务模式（每天17:00执行）
python backend/scripts/refresh_volume_type_production.py --scheduler

# 方式2：立即执行一次（刷新最近90天）
python backend/scripts/refresh_volume_type_production.py --days 90

# 方式3：测试模式（只处理前5只股票，最近30天）
python backend/scripts/refresh_volume_type_production.py --test 5 --days 30

# 方式4：使用启动脚本
backend\scripts\start_refresh_scheduler.bat  # Windows
```

### 日志文件
- `backend/scripts/logs/refresh_volume_type.log`

---

## 📊 对比总结

| 脚本 | 执行时间 | 股票范围 | 数据范围 | 主要功能 |
|------|---------|---------|---------|---------|
| **daily_chance_scheduler.py** | 17:00 | 59支 | 最新1天 | API数据 + 成交量类型 + 多空组合 |
| **schedule_daily_chance.py** | 16:00 | 全部 | 最新1天 | 同步每日机会数据 |
| **refresh_volume_type_production.py** | 17:00 | 全部 | 最近90天 | 刷新历史成交量类型和组合 |

---

## ⚠️ 注意事项

### 1. 时间冲突
- `daily_chance_scheduler.py` 和 `refresh_volume_type_production.py` 都在 **17:00** 执行
- 建议错开时间，或确保服务器资源充足

### 2. 功能重叠
- `daily_chance_scheduler.py` 和 `schedule_daily_chance.py` 功能类似
- 建议只使用 `daily_chance_scheduler.py`（功能更完整）

### 3. 数据范围
- `daily_chance_scheduler.py`：只处理**最新1天**
- `refresh_volume_type_production.py`：处理**最近90天**（历史数据）

### 4. 股票范围
- `daily_chance_scheduler.py`：只处理**59支代表性股票**
- `refresh_volume_type_production.py`：处理**全部股票**（5000+支）

---

## 🚀 推荐配置

### 生产环境建议

**方案1：只使用 daily_chance_scheduler.py**
```
17:00 - daily_chance_scheduler.py（最新1天，59支股票）
```

**方案2：错开时间**
```
16:00 - schedule_daily_chance.py（最新1天，全部股票）
17:00 - daily_chance_scheduler.py（最新1天，59支股票）
18:00 - refresh_volume_type_production.py（历史90天，全部股票）
```

**方案3：周末刷新历史数据**
```
每天 17:00 - daily_chance_scheduler.py（最新1天）
每周日 02:00 - refresh_volume_type_production.py（历史90天）
```

---

## 📝 检查运行状态

### 查看进程
```bash
# Linux
ps aux | grep scheduler

# Windows
tasklist | findstr python
```

### 查看日志
```bash
# daily_chance_scheduler
tail -f backend/scripts/logs/daily_chance_scheduler.log

# refresh_volume_type_production
tail -f backend/scripts/logs/refresh_volume_type.log
```

### 使用检查脚本
```bash
bash backend/scripts/check_scheduler_status.sh
```

---

## 🔧 停止服务

```bash
# Linux
bash backend/scripts/stop_daily_chance_scheduler.sh

# 或直接 kill 进程
ps aux | grep scheduler
kill <PID>
```
