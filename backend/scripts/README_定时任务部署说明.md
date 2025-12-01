# 每日机会数据定时同步服务部署说明

## 📋 功能说明

定时任务每天晚上 **17:00** 自动更新生产数据库中59支股票最新一天的数据，包括：
- 赔率总分（日线、周线、总分）
- 支撑线
- 压力线
- 成交量类型（实时计算）

数据来源：外部API `http://121.5.174.81:8005/stock/getDailyChanceWithBeauty`

数据目标：生产主库 `sh-cdb-2hxu41ka.sql.tencentcdb.com:21648`

---

## 🚀 部署步骤

### 1. 上传文件到服务器

将以下文件上传到服务器：
```bash
backend/scripts/
├── daily_chance_scheduler.py          # 主程序
├── start_daily_chance_scheduler.sh    # 启动脚本
├── stop_daily_chance_scheduler.sh     # 停止脚本
├── check_scheduler_status.sh          # 状态检查
└── test_sync_once.sh                  # 测试脚本
```

### 2. 赋予执行权限

```bash
cd /path/to/alpha_strategy_v2/backend/scripts
chmod +x *.sh
```

### 3. 安装依赖

确保已安装 `apscheduler`：

```bash
pip install apscheduler
```

或者：

```bash
pip install -r ../../requirements.txt
```

### 4. 测试运行

先执行一次测试，确保配置正确：

```bash
bash test_sync_once.sh
```

查看输出，确认：
- ✅ 能够连接生产数据库
- ✅ 能够访问外部API
- ✅ 数据正确写入数据库

### 5. 启动定时服务

```bash
bash start_daily_chance_scheduler.sh
```

输出示例：
```
🚀 启动每日机会数据定时同步服务...
✅ 服务已启动 (PID: 12345)
📋 日志文件: /path/to/logs/daily_chance_scheduler.log
📋 输出日志: /path/to/logs/scheduler_output.log

查看日志: tail -f /path/to/logs/daily_chance_scheduler.log
停止服务: bash /path/to/stop_daily_chance_scheduler.sh
```

---

## 📊 管理命令

### 查看服务状态

```bash
bash check_scheduler_status.sh
```

### 查看实时日志

```bash
tail -f logs/daily_chance_scheduler.log
```

### 停止服务

```bash
bash stop_daily_chance_scheduler.sh
```

### 重启服务

```bash
bash stop_daily_chance_scheduler.sh
bash start_daily_chance_scheduler.sh
```

---

## 🔧 配置修改

### 修改执行时间

编辑 `daily_chance_scheduler.py`，找到：

```python
scheduler.add_job(
    sync_daily_chance_job,
    trigger=CronTrigger(hour=17, minute=0),  # 修改这里
    ...
)
```

时间格式说明：
- `hour=17, minute=0` - 每天17:00
- `hour=9, minute=30` - 每天9:30
- `hour=17, minute=0, day_of_week='mon-fri'` - 工作日17:00

### 修改数据库配置

编辑 `daily_chance_scheduler.py`，修改：

```python
MASTER_DB_CONFIG = {
    'host': 'sh-cdb-2hxu41ka.sql.tencentcdb.com',
    'port': 21648,
    'user': 'root',
    'password': 'MrEPYZus7myr',
    'database': 'stock',
    'charset': 'utf8mb4'
}
```

---

## 📝 日志文件

日志存放在 `backend/scripts/logs/` 目录：

- `daily_chance_scheduler.log` - 任务执行日志
- `scheduler_output.log` - 标准输出/错误日志
- `scheduler.pid` - 进程PID文件

---

## 🔍 故障排查

### 服务无法启动

1. 检查Python环境：
```bash
python3 --version
pip list | grep apscheduler
```

2. 检查端口和数据库连接：
```bash
telnet sh-cdb-2hxu41ka.sql.tencentcdb.com 21648
```

3. 查看详细错误日志：
```bash
cat logs/scheduler_output.log
```

### 任务未执行

1. 检查服务状态：
```bash
bash check_scheduler_status.sh
```

2. 查看最近的日志：
```bash
tail -n 50 logs/daily_chance_scheduler.log
```

3. 检查系统时间：
```bash
date
```

### 数据未更新

1. 手动执行一次测试：
```bash
bash test_sync_once.sh
```

2. 检查数据库中的数据：
```sql
SELECT * FROM b_daily_chance 
WHERE date = CURDATE() 
ORDER BY updated_at DESC 
LIMIT 10;
```

---

## 🌟 systemd 服务配置（可选）

如果希望服务开机自启动，可以配置为 systemd 服务。

### 1. 创建服务文件

```bash
sudo nano /etc/systemd/system/daily-chance-sync.service
```

内容：

```ini
[Unit]
Description=Daily Chance Data Sync Service
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/alpha_strategy_v2
ExecStart=/usr/bin/python3 /path/to/alpha_strategy_v2/backend/scripts/daily_chance_scheduler.py
Restart=on-failure
RestartSec=10
StandardOutput=append:/path/to/alpha_strategy_v2/backend/scripts/logs/scheduler_output.log
StandardError=append:/path/to/alpha_strategy_v2/backend/scripts/logs/scheduler_output.log

[Install]
WantedBy=multi-user.target
```

### 2. 启用并启动服务

```bash
sudo systemctl daemon-reload
sudo systemctl enable daily-chance-sync
sudo systemctl start daily-chance-sync
```

### 3. 管理服务

```bash
# 查看状态
sudo systemctl status daily-chance-sync

# 查看日志
sudo journalctl -u daily-chance-sync -f

# 重启服务
sudo systemctl restart daily-chance-sync

# 停止服务
sudo systemctl stop daily-chance-sync
```

---

## 📞 联系方式

如有问题，请联系技术支持。

