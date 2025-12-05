# Ubuntu部署说明 - 刷新成交量类型和K线组合定时任务

## 部署方式

有两种部署方式，推荐使用 **方式1（systemd服务）**，更稳定可靠。

---

## 方式1: systemd服务（推荐）

### 1. 运行部署脚本

```bash
cd backend/scripts
chmod +x ubuntu_deploy.sh
./ubuntu_deploy.sh
```

### 2. 启动服务

```bash
# 启动服务
sudo systemctl start refresh-volume-patterns

# 设置开机自启
sudo systemctl enable refresh-volume-patterns

# 查看服务状态
sudo systemctl status refresh-volume-patterns
```

### 3. 管理服务

```bash
# 启动服务
sudo systemctl start refresh-volume-patterns

# 停止服务
sudo systemctl stop refresh-volume-patterns

# 重启服务
sudo systemctl restart refresh-volume-patterns

# 查看实时日志
sudo journalctl -u refresh-volume-patterns -f

# 查看最近100行日志
sudo journalctl -u refresh-volume-patterns -n 100
```

### 4. 服务配置

服务文件位置：`/etc/systemd/system/refresh-volume-patterns.service`

**执行时间**：每天 17:00（在Python脚本中配置）

**日志文件**：
- 标准输出：`backend/scripts/logs/scheduler_output.log`
- 标准错误：`backend/scripts/logs/scheduler_error.log`
- 应用日志：`backend/scripts/logs/refresh_volume_type.log`

---

## 方式2: Cron定时任务

### 1. 运行配置脚本

```bash
cd backend/scripts
chmod +x ubuntu_cron_setup.sh
./ubuntu_cron_setup.sh
```

脚本会自动：
- 创建执行脚本 `run_refresh_job.sh`
- 添加cron任务（每天17:00执行）

### 2. 手动配置（可选）

如果不想使用脚本，可以手动配置：

```bash
# 编辑crontab
crontab -e

# 添加以下行（每天17:00执行）
0 17 * * * /path/to/backend/scripts/run_refresh_job.sh
```

### 3. 管理Cron任务

```bash
# 查看cron任务
crontab -l

# 编辑cron任务
crontab -e

# 删除所有cron任务（谨慎操作）
crontab -r
```

### 4. 查看日志

```bash
# 查看执行日志
tail -f backend/scripts/logs/cron_refresh.log

# 查看应用日志
tail -f backend/scripts/logs/refresh_volume_type.log
```

---

## 环境要求

### 1. Python环境

```bash
# 检查Python版本（需要Python 3.6+）
python3 --version

# 如果没有，安装Python
sudo apt update
sudo apt install python3 python3-pip
```

### 2. 安装依赖

```bash
cd backend/scripts

# 安装依赖
pip3 install pymysql APScheduler

# 或使用requirements.txt（如果有）
pip3 install -r ../../requirements.txt
```

### 3. 配置文件

确保 `config_production_master.py` 文件存在，包含正确的数据库配置。

---

## 测试

### 测试脚本（不启动定时任务）

```bash
cd backend/scripts

# 测试模式：只处理前5只股票，最近30天
python3 refresh_volume_type_production.py --test 5 --days 30

# 正常模式：处理全部股票，最近90天
python3 refresh_volume_type_production.py --days 90
```

### 测试定时任务

```bash
# 方式1: 测试systemd服务
sudo systemctl start refresh-volume-patterns
sudo systemctl status refresh-volume-patterns

# 方式2: 测试cron（手动执行脚本）
./run_refresh_job.sh
```

---

## 故障排查

### 1. 服务无法启动

```bash
# 查看服务状态
sudo systemctl status refresh-volume-patterns

# 查看详细错误
sudo journalctl -u refresh-volume-patterns -n 50
```

### 2. 权限问题

```bash
# 确保脚本有执行权限
chmod +x backend/scripts/refresh_volume_type_production.py
chmod +x backend/scripts/run_refresh_job.sh

# 确保日志目录可写
chmod 755 backend/scripts/logs
```

### 3. Python路径问题

如果出现模块导入错误，检查 `PYTHONPATH`：

```bash
# 在脚本中设置PYTHONPATH
export PYTHONPATH="/path/to/backend:/path/to/project"
```

### 4. 数据库连接问题

检查 `config_production_master.py` 中的数据库配置是否正确。

---

## 日志文件说明

- `logs/refresh_volume_type.log`: 主日志文件（应用日志）
- `logs/scheduler_output.log`: systemd标准输出
- `logs/scheduler_error.log`: systemd标准错误
- `logs/cron_refresh.log`: cron执行日志

---

## 定时任务配置

**执行时间**：每天 17:00（下午5点）

**刷新范围**：
- 最近90天（3个月）的数据
- `stock_list.csv` 中的所有股票

**刷新内容**：
- `volume_type`: 成交量类型
- `bullish_pattern`: 多头K线组合
- `bearish_pattern`: 空头K线组合

---

## 注意事项

1. **首次运行**：建议先用 `--test` 参数测试少量股票
2. **执行时间**：每天17:00执行，可能需要较长时间（5000+只股票）
3. **资源占用**：执行时会占用数据库连接和CPU资源
4. **日志管理**：定期清理日志文件，避免占用过多磁盘空间

---

## 更新定时任务时间

如果需要修改执行时间：

### systemd方式
编辑服务文件：
```bash
sudo nano /etc/systemd/system/refresh-volume-patterns.service
```
修改Python脚本中的 `CronTrigger(hour=17, minute=0)` 部分

### Cron方式
```bash
crontab -e
# 修改时间，例如改为每天18:00：
0 18 * * * /path/to/backend/scripts/run_refresh_job.sh
```

