# 刷新 b_daily_chance 表脚本使用说明

## 📋 功能说明

这两个脚本用于重新计算并更新 `b_daily_chance` 表中的三个字段：
- `volume_type` - 成交量类型（A/B/C/D/E/F/G/H/X/Y/Z）
- `bullish_pattern` - 多头组合（如：十字星+中阳线）
- `bearish_pattern` - 空头组合（如：十字星+中阴）

## 📦 脚本列表

### 0. 备份工具：`backup_daily_chance.py` ⭐推荐先执行

**功能：** 备份 b_daily_chance 表的关键字段

**使用场景：** 执行刷新前先备份

**运行方式：**
```bash
python backup_daily_chance.py
```

**特点：**
- ✅ 自动生成带时间戳的备份文件
- ✅ 可用于恢复数据
- ✅ 备份文件为SQL格式

**备份文件示例：**
```
backup_daily_chance_20241124_143055.sql
```

---

### 0.5. 对比工具：`compare_daily_chance_patterns.py` ⭐推荐先查看

**功能：** 对比新旧数据差异（不更新数据库）

**使用场景：** 执行刷新前先查看会有哪些变化

**运行方式：**
```bash
# 对比指定股票的最近10条记录
python compare_daily_chance_patterns.py -s SH600000

# 对比指定股票的最近20条记录
python compare_daily_chance_patterns.py -s SH600000 -n 20
```

**特点：**
- ✅ 不修改数据库，只查看差异
- ✅ 清晰显示新旧值对比
- ✅ 统计差异数量

---

### 1. 基础版本：`refresh_daily_chance_patterns.py`

**功能：** 刷新所有股票的所有记录

**使用场景：** 首次刷新或全量更新

**运行方式：**
```bash
python refresh_daily_chance_patterns.py
```

**特点：**
- ✅ 简单直接，无需参数
- ✅ 自动处理所有股票
- ✅ 每100条记录提交一次
- ✅ 支持中途中断保存

---

### 2. 高级版本：`refresh_daily_chance_patterns_advanced.py`

**功能：** 支持指定股票代码和日期范围的刷新

**使用场景：** 增量更新、特定股票更新

**运行方式：**

#### 基本用法（刷新所有）
```bash
python refresh_daily_chance_patterns_advanced.py
```

#### 指定单个股票
```bash
python refresh_daily_chance_patterns_advanced.py -s SH600000
```

#### 指定多个股票
```bash
python refresh_daily_chance_patterns_advanced.py -s SH600000 SZ000001 SH601318
```

#### 指定日期范围
```bash
# 刷新所有股票的 2024年数据
python refresh_daily_chance_patterns_advanced.py --start 2024-01-01 --end 2024-12-31
```

#### 指定股票 + 日期范围
```bash
# 刷新指定股票的 2024年11月数据
python refresh_daily_chance_patterns_advanced.py -s SH600000 --start 2024-11-01 --end 2024-11-30
```

#### 跳过确认直接执行
```bash
python refresh_daily_chance_patterns_advanced.py -s SH600000 -y
```

---

## 📊 参数说明

| 参数 | 简写 | 说明 | 示例 |
|------|------|------|------|
| `--stocks` | `-s` | 指定股票代码（可多个） | `-s SH600000 SZ000001` |
| `--start` | - | 开始日期（YYYY-MM-DD） | `--start 2024-01-01` |
| `--end` | - | 结束日期（YYYY-MM-DD） | `--end 2024-12-31` |
| `--yes` | `-y` | 跳过确认直接执行 | `-y` |

---

## 🔄 执行流程

1. **连接数据库**
2. **获取股票代码列表**（如果指定了股票，则只获取指定的）
3. **确认执行**（除非使用 `-y` 参数）
4. **逐个处理股票：**
   - 获取该股票的 daily_chance 记录
   - 对每条记录：
     - 计算成交量类型
     - 识别多头组合
     - 识别空头组合
     - 更新数据库
5. **显示统计结果**

---

## 🔄 推荐执行流程

### ⭐ 标准流程（推荐）

```bash
# 步骤1：备份数据（重要！）
python backup_daily_chance.py

# 步骤2：对比查看差异（可选，但推荐）
python compare_daily_chance_patterns.py -s SH600000 -n 10

# 步骤3：小范围测试
python refresh_daily_chance_patterns_advanced.py -s SH600000 -y

# 步骤4：验证结果
# 查看数据库确认更新正确

# 步骤5：全量刷新
python refresh_daily_chance_patterns.py
```

---

## 💡 使用示例

### 场景1：首次刷新整个数据库

```bash
python refresh_daily_chance_patterns.py
```

**预期输出：**
```
================================================================================
开始刷新 b_daily_chance 表
================================================================================
数据库: localhost:3306/stock
--------------------------------------------------------------------------------
✓ 数据库连接成功
✓ 找到 1250 只股票
--------------------------------------------------------------------------------

是否开始刷新 1250 只股票的数据？(y/n): y

================================================================================
开始刷新...
================================================================================

[1/1250] 处理股票: SH600000
开始处理股票 SH600000，共 500 条记录
  进度: 100/500 (100 条已更新)
  进度: 200/500 (200 条已更新)
  ...
股票 SH600000 处理完成，更新了 500/500 条记录

[2/1250] 处理股票: SH600001
...
```

---

### 场景2：只刷新特定股票

```bash
# 只刷新白云机场和中国石油
python refresh_daily_chance_patterns_advanced.py -s SH600004 SH601857
```

---

### 场景3：刷新最近一个月的数据

```bash
# 刷新所有股票 2024年11月的数据
python refresh_daily_chance_patterns_advanced.py --start 2024-11-01 --end 2024-11-30
```

---

### 场景4：批量处理（用于定时任务）

```bash
# 跳过确认，直接执行（适合定时任务）
python refresh_daily_chance_patterns_advanced.py --start 2024-11-24 -y
```

---

## ⚠️ 注意事项

### 1. 数据库连接
- 确保 `config.py` 中的数据库配置正确
- 确保数据库用户有读写权限

### 2. 执行时间
- 全量刷新可能需要较长时间（取决于数据量）
- 建议先用小范围测试（指定1-2只股票）

### 3. 中断恢复
- 两个脚本都支持 `Ctrl+C` 中断
- 中断时会自动保存已处理的数据
- 可以从中断的地方继续（使用日期范围参数）

### 4. 错误处理
- 单条记录失败不会影响其他记录
- 错误信息会记录到日志
- 最后会显示成功/失败统计

---

## 📝 日志查看

脚本运行时会输出详细日志：

```
[1/10] 处理股票: SH600000
开始处理股票 SH600000，共 500 条记录
  进度: 50/500 (50 条已更新)
  进度: 100/500 (100 条已更新)
股票 SH600000 处理完成，更新了 500/500 条记录
```

如果有错误，会显示：
```
ERROR - 处理记录失败 SH600000 2024-11-24: [错误详情]
```

---

## 🚀 性能优化

### 提交策略
- **基础版本**：每100条记录提交一次
- **高级版本**：每50条记录提交一次

### 优化建议
1. 如果数据量大，可以分批次处理
2. 可以并行处理多个股票（需修改脚本）
3. 考虑在低峰期运行

---

## 🔙 恢复备份

如果刷新后发现问题，可以从备份恢复：

### 方法1：使用 MySQL 命令行

```bash
mysql -h localhost -u root -p stock < backup_daily_chance_20241124_143055.sql
```

### 方法2：使用 MySQL 客户端

```sql
SOURCE /path/to/backup_daily_chance_20241124_143055.sql;
```

### 方法3：使用 Python 脚本

```python
import pymysql
from config import DATABASE_CONFIG

conn = pymysql.connect(**DATABASE_CONFIG)
cursor = conn.cursor()

with open('backup_daily_chance_20241124_143055.sql', 'r') as f:
    sql_script = f.read()
    for statement in sql_script.split(';'):
        if statement.strip():
            cursor.execute(statement)
conn.commit()
conn.close()
```

---

## 🔧 常见问题

### Q1: 提示"没有需要处理的股票"
**A:** 检查：
- b_daily_chance 表是否有数据
- 指定的股票代码是否正确
- 日期范围是否正确

### Q2: 某些股票更新失败
**A:** 可能原因：
- basic_data_xxx 表不存在
- 历史数据不足（需要至少2天数据）
- 数据质量问题

### Q3: 如何验证更新成功？
**A:** 查询数据库：
```sql
SELECT stock_code, date, volume_type, bullish_pattern, bearish_pattern 
FROM b_daily_chance 
WHERE stock_code = 'SH600000' 
ORDER BY date DESC 
LIMIT 10;
```

---

## 📞 联系与支持

如有问题，请检查：
1. 数据库连接配置
2. 日志输出信息
3. 相关服务代码（VolumeTypeService、BullishPatternService、BearishPatternService）

